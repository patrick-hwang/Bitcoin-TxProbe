"""Unit tests for Step 3: Matrix Partitioning, UTXO Splitting & Raw Transaction Crafting."""

from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from txprobe.config import TxCraftingConfig
from txprobe.models.graph import GraphSnapshot
from txprobe.models.node import NodeIdentity
from txprobe.models.transaction import (
    MatrixRound,
    TxMessage,
    TxProbeCraftingResult,
    UtxoInfo,
)
from txprobe.transactions import (
    btc_to_sats,
    calculate_split_outputs,
    compute_matrix_dimensions,
    craft_all_rounds,
    craft_conflicting_transactions,
    craft_marker_transactions,
    derive_recipient_addresses,
    ensure_wallet_loaded,
    estimate_split_tx_vsize,
    generate_matrix_rounds,
    prepare_utxos_for_rounds,
    sats_to_btc_str,
    split_single_utxo,
)


def _make_fake_rpc_for_crafting() -> AsyncMock:
    """Create a mock AsyncBitcoinRpc that deterministically handles raw tx batch calls."""
    rpc = AsyncMock()
    rpc.listwallets.return_value = ["mywallet"]
    rpc.listdescriptors.return_value = {
        "descriptors": [
            {
                "desc": "wpkh([12345678/84h/1h/0h]tpubD6NzVbkrYhZ4X.../1/*)#abcdef12",
                "active": True,
                "internal": True,
            }
        ]
    }

    async def _deriveaddresses(desc: str, range_spec: list[int]) -> list[str]:
        start, end = range_spec[0], range_spec[1]
        return [f"tb1qaddr{i:04d}xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" for i in range(start, end + 1)]

    rpc.deriveaddresses.side_effect = _deriveaddresses

    async def _call_batch(calls: list[tuple[Any, ...]], *, raise_on_error: bool = True) -> list[Any]:
        results: list[Any] = []
        for call in calls:
            method = call[0]
            if method == "createrawtransaction":
                inputs, outputs = call[1], call[2]
                in_txid = inputs[0]["txid"]
                in_vout = inputs[0]["vout"]
                out_addr = list(outputs[0].keys())[0]
                out_amt = list(outputs[0].values())[0]
                raw_tag = f"unsigned:{in_txid}:{in_vout}:{out_addr}:{out_amt}"
                results.append(raw_tag.encode().hex())
            elif method == "signrawtransactionwithwallet":
                raw_hex = call[1]
                signed_hex = "signed_" + raw_hex
                results.append({"hex": signed_hex, "complete": True})
            elif method == "decoderawtransaction":
                signed_hex = call[1]
                raw_hex = signed_hex.removeprefix("signed_")
                decoded_str = bytes.fromhex(raw_hex).decode()
                # Format: unsigned:<in_txid>:<in_vout>:<out_addr>:<out_amt>
                parts = decoded_str.split(":")
                out_addr = parts[3]
                out_amt = parts[4]
                txid = hashlib.sha256(signed_hex.encode()).hexdigest()
                wtxid = hashlib.sha256((signed_hex + ":w").encode()).hexdigest()
                spk_hex = "0014" + hashlib.sha256(out_addr.encode()).hexdigest()[:40]
                results.append(
                    {
                        "txid": txid,
                        "hash": wtxid,
                        "vout": [
                            {
                                "n": 0,
                                "value": float(out_amt),
                                "scriptPubKey": {"hex": spk_hex},
                            }
                        ],
                    }
                )
            elif method == "getnewaddress":
                idx = len(results)
                results.append(f"tb1qfallback{idx:04d}xxxxxxxxxxxxxxxxxxxxxxxxxx")
        return results

    rpc.call_batch.side_effect = _call_batch
    return rpc


def test_sats_and_btc_conversions() -> None:
    assert sats_to_btc_str(0) == "0.00000000"
    assert sats_to_btc_str(2000) == "0.00002000"
    assert sats_to_btc_str(500) == "0.00000500"
    assert sats_to_btc_str(100_000_000) == "1.00000000"
    assert sats_to_btc_str(123_456_789) == "1.23456789"

    with pytest.raises(ValueError, match="cannot be negative"):
        sats_to_btc_str(-1)

    assert btc_to_sats("0.00002000") == 2000
    assert btc_to_sats(0.00002) == 2000
    assert btc_to_sats(Decimal("0.01000000")) == 1_000_000
    assert btc_to_sats(1) == 100_000_000


