"""Tests for Step 2 INVBLOCK Pre-filtering."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from txprobe.invblock import (
    InvblockResult,
    InvblockStats,
    clear_log_file,
    craft_dummy_test_transaction,
    craft_test_transaction,
    disconnect_peers_parallel,
    parse_getdata_peers_from_log,
    run_invblock_prefilter,
)
from txprobe.models.graph import GraphSnapshot
from txprobe.models.node import NodeIdentity
from txprobe.models.transaction import TxMessage


def test_craft_dummy_test_transaction():
    """craft_dummy_test_transaction returns a valid TxMessage with unique hashes."""
    tx1 = craft_dummy_test_transaction(nonce_seed="seed1")
    tx2 = craft_dummy_test_transaction(nonce_seed="seed2")

    assert len(tx1.txid) == 64
    assert len(tx1.wtxid) == 64
    assert len(tx1.hexstr) > 0
    # Different seeds produce different transactions
    assert tx1.txid != tx2.txid


@pytest.mark.asyncio
async def test_craft_test_transaction_fallback_on_rpc_error():
    """craft_test_transaction falls back to dummy crafting if RPC fails."""
    mock_rpc = AsyncMock()
    mock_rpc.createrawtransaction.side_effect = RuntimeError("RPC error")

    tx = await craft_test_transaction(mock_rpc, nonce_seed="test_fallback")
    assert len(tx.txid) == 64
    assert len(tx.hexstr) > 0


def test_parse_getdata_peers_from_log(tmp_path: Path):
    """parse_getdata_peers_from_log correctly extracts addresses from both log patterns."""
    log_content = (
        # Matching BLOCKED_NOTFOUND line
        "[1000] BLOCKED_NOTFOUND peer=10 addr=1.2.3.4:48333 type=wtx hash=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        # Non-matching hash BLOCKED_NOTFOUND
        "[1001] BLOCKED_NOTFOUND peer=11 addr=5.6.7.8:48333 type=wtx hash=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        # Matching received getdata line
        "[1002] received getdata for: wtx aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa peer=20\n"
        # Non-matching hash received getdata
        "[1003] received getdata for: tx cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc peer=30\n"
        # Malformed line
        "[1004] Random irrelevant log entry\n"
    )
    log_file = tmp_path / "test_txprobe.log"
    log_file.write_text(log_content, encoding="utf-8")

    target_hashes = {"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
    peer_id_to_addr = {20: "9.10.11.12:48333", 30: "13.14.15.16:48333"}

    matched = parse_getdata_peers_from_log(log_file, target_hashes, peer_id_to_addr)
    assert matched == {"1.2.3.4:48333", "9.10.11.12:48333"}


def test_parse_getdata_peers_missing_log():
    """parse_getdata_peers_from_log returns empty set when file does not exist."""
    res = parse_getdata_peers_from_log("non_existent_file.log", {"aaa"})
    assert res == set()


def test_clear_log_file(tmp_path: Path):
    """clear_log_file empties existing file without error and handles missing files gracefully."""
    log_file = tmp_path / "test.log"
    log_file.write_text("historical log line 1\nhistorical log line 2\n", encoding="utf-8")
    assert len(log_file.read_text(encoding="utf-8")) > 0

    clear_log_file(log_file)
    assert log_file.read_text(encoding="utf-8") == ""

    # Should not raise on non-existent file
    clear_log_file(tmp_path / "does_not_exist.log")


def test_graph_snapshot_prune_and_remove_nodes():
    """GraphSnapshot prune_nodes and remove_nodes keep only relevant nodes and incident edges."""
    n1 = NodeIdentity("1.1.1.1:48333")
    n2 = NodeIdentity("2.2.2.2:48333")
    n3 = NodeIdentity("3.3.3.3:48333")

    initial = GraphSnapshot(
        nodes=(n1, n2, n3),
        adj_list=MappingProxyType({
            n1: (n2, n3),
            n2: (n1,),
            n3: (n1,),
        }),
    )
    assert initial.num_nodes == 3
    assert initial.num_edges == 2

    pruned = initial.prune_nodes([n1, n2])
    assert pruned.num_nodes == 2
    assert pruned.num_edges == 1
    assert pruned.adj_list[n1] == (n2,)
    assert pruned.adj_list[n2] == (n1,)

    removed = initial.remove_nodes([n3])
    assert removed.nodes == pruned.nodes
    assert removed.num_edges == 1


@pytest.mark.asyncio
async def test_disconnect_peers_parallel():
    """disconnect_peers_parallel calls disconnectnode and addnode remove on rpc."""
    mock_rpc = AsyncMock()
    addrs = ["1.1.1.1:48333", "2.2.2.2:48333"]

    await disconnect_peers_parallel(mock_rpc, addrs, concurrency=2)

    assert mock_rpc.disconnectnode.call_count == 2
    assert mock_rpc.addnode.call_count == 2


@pytest.mark.asyncio
async def test_run_invblock_prefilter_dual_condition(tmp_path: Path):
    """run_invblock_prefilter properly applies the dual-condition filter:
    - Node A (Good): responds to Probe 0, does not respond to Probe 1 -> KEPT
    - Node B (IBD/non-responsive): does not respond to Probe 0 -> ELIMINATED
    - Node C (Violating): responds to Probe 0 and Probe 1 -> ELIMINATED
    - Node D (Dropped): disconnected from Probe 1 -> ELIMINATED
    """
    node_a = NodeIdentity("10.0.0.1:48333")
    node_b = NodeIdentity("10.0.0.2:48333")
    node_c = NodeIdentity("10.0.0.3:48333")
    node_d = NodeIdentity("10.0.0.4:48333")

    initial_graph = GraphSnapshot(
        nodes=(node_a, node_b, node_c, node_d),
        adj_list=MappingProxyType({
            node_a: (node_b, node_c),
            node_b: (node_a,),
            node_c: (node_a,),
            node_d: (),
        }),
    )

    test_tx = TxMessage(
        hexstr="01000000010000000000",
        txid="1111111111111111111111111111111111111111111111111111111111111111",
        wtxid="1111111111111111111111111111111111111111111111111111111111111111",
    )

    # Peer list on Probe 0: A(id=1), B(id=2), C(id=3), D(id=4)
    p0_peers = [
        {"id": 1, "addr": node_a.addr, "connection_type": "outbound-full-relay"},
        {"id": 2, "addr": node_b.addr, "connection_type": "outbound-full-relay"},
        {"id": 3, "addr": node_c.addr, "connection_type": "outbound-full-relay"},
        {"id": 4, "addr": node_d.addr, "connection_type": "outbound-full-relay"},
    ]

    # Peer list on Probe 1: A(id=11), B(id=12), C(id=13) (D dropped)
    p1_peers = [
        {"id": 11, "addr": node_a.addr, "connection_type": "outbound-full-relay"},
        {"id": 12, "addr": node_b.addr, "connection_type": "outbound-full-relay"},
        {"id": 13, "addr": node_c.addr, "connection_type": "outbound-full-relay"},
    ]

    mock_p0 = AsyncMock()
    mock_p0.getpeerinfo.return_value = p0_peers
    mock_p0.sendinv_orphan = AsyncMock()
    mock_p0.disconnectnode = AsyncMock()
    mock_p0.addnode = AsyncMock()
    mock_p0.clearinv_probe = AsyncMock(return_value={"success": True})

    mock_p1 = AsyncMock()
    mock_p1.getpeerinfo.return_value = p1_peers
    mock_p1.sendinv_orphan = AsyncMock()
    mock_p1.disconnectnode = AsyncMock()
    mock_p1.addnode = AsyncMock()
    mock_p1.clearinv_probe = AsyncMock(return_value={"success": True})

    # Log files: pre-fill with old junk to verify that clear_logs=True clears them first
    p0_log = tmp_path / "txprobe_0.log"
    p1_log = tmp_path / "txprobe_1.log"
    p0_log.write_text("old historical junk line\n", encoding="utf-8")
    p1_log.write_text("old historical junk line\n", encoding="utf-8")

    async def _p0_sendinv(*args, **kwargs):
        p0_log.write_text(
            f"[100] BLOCKED_NOTFOUND peer=1 addr={node_a.addr} type=wtx hash={test_tx.txid}\n"
            f"[101] BLOCKED_NOTFOUND peer=3 addr={node_c.addr} type=wtx hash={test_tx.txid}\n",
            encoding="utf-8",
        )

    async def _p1_sendinv(*args, **kwargs):
        p1_log.write_text(
            f"[200] BLOCKED_NOTFOUND peer=13 addr={node_c.addr} type=wtx hash={test_tx.txid}\n",
            encoding="utf-8",
        )

    mock_p0.sendinv_orphan = AsyncMock(side_effect=_p0_sendinv)
    mock_p1.sendinv_orphan = AsyncMock(side_effect=_p1_sendinv)

    res = await run_invblock_prefilter(
        graph=initial_graph,
        probe_0=mock_p0,
        probe_1=mock_p1,
        probe_0_log_path=p0_log,
        probe_1_log_path=p1_log,
        wait_time_sec=0.01,
        test_tx=test_tx,
    )

    # Probe 0 sendinv_orphan called for mutually connected nodes (A, B, C)
    mock_p0.sendinv_orphan.assert_called_once_with([test_tx.hexstr], [1, 2, 3])

    # Probe 1 sendinv_orphan called only for responsive nodes (A, C)
    mock_p1.sendinv_orphan.assert_called_once_with([test_tx.hexstr], [11, 13])

    # Only Node A qualifies
    assert res.snapshot.nodes == (node_a,)
    assert res.eliminated_nonresponsive == (node_b,)
    assert res.eliminated_violating == (node_c,)

    assert res.stats.total_initial_nodes == 4
    assert res.stats.probe_0_responsive_count == 2  # A, C
    assert res.stats.probe_0_nonresponsive_count == 1  # B
    assert res.stats.probe_1_violating_count == 1  # C
    assert res.stats.remaining_qualified_count == 1  # A
    assert res.stats.eliminated_count == 3  # B (nonresponsive) + C (violating) + D (dropped)

    # Both probes had clearinv_probe called
    mock_p0.clearinv_probe.assert_called_once()
    mock_p1.clearinv_probe.assert_called_once()


def test_invblock_result_save_and_load(tmp_path: Path):
    """InvblockResult roundtrip JSON serialization."""
    n1 = NodeIdentity("1.1.1.1:48333")
    n2 = NodeIdentity("2.2.2.2:48333")
    snapshot = GraphSnapshot(nodes=(n1,), adj_list=MappingProxyType({n1: ()}))
    stats = InvblockStats(
        total_initial_nodes=2,
        probe_0_active_peers=2,
        probe_1_active_peers=2,
        mutually_connected_count=2,
        probe_0_responsive_count=1,
        probe_0_nonresponsive_count=1,
        probe_1_violating_count=0,
        eliminated_count=1,
        remaining_qualified_count=1,
        remaining_edges_count=0,
    )
    result = InvblockResult(
        snapshot=snapshot,
        eliminated_nonresponsive=(n2,),
        eliminated_violating=(),
        stats=stats,
    )

    out_file = tmp_path / "result.json"
    result.save(out_file)

    loaded = InvblockResult.load(out_file)
    assert loaded.snapshot.nodes == (n1,)
    assert loaded.eliminated_nonresponsive == (n2,)
    assert loaded.stats.probe_0_nonresponsive_count == 1
    assert loaded.stats.remaining_qualified_count == 1
