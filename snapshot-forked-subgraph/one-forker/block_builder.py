"""Offline Double-Spend & Block Crafter for Fork Propagation Experiment.

Crafts conflicting transactions (tx1 and tx2) spending the same parent UTXO (tx0),
and constructs blocks B1, B2, and B3 offline without premature network broadcasting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import random
import sys
import time
from typing import Any

# Add project root and test_framework to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
TEST_FRAMEWORK_DIR = PROJECT_ROOT / "test" / "functional"

for p in (TXPROBE_DIR, TEST_FRAMEWORK_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from test_framework.blocktools import add_witness_commitment, create_block, create_coinbase
from test_framework.messages import CBlock, tx_from_hex

from txprobe.rpc.client import AsyncBitcoinRpc, RpcError

try:
    from .config import FORKER_NODE_ID, ExperimentConfig, get_node_config
    from .funding import FORKER_WALLET_NAME, ParentUtxo, make_rpc_client, sats_to_btc_str
except ImportError:
    from config import FORKER_NODE_ID, ExperimentConfig, get_node_config
    from funding import FORKER_WALLET_NAME, ParentUtxo, make_rpc_client, sats_to_btc_str

log = logging.getLogger("snapshot_fork.block_builder")


@dataclass(frozen=True)
class ConflictingTransactions:
    """Pair of conflicting double-spending transactions spending identical tx0 input."""
    tx0: ParentUtxo
    tx1_hex: str
    tx1_txid: str
    tx1_dest_addr: str
    tx2_hex: str
    tx2_txid: str
    tx2_dest_addr: str
    dust_amount_sats: int
    fee_sats: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx0": self.tx0.to_dict(),
            "tx1": {
                "txid": self.tx1_txid,
                "hex": self.tx1_hex,
                "dest_addr": self.tx1_dest_addr,
            },
            "tx2": {
                "txid": self.tx2_txid,
                "hex": self.tx2_hex,
                "dest_addr": self.tx2_dest_addr,
            },
            "dust_amount_sats": self.dust_amount_sats,
            "fee_sats": self.fee_sats,
        }


@dataclass(frozen=True)
class CraftedBlock:
    """Offline constructed and PoW-solved block."""
    label: str  # "B1", "B2", "B3"
    height: int
    block_hash: str
    prev_block_hash: str
    block_hex: str
    txids: list[str]
    time: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "height": self.height,
            "block_hash": self.block_hash,
            "prev_block_hash": self.prev_block_hash,
            "block_hex": self.block_hex,
            "txids": self.txids,
            "time": self.time,
        }


@dataclass(frozen=True)
class ForkPackage:
    """Complete bundle containing parent tip reference, conflicts, and blocks B1, B2, B3."""
    parent_hash: str
    parent_height: int
    conflicts: ConflictingTransactions
    b1: CraftedBlock
    b2: CraftedBlock
    b3: CraftedBlock
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_hash": self.parent_hash,
            "parent_height": self.parent_height,
            "conflicts": self.conflicts.to_dict(),
            "blocks": {
                "B1": self.b1.to_dict(),
                "B2": self.b2.to_dict(),
                "B3": self.b3.to_dict(),
            },
            "created_at": self.created_at,
        }


def solve_and_serialize_block(block: CBlock) -> tuple[str, str]:
    """Calculate witness commitment (if applicable), solve PoW, and return (hash_hex, block_hex)."""
    has_witness = any(
        getattr(tx, "wit", None) and not tx.wit.is_null()
        for tx in block.vtx[1:]
    )
    if has_witness:
        add_witness_commitment(block)
    else:
        block.hashMerkleRoot = block.calc_merkle_root()

    block.solve()
    return block.hash_hex, block.serialize().hex()


async def craft_conflicting_transactions(
    rpc_wallet: AsyncBitcoinRpc,
    tx0: ParentUtxo,
    dust_sats: int = 10_000,
    fee_sats: int = 1_000,
    random_dest_addr: str | None = None,
) -> ConflictingTransactions:
    """Craft and sign two mutually exclusive conflicting transactions spending tx0.

    tx1: Sends dust_sats to random_dest_addr, change back to Node 2.
    tx2: Sends dust_sats to Node 2 itself, change back to Node 2.
    """
    total_in = tx0.amount_sats
    if total_in < dust_sats + fee_sats:
        raise ValueError(
            f"Insufficient parent UTXO balance: {total_in} sats < dust ({dust_sats}) + fee ({fee_sats})"
        )

    change_sats = total_in - dust_sats - fee_sats
    dust_btc_str = sats_to_btc_str(dust_sats)
    change_btc_str = sats_to_btc_str(change_sats)

    # 1. Get Node 2 addresses for change and tx2 destination
    forker_change_addr: str = await rpc_wallet.call("getnewaddress", "forker_change")
    forker_dest_addr: str = await rpc_wallet.call("getnewaddress", "forker_self_dest")

    if random_dest_addr is None:
        # Generate dummy address or random node address
        random_dest_addr = await rpc_wallet.call("getnewaddress", "random_target")

    vin = [{"txid": tx0.txid, "vout": tx0.vout}]

    # 2. Build tx1 (to random node)
    vout_tx1 = {
        random_dest_addr: float(dust_btc_str),
        forker_change_addr: float(change_btc_str),
    }
    raw_tx1_hex: str = await rpc_wallet.call("createrawtransaction", vin, vout_tx1)
    signed_tx1: dict[str, Any] = await rpc_wallet.call("signrawtransactionwithwallet", raw_tx1_hex)
    if not signed_tx1.get("complete", False):
        raise RuntimeError(f"Failed to sign tx1: {signed_tx1}")
    tx1_hex = signed_tx1["hex"]
    tx1_txid = tx_from_hex(tx1_hex).txid_hex

    # 3. Build tx2 (back to Node 2 - the forker)
    vout_tx2 = {
        forker_dest_addr: float(dust_btc_str),
        forker_change_addr: float(change_btc_str),
    }
    raw_tx2_hex: str = await rpc_wallet.call("createrawtransaction", vin, vout_tx2)
    signed_tx2: dict[str, Any] = await rpc_wallet.call("signrawtransactionwithwallet", raw_tx2_hex)
    if not signed_tx2.get("complete", False):
        raise RuntimeError(f"Failed to sign tx2: {signed_tx2}")
    tx2_hex = signed_tx2["hex"]
    tx2_txid = tx_from_hex(tx2_hex).txid_hex

    log.info("Crafted conflicting transactions: tx1=%s, tx2=%s spending input %s:%d",
             tx1_txid, tx2_txid, tx0.txid, tx0.vout)

    return ConflictingTransactions(
        tx0=tx0,
        tx1_hex=tx1_hex,
        tx1_txid=tx1_txid,
        tx1_dest_addr=random_dest_addr,
        tx2_hex=tx2_hex,
        tx2_txid=tx2_txid,
        tx2_dest_addr=forker_dest_addr,
        dust_amount_sats=dust_sats,
        fee_sats=fee_sats,
    )


def craft_fork_blocks(
    parent_hash: str,
    parent_height: int,
    parent_time: int,
    conflicts: ConflictingTransactions,
) -> ForkPackage:
    """Construct blocks B1, B2, B3 offline and solve Proof-of-Work without publishing.

    Topology:
        Parent (height H)
           ├── B1 (height H+1, contains tx1)
           └── B2 (height H+1, contains tx2) ──> B3 (height H+2, empty extension)
    """
    log.info("Crafting fork blocks off parent %s (height %d)...", parent_hash, parent_height)
    parent_hash_int = int(parent_hash, 16)
    target_height_fork = parent_height + 1
    target_height_ext = parent_height + 2
    base_time = max(parent_time + 1, int(time.time()))

    # Parse CTransaction objects
    tx1_obj = tx_from_hex(conflicts.tx1_hex)
    tx2_obj = tx_from_hex(conflicts.tx2_hex)

    # 1. Block B1 (contains tx1)
    cb1 = create_coinbase(height=target_height_fork)
    block_b1 = create_block(
        hashprev=parent_hash_int,
        coinbase=cb1,
        ntime=base_time,
        txlist=[tx1_obj],
    )
    b1_hash, b1_hex = solve_and_serialize_block(block_b1)
    b1 = CraftedBlock(
        label="B1",
        height=target_height_fork,
        block_hash=b1_hash,
        prev_block_hash=parent_hash,
        block_hex=b1_hex,
        txids=[cb1.txid_hex, conflicts.tx1_txid],
        time=base_time,
    )
    log.info("Crafted and solved Block B1: %s (height %d)", b1_hash, target_height_fork)

    # 2. Block B2 (contains tx2, competing at same height target_height_fork)
    cb2 = create_coinbase(height=target_height_fork)
    block_b2 = create_block(
        hashprev=parent_hash_int,
        coinbase=cb2,
        ntime=base_time + 1,
        txlist=[tx2_obj],
    )
    b2_hash, b2_hex = solve_and_serialize_block(block_b2)
    b2 = CraftedBlock(
        label="B2",
        height=target_height_fork,
        block_hash=b2_hash,
        prev_block_hash=parent_hash,
        block_hex=b2_hex,
        txids=[cb2.txid_hex, conflicts.tx2_txid],
        time=base_time + 1,
    )
    log.info("Crafted and solved Block B2: %s (height %d)", b2_hash, target_height_fork)

    # 3. Block B3 (extends B2 at height target_height_ext)
    b2_hash_int = block_b2.hash_int
    cb3 = create_coinbase(height=target_height_ext)
    block_b3 = create_block(
        hashprev=b2_hash_int,
        coinbase=cb3,
        ntime=base_time + 2,
        txlist=[],
    )
    b3_hash, b3_hex = solve_and_serialize_block(block_b3)
    b3 = CraftedBlock(
        label="B3",
        height=target_height_ext,
        block_hash=b3_hash,
        prev_block_hash=b2_hash,
        block_hex=b3_hex,
        txids=[cb3.txid_hex],
        time=base_time + 2,
    )
    log.info("Crafted and solved Block B3: %s (height %d, extending B2)", b3_hash, target_height_ext)

    return ForkPackage(
        parent_hash=parent_hash,
        parent_height=parent_height,
        conflicts=conflicts,
        b1=b1,
        b2=b2,
        b3=b3,
    )


async def build_fork_package(
    forker_id: int = FORKER_NODE_ID,
    tx0: ParentUtxo | None = None,
    config: ExperimentConfig | None = None,
) -> ForkPackage:
    """High-level async orchestrator to prepare the complete offline ForkPackage for Node 2."""
    if config is None:
        config = ExperimentConfig()

    async with make_rpc_client(forker_id, wallet=FORKER_WALLET_NAME) as rpc_wallet:
        if tx0 is None:
            from .funding import fund_forker_node
            tx0 = await fund_forker_node(
                forker_id=forker_id,
                target_amount_sats=config.funding_target_sats,
            )

        # 1. Fetch current tip metadata
        parent_hash: str = await rpc_wallet.call("getbestblockhash")
        parent_height: int = await rpc_wallet.call("getblockcount")
        parent_block: dict[str, Any] = await rpc_wallet.call("getblock", parent_hash)
        parent_time: int = parent_block["time"]

        # 2. Pick a random target node address for tx1
        random_node_id = random.choice(list(range(3, 3 + min(config.num_target_nodes - 1, 999))))
        async with make_rpc_client(random_node_id) as rpc_random:
            try:
                random_dest_addr: str = await rpc_random.call("getnewaddress", "target_dust")
            except Exception:
                random_dest_addr = await rpc_wallet.call("getnewaddress", "target_dust_fallback")

        # 3. Craft conflicting transactions
        conflicts = await craft_conflicting_transactions(
            rpc_wallet=rpc_wallet,
            tx0=tx0,
            dust_sats=config.dust_amount_sats,
            fee_sats=config.fee_sats,
            random_dest_addr=random_dest_addr,
        )

        # 4. Construct offline blocks
        return craft_fork_blocks(
            parent_hash=parent_hash,
            parent_height=parent_height,
            parent_time=parent_time,
            conflicts=conflicts,
        )