def test_compute_matrix_dimensions() -> None:
    # 1000 nodes -> ceil(sqrt(1000)) = 32 -> w = 32, h = 32
    assert compute_matrix_dimensions(1000, max_source_size=75) == (32, 32)
    # 2 nodes -> w = 2, h = 1
    assert compute_matrix_dimensions(2, max_source_size=75) == (2, 1)
    # 10 nodes -> ceil(sqrt(10)) = 4 -> w = 4, h = 3
    assert compute_matrix_dimensions(10, max_source_size=75) == (4, 3)
    # Large network exceeding max_source_size**2: 10000 nodes -> w = 75, h = 134
    assert compute_matrix_dimensions(10000, max_source_size=75) == (75, 134)

    with pytest.raises(ValueError, match="At least 2 nodes"):
        compute_matrix_dimensions(1)
    with pytest.raises(ValueError, match="max_source_size must be >= 1"):
        compute_matrix_dimensions(10, max_source_size=0)


def test_generate_matrix_rounds_pairwise_separation() -> None:
    # Case 1: w >= h (10 nodes -> w=4, h=3 -> w+h-2 = 5 rounds)
    nodes_10 = [NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(10)]
    rounds_10 = generate_matrix_rounds(nodes_10, max_source_size=75)
    assert len(rounds_10) == 5

    # Check every pair of distinct nodes is separated into (source, sink) in at least 1 round
    for i in range(len(nodes_10)):
        for j in range(i + 1, len(nodes_10)):
            u, v = nodes_10[i], nodes_10[j]
            separated = any(
                (u in r.source_nodes and v in r.sink_nodes)
                or (v in r.source_nodes and u in r.sink_nodes)
                for r in rounds_10
            )
            assert separated, f"Pair ({u}, {v}) was never separated!"

    # Case 2: w < h (14 nodes with max_source_size=3 -> w=3, h=5)
    nodes_14 = [NodeIdentity(addr=f"10.0.1.{i}:48333") for i in range(14)]
    rounds_14 = generate_matrix_rounds(nodes_14, max_source_size=3)
    for r in rounds_14:
        assert r.num_sources <= 3
        assert set(r.source_nodes).isdisjoint(set(r.sink_nodes))
        assert len(r.source_nodes) + len(r.sink_nodes) == 14

    for i in range(len(nodes_14)):
        for j in range(i + 1, len(nodes_14)):
            u, v = nodes_14[i], nodes_14[j]
            separated = any(
                (u in r.source_nodes and v in r.sink_nodes)
                or (v in r.source_nodes and u in r.sink_nodes)
                for r in rounds_14
            )
            assert separated, f"Pair ({u}, {v}) was never separated in w < h mode!"


def test_calculate_split_outputs() -> None:
    # Too small to split into 2 x 2000 sats
    assert calculate_split_outputs(3500, target_sats=2000, fee_rate_sat_vb=2) == []

    # Enough for 2 outputs: input = 4500 sats, fee_rate = 2 sat/vB
    # vsize(1, 2) = 11 + 68 + 62 = 141 vB -> fee = 282 sats
    # Output 0 = 2000 sats, Output 1 = 4500 - 282 - 2000 = 2218 sats
    outs_2 = calculate_split_outputs(4500, target_sats=2000, fee_rate_sat_vb=2)
    assert outs_2 == [2000, 2218]
    assert sum(outs_2) + estimate_split_tx_vsize(1, 2) * 2 == 4500

    # Large UTXO capped at max_outputs = 100
    outs_capped = calculate_split_outputs(
        1_000_000, target_sats=2000, fee_rate_sat_vb=2, max_outputs=100
    )
    assert len(outs_capped) == 100
    assert all(x == 2000 for x in outs_capped[:-1])
    assert outs_capped[-1] > 2000
    assert sum(outs_capped) + estimate_split_tx_vsize(1, 100) * 2 == 1_000_000

    # Edge validation errors
    with pytest.raises(ValueError, match="below P2WPKH dust"):
        calculate_split_outputs(10000, target_sats=100)
    with pytest.raises(ValueError, match="max_outputs must be in"):
        calculate_split_outputs(10000, max_outputs=1001)


@pytest.mark.asyncio
async def test_ensure_wallet_loaded() -> None:
    rpc = AsyncMock()
    rpc.listwallets.return_value = ["mywallet"]
    await ensure_wallet_loaded(rpc, "mywallet")
    rpc.loadwallet.assert_not_called()

    rpc.listwallets.return_value = ["otherwallet"]
    await ensure_wallet_loaded(rpc, "mywallet")
    rpc.loadwallet.assert_called_once_with("mywallet")


