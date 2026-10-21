"""Unit tests for funding engine and UTXO management."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

# Add project root and module to path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
sys.path.insert(0, str(TXPROBE_DIR))
sys.path.insert(0, str(CURRENT_DIR))

import pytest
from funding import (
    DEFAULT_TARGET_SATS,
    FORKER_WALLET_NAME,
    ParentUtxo,
    btc_to_sats,
    ensure_wallet_loaded,
    find_spendable_utxo,
    fund_forker_node,
    sats_to_btc_str,
)


def test_sats_and_btc_conversions() -> None:
    """Verify precision of satoshi and BTC string conversions."""
    assert sats_to_btc_str(100_000_000) == "1.00000000"
    assert sats_to_btc_str(10_000) == "0.00010000"
    assert sats_to_btc_str(546) == "0.00000546"
    assert sats_to_btc_str(0) == "0.00000000"

    with pytest.raises(ValueError):
        sats_to_btc_str(-1)

    assert btc_to_sats("1.00000000") == 100_000_000
    assert btc_to_sats(Decimal("0.00010000")) == 10_000
    assert btc_to_sats(0.00000546) == 546


def test_parent_utxo_dataclass() -> None:
    """Verify ParentUtxo model serialization."""
    utxo = ParentUtxo(
        txid="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        vout=0,
        amount_sats=100_000_000,
        address="bcrt1qmockaddress",
        script_pub_key="0014mockscript",
    )
    d = utxo.to_dict()
    assert d["txid"].startswith("abcdef")
    assert d["vout"] == 0
    assert d["amount_sats"] == 100_000_000
    assert d["address"] == "bcrt1qmockaddress"


@pytest.mark.asyncio
async def test_ensure_wallet_loaded_already_loaded() -> None:
    """Verify ensure_wallet_loaded when wallet is already active."""
    mock_rpc = AsyncMock()
    mock_rpc.call.return_value = ["forker_wallet", "default"]

    await ensure_wallet_loaded(mock_rpc, "forker_wallet")
    mock_rpc.call.assert_called_once_with("listwallets")


@pytest.mark.asyncio
async def test_ensure_wallet_loaded_load_existing() -> None:
    """Verify loading an existing unloaded wallet from wallet directory."""
    mock_rpc = AsyncMock()
    # listwallets returns other wallet
    # listwalletdir returns forker_wallet
    mock_rpc.call.side_effect = [
        ["other_wallet"],
        {"wallets": [{"name": "forker_wallet"}]},
        {"name": "forker_wallet"},  # loadwallet
    ]

    await ensure_wallet_loaded(mock_rpc, "forker_wallet")
    assert mock_rpc.call.call_count == 3
    mock_rpc.call.assert_any_call("loadwallet", "forker_wallet")


@pytest.mark.asyncio
async def test_ensure_wallet_loaded_create_new() -> None:
    """Verify creating a new wallet if not in listwallets or listwalletdir."""
    mock_rpc = AsyncMock()
    mock_rpc.call.side_effect = [
        [],
        {"wallets": []},
        {"name": "forker_wallet"},  # createwallet
    ]

    await ensure_wallet_loaded(mock_rpc, "forker_wallet")
    assert mock_rpc.call.call_count == 3
    mock_rpc.call.assert_any_call("createwallet", "forker_wallet")


@pytest.mark.asyncio
async def test_find_spendable_utxo_filtering() -> None:
    """Verify filtering and sorting of UTXOs by spendable status and amount."""
    mock_rpc = AsyncMock()
    mock_rpc.call.return_value = [
        # UTXO 1: unspendable watch-only
        {"txid": "tx1", "vout": 0, "amount": 2.0, "spendable": False, "address": "addr1", "scriptPubKey": "spk1"},
        # UTXO 2: spendable, small
        {"txid": "tx2", "vout": 1, "amount": 0.1, "spendable": True, "address": "addr2", "scriptPubKey": "spk2"},
        # UTXO 3: spendable, large (target)
        {"txid": "tx3", "vout": 0, "amount": 1.5, "spendable": True, "address": "addr3", "scriptPubKey": "spk3"},
    ]

    # Target: >= 1.0 BTC (100_000_000 sats)
    utxo = await find_spendable_utxo(mock_rpc, min_amount_sats=100_000_000)
    assert utxo is not None
    assert utxo.txid == "tx3"
    assert utxo.amount_sats == 150_000_000

    # Target: >= 3.0 BTC (too high, none match)
    none_utxo = await find_spendable_utxo(mock_rpc, min_amount_sats=300_000_000)
    assert none_utxo is None


@pytest.mark.asyncio
async def test_fund_forker_node_existing_utxo() -> None:
    """Verify fund_forker_node fast-path when Node 2 already has UTXOs."""
    mock_existing = ParentUtxo(
        txid="tx_existing",
        vout=0,
        amount_sats=100_000_000,
        address="addr_existing",
        script_pub_key="spk_existing",
    )

    with patch("funding.make_rpc_client") as mock_make_rpc, \
         patch("funding.ensure_wallet_loaded", new_callable=AsyncMock), \
         patch("funding.find_spendable_utxo", new_callable=AsyncMock, return_value=mock_existing):

        mock_client = AsyncMock()
        mock_make_rpc.return_value.__aenter__.return_value = mock_client

        utxo = await fund_forker_node(forker_id=2, target_amount_sats=100_000_000)
        assert utxo == mock_existing
        assert utxo.txid == "tx_existing"
