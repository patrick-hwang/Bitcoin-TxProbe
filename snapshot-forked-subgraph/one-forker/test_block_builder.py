"""Unit tests for offline double-spend transaction crafting and block builder."""

from __future__ import annotations

import io
from pathlib import Path
import sys
from unittest.mock import AsyncMock

# Add project root and module to path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
TEST_FRAMEWORK_DIR = PROJECT_ROOT / "test" / "functional"

for p in (TXPROBE_DIR, TEST_FRAMEWORK_DIR, CURRENT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest
from block_builder import (
    ConflictingTransactions,
    CraftedBlock,
    ForkPackage,
    craft_conflicting_transactions,
    craft_fork_blocks,
    solve_and_serialize_block,
)
from funding import ParentUtxo
from test_framework.blocktools import create_coinbase
from test_framework.messages import CBlock, CTransaction, COutPoint, CTxIn, CTxOut
from test_framework.script import CScript, OP_TRUE


def _create_dummy_tx(tx0_txid: str, tx0_vout: int, dest_sats: int, change_sats: int) -> str:
    """Helper to create a serialized raw transaction spending tx0 for testing."""
    tx = CTransaction()
    tx.vin.append(CTxIn(COutPoint(int(tx0_txid, 16), tx0_vout), CScript([b"\x00"]), 0xffffffff))
    tx.vout.append(CTxOut(dest_sats, CScript([OP_TRUE])))
    tx.vout.append(CTxOut(change_sats, CScript([OP_TRUE])))
    return tx.serialize().hex()


def test_models_serialization() -> None:
    """Verify dataclasses dictionary serialization."""
    tx0 = ParentUtxo(
        txid="0000000000000000000000000000000000000000000000000000000000000001",
        vout=0,
        amount_sats=100_000,
        address="bcrt1qforker",
        script_pub_key="0014mock",
    )
    conflicts = ConflictingTransactions(
        tx0=tx0,
        tx1_hex="01000000...",
        tx1_txid="tx1_id",
        tx1_dest_addr="bcrt1qrandom",
        tx2_hex="02000000...",
        tx2_txid="tx2_id",
        tx2_dest_addr="bcrt1qforker",
        dust_amount_sats=10_000,
        fee_sats=1_000,
    )
    d = conflicts.to_dict()
    assert d["tx1"]["dest_addr"] == "bcrt1qrandom"
    assert d["tx2"]["dest_addr"] == "bcrt1qforker"
    assert d["dust_amount_sats"] == 10_000


def test_craft_fork_blocks_offline_validity() -> None:
    """Verify offline block construction, linkage, PoW solving, and conflict inclusion."""
    parent_hash = "6b2a000000000000000000000000000000000000000000000000000000000001"
    parent_height = 100
    parent_time = 1700000000

    tx0 = ParentUtxo(
        txid="0000000000000000000000000000000000000000000000000000000000000001",
        vout=0,
        amount_sats=100_000,
        address="bcrt1qforker",
        script_pub_key="0014mock",
    )

    tx1_hex = _create_dummy_tx(tx0.txid, tx0.vout, 10_000, 89_000)
    tx2_hex = _create_dummy_tx(tx0.txid, tx0.vout, 10_000, 89_000)

    conflicts = ConflictingTransactions(
        tx0=tx0,
        tx1_hex=tx1_hex,
        tx1_txid="tx1_mock_id",
        tx1_dest_addr="bcrt1qrandom",
        tx2_hex=tx2_hex,
        tx2_txid="tx2_mock_id",
        tx2_dest_addr="bcrt1qforker",
        dust_amount_sats=10_000,
        fee_sats=1_000,
    )

    fork_pkg = craft_fork_blocks(
        parent_hash=parent_hash,
        parent_height=parent_height,
        parent_time=parent_time,
        conflicts=conflicts,
    )

    # 1. Height and linkage assertions
    assert fork_pkg.b1.height == 101
    assert fork_pkg.b2.height == 101
    assert fork_pkg.b3.height == 102

    assert fork_pkg.b1.prev_block_hash == parent_hash
    assert fork_pkg.b2.prev_block_hash == parent_hash
    assert fork_pkg.b3.prev_block_hash == fork_pkg.b2.block_hash

    # 2. Block hashes must be distinct
    assert fork_pkg.b1.block_hash != fork_pkg.b2.block_hash
    assert fork_pkg.b3.block_hash != fork_pkg.b2.block_hash

    # 3. Deserialization and PoW verification
    for b in (fork_pkg.b1, fork_pkg.b2, fork_pkg.b3):
        block_bytes = bytes.fromhex(b.block_hex)
        cblock = CBlock()
        cblock.deserialize(io.BytesIO(block_bytes))
        # Verify PoW target and merkle root
        assert cblock.is_valid()
        assert cblock.hash_hex == b.block_hash

    # 4. Verify transaction counts: B1 has 2 txs (coinbase + tx1), B2 has 2 txs (coinbase + tx2), B3 has 1 tx (coinbase)
    assert len(fork_pkg.b1.txids) == 2
    assert len(fork_pkg.b2.txids) == 2
    assert len(fork_pkg.b3.txids) == 1


@pytest.mark.asyncio
async def test_craft_conflicting_transactions_mock_rpc() -> None:
    """Verify craft_conflicting_transactions RPC orchestration and input reuse."""
    mock_rpc = AsyncMock()
    # Mock calls:
    # 1. getnewaddress forker_change -> "change_addr"
    # 2. getnewaddress forker_self_dest -> "self_addr"
    # 3. createrawtransaction tx1 -> "raw_tx1"
    # 4. signrawtransactionwithwallet raw_tx1 -> {"complete": True, "hex": tx1_hex}
    # 5. createrawtransaction tx2 -> "raw_tx2"
    # 6. signrawtransactionwithwallet raw_tx2 -> {"complete": True, "hex": tx2_hex}
    dummy_hex = _create_dummy_tx("0000000000000000000000000000000000000000000000000000000000000001", 0, 10_000, 89_000)

    mock_rpc.call.side_effect = [
        "bcrt1qchange",
        "bcrt1qself",
        "raw_tx1",
        {"complete": True, "hex": dummy_hex},
        "raw_tx2",
        {"complete": True, "hex": dummy_hex},
    ]

    tx0 = ParentUtxo(
        txid="0000000000000000000000000000000000000000000000000000000000000001",
        vout=0,
        amount_sats=100_000,
        address="bcrt1qforker",
        script_pub_key="0014mock",
    )

    conflicts = await craft_conflicting_transactions(
        rpc_wallet=mock_rpc,
        tx0=tx0,
        dust_sats=10_000,
        fee_sats=1_000,
        random_dest_addr="bcrt1qtarget",
    )

    assert conflicts.dust_amount_sats == 10_000
    assert conflicts.tx1_dest_addr == "bcrt1qtarget"
    assert conflicts.tx2_dest_addr == "bcrt1qself"
    assert conflicts.tx0.txid == tx0.txid
    assert conflicts.tx0.vout == tx0.vout