@pytest.mark.asyncio
async def test_derive_recipient_addresses_and_fallback() -> None:
    rpc = _make_fake_rpc_for_crafting()
    addrs = await derive_recipient_addresses(rpc, count=4, start_index=0)
    assert len(addrs) == 4
    assert len(set(addrs)) == 4

    # Test keypool lookahead limit protection
    with pytest.raises(ValueError, match="exceeds wallet keypool lookahead limit"):
        await derive_recipient_addresses(rpc, count=1001, start_index=0)

    # Test fallback to getnewaddress when listdescriptors fails
    rpc.listdescriptors.side_effect = RuntimeError("descriptor RPC disabled")
    fallback_addrs = await derive_recipient_addresses(rpc, count=3, start_index=0)
    assert len(fallback_addrs) == 3


@pytest.mark.asyncio
async def test_split_single_utxo() -> None:
    rpc = _make_fake_rpc_for_crafting()
    rpc.createrawtransaction.return_value = "01000000rawsplit"
    rpc.signrawtransactionwithwallet.return_value = {
        "hex": "01000000signedsplit",
        "complete": True,
    }
    rpc.sendrawtransaction.return_value = "a" * 64

    big_utxo = UtxoInfo(txid="b" * 64, vout=1, amount_sats=10_000, confirmations=3)
    split_txid = await split_single_utxo(
        rpc, big_utxo, target_sats=2000, fee_rate_sat_vb=2
    )
    assert split_txid == "a" * 64

    # Verify len(vin) == 1
    args, _ = rpc.createrawtransaction.call_args
    assert len(args[0]) == 1
    assert args[0][0] == {"txid": "b" * 64, "vout": 1}
    # 10,000 sats splits into 4 outputs
    assert len(args[1]) == 4

    # Small UTXO returns None without broadcasting
    small_utxo = UtxoInfo(txid="c" * 64, vout=0, amount_sats=2500, confirmations=1)
    assert await split_single_utxo(rpc, small_utxo, target_sats=2000) is None


@pytest.mark.asyncio
async def test_prepare_utxos_fast_path_sorts_smallest_first() -> None:
    rpc = _make_fake_rpc_for_crafting()
    # Wallet already has 3 small UTXOs (2000, 2100, 2000 sats) and 1 big remainder UTXO (500,000 sats)
    rpc.listunspent.return_value = [
        {"txid": "tx_big", "vout": 0, "amount": "0.00500000", "confirmations": 5, "spendable": True},
        {"txid": "tx_2", "vout": 0, "amount": "0.00002100", "confirmations": 2, "spendable": True},
        {"txid": "tx_1", "vout": 0, "amount": "0.00002000", "confirmations": 2, "spendable": True},
        {"txid": "tx_3", "vout": 0, "amount": "0.00002000", "confirmations": 2, "spendable": True},
    ]

    utxos, split_txids = await prepare_utxos_for_rounds(rpc, num_rounds=3)
    assert split_txids == []
    assert [u.amount_sats for u in utxos] == [2000, 2000, 2100]
    assert "tx_big" not in [u.txid for u in utxos]


@pytest.mark.asyncio
async def test_prepare_utxos_auto_split_and_mempool_wait() -> None:
    rpc = _make_fake_rpc_for_crafting()
    rpc.createrawtransaction.return_value = "raw_split_hex"
    rpc.signrawtransactionwithwallet.return_value = {"hex": "signed_split_hex", "complete": True}
    rpc.sendrawtransaction.return_value = "split_tx_01"

    # Poll 1: Only 1 large confirmed UTXO (10,000 sats) -> triggers split into 4 outputs
    # Poll 2: 4 unconfirmed outputs in mempool (confirmations=0) -> waits without re-splitting or prompting funding
    # Poll 3: 4 confirmed outputs (confirmations=1) -> returns 3 smallest UTXOs
    rpc.listunspent.side_effect = [
        [
            {"txid": "parent_big", "vout": 0, "amount": "0.00010000", "confirmations": 6, "spendable": True},
        ],
        [
            {"txid": "split_tx_01", "vout": i, "amount": "0.00002000", "confirmations": 0, "spendable": True}
            for i in range(4)
        ],
        [
            {"txid": "split_tx_01", "vout": i, "amount": "0.00002000", "confirmations": 1, "spendable": True}
            for i in range(4)
        ],
    ]

    funding_called = False

    def _on_funding(addr: str, cur: int, needed: int) -> None:
        nonlocal funding_called
        funding_called = True

    cfg = TxCraftingConfig(
        utxo_target_sats=2000,
        poll_interval_sec=0.01,
        block_propagation_wait_sec=0.01,
    )
    utxos, split_txids = await prepare_utxos_for_rounds(
        rpc,
        num_rounds=3,
        config=cfg,
        funding_callback=_on_funding,
    )

    assert not funding_called
    assert split_txids == ["split_tx_01"]
    assert len(utxos) == 3
    assert all(u.amount_sats == 2000 for u in utxos)


@pytest.mark.asyncio
async def test_prepare_utxos_prompts_funding_and_times_out() -> None:
    rpc = _make_fake_rpc_for_crafting()
    rpc.listunspent.return_value = []
    rpc.getnewaddress.return_value = "tb1qdepositaddress12345"

    prompts: list[tuple[str, int, int]] = []
    cfg = TxCraftingConfig(poll_interval_sec=0.01, block_propagation_wait_sec=0.0)

    with pytest.raises(TimeoutError, match="Timed out waiting for 2 confirmed UTXOs"):
        await prepare_utxos_for_rounds(
            rpc,
            num_rounds=2,
            config=cfg,
            max_wait_polls=1,
            funding_callback=lambda addr, cur, need: prompts.append((addr, cur, need)),
        )

    assert len(prompts) == 2
    assert prompts[0] == ("tb1qdepositaddress12345", 0, 2)


@pytest.mark.asyncio
async def test_craft_conflicting_and_marker_transactions() -> None:
    rpc = _make_fake_rpc_for_crafting()
    utxo = UtxoInfo(txid="1" * 64, vout=0, amount_sats=2000, confirmations=1)

    parents, flood, p_decoded = await craft_conflicting_transactions(
        rpc, utxo, num_parents=3, fee_sats=500
    )
    assert len(parents) == 3
    all_txids = {p.txid for p in parents} | {flood.txid}
    assert len(all_txids) == 4  # All 4 conflicting txs have unique txids

    markers = await craft_marker_transactions(
        rpc,
        parent_txs=parents,
        parent_decoded=p_decoded,
        parent_output_sats=1500,
        fee_sats=500,
    )
    assert len(markers) == 3
    assert len({m.txid for m in markers}) == 3

    # Dust error check
    tiny_utxo = UtxoInfo(txid="2" * 64, vout=0, amount_sats=600, confirmations=1)
    with pytest.raises(ValueError, match="below dust"):
        await craft_conflicting_transactions(rpc, tiny_utxo, num_parents=2, fee_sats=500)


@pytest.mark.asyncio
async def test_craft_all_rounds_and_serialization_roundtrip(tmp_path: Path) -> None:
    rpc = _make_fake_rpc_for_crafting()
    # 6 nodes -> w=3, h=2 -> w+h-2 = 3 rounds
    nodes = tuple(NodeIdentity(addr=f"192.168.1.{i}:48333") for i in range(1, 7))
    snapshot = GraphSnapshot(
        nodes=nodes,
        adj_list={n: () for n in nodes},
    )

    rpc.listunspent.return_value = [
        {"txid": f"utxo_{i:02d}", "vout": 0, "amount": "0.00002000", "confirmations": 3, "spendable": True}
        for i in range(5)
    ]

    cfg = TxCraftingConfig(
        utxo_target_sats=2000,
        parent_fee_sats=500,
        marker_fee_sats=500,
        poll_interval_sec=0.01,
        block_propagation_wait_sec=0.0,
    )

    result = await craft_all_rounds(
        snapshot=snapshot,
        rpc=rpc,
        config=cfg,
        wallet_name="mywallet",
    )

    assert result.stats.total_nodes == 6
    assert result.stats.matrix_width == 3
    assert result.stats.matrix_height == 2
    assert result.stats.total_rounds == 3
    assert len(result.rounds) == 3

    # Check that each round uses a distinct UTXO
    used_utxos = {r.utxo.outpoint for r in result.rounds}
    assert len(used_utxos) == 3

    for r in result.rounds:
        assert len(r.parent_txs) == len(r.source_nodes)
        assert len(r.marker_txs) == len(r.source_nodes)

    # Save and load roundtrip
    out_file = tmp_path / "crafted_rounds.json"
    result.save(out_file)
    loaded = TxProbeCraftingResult.load(out_file)

    assert loaded.stats == result.stats
    assert loaded.snapshot.nodes == result.snapshot.nodes
    assert len(loaded.rounds) == len(result.rounds)
    for r_orig, r_load in zip(result.rounds, loaded.rounds):
        assert r_orig == r_load
