"""Unit tests for Step 4: TxProbe Execution Loop & Multi-Round Topology Inference."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from txprobe.config import TxProbeExecutionConfig
from txprobe.models.graph import GraphSnapshot
from txprobe.models.node import NodeIdentity
from txprobe.models.transaction import (
    TxCraftingStats,
    TxMessage,
    TxProbeCraftingResult,
    TxProbeRoundTxs,
    UtxoInfo,
)
from txprobe.probing import (
    RoundExecutionResult,
    TxProbeExecutionResult,
    TxProbeExecutionStats,
    build_cleanup_batch_calls,
    build_inferred_snapshot_from_edges,
    canonical_edge,
    detect_malfunctioning_sources,
    execute_single_round,
    extract_eligible_peer_maps,
    parse_getdata_by_tx_from_log,
    run_txprobe_execution,
)


def _make_tx(tag: str, index: int) -> TxMessage:
    """Create a deterministic dummy TxMessage with distinct txid and wtxid."""
    txid = f"{index:02x}" + tag.encode("ascii").hex().ljust(62, "a")[:62]
    wtxid = f"{index:02x}" + tag.encode("ascii").hex().ljust(62, "b")[:62]
    hexstr = f"02000000{index:02x}{tag.encode('ascii').hex()}"
    return TxMessage(txid=txid, wtxid=wtxid, hexstr=hexstr)


class FakeProbe0Rpc:
    """Configurable mock of Probe 0's AsyncBitcoinRpc for Step 4 unit testing."""

    def __init__(
        self,
        start_peers: list[dict[str, Any]],
        end_peers: list[dict[str, Any]] | None = None,
        log_path: Path | None = None,
        on_invblock: str = "",
        on_markers_batch: str = "",
        on_markers_inv: str = "",
    ) -> None:
        self.start_peers = start_peers
        self.end_peers = end_peers if end_peers is not None else start_peers
        self.log_path = log_path
        self.on_invblock = on_invblock
        self.on_markers_batch = on_markers_batch
        self.on_markers_inv = on_markers_inv

        self.getpeerinfo_calls = 0
        self.sendinv_calls: list[tuple[list[str], list[int]]] = []
        self.sendraw_calls: list[tuple[str, int, int, list[int]]] = []
        self.batch_calls: list[list[tuple[Any, ...]]] = []
        self.clearinv_calls = 0

    async def getpeerinfo(self) -> list[dict[str, Any]]:
        self.getpeerinfo_calls += 1
        if self.getpeerinfo_calls % 2 == 1:
            return self.start_peers
        return self.end_peers

    async def sendinv_orphan(
        self, hexstrings: list[str], peer_ids: list[int]
    ) -> dict[str, Any]:
        self.sendinv_calls.append((list(hexstrings), list(peer_ids)))
        if len(self.sendinv_calls) % 2 == 1:
            # Step 2.2: INVBLOCK
            if self.log_path and self.on_invblock:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(self.on_invblock)
        else:
            # Step 2.6: Marker INV query
            if self.log_path and self.on_markers_inv:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(self.on_markers_inv)
        return {"inv_sent_to": peer_ids}

    async def sendrawtransaction_orphan(
        self, hexstring: str, maxfeerate: int, maxburnamount: int, peer_ids: list[int]
    ) -> str:
        self.sendraw_calls.append((hexstring, maxfeerate, maxburnamount, list(peer_ids)))
        return "ok"

    async def call_batch(
        self, calls: list[tuple[Any, ...]], raise_on_error: bool = False
    ) -> list[Any]:
        self.batch_calls.append(list(calls))
        # Order of call_batch per round:
        # 1st: Step 2.4 (parent_txs)
        # 2nd: Step 2.5 (marker_txs)
        # 3rd: Step 2.8 (cleanup_calls)
        if len(self.batch_calls) % 3 == 2 and self.log_path and self.on_markers_batch:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(self.on_markers_batch)
        return ["ok" for _ in calls]

    async def clearinv_probe(self) -> dict[str, Any]:
        self.clearinv_calls += 1
        return {"cleared": True}


def test_canonical_edge():
    assert canonical_edge("10.0.0.2:48333", "10.0.0.1:48333") == (
        "10.0.0.1:48333",
        "10.0.0.2:48333",
    )
    assert canonical_edge("10.0.0.1:48333", "10.0.0.2:48333") == (
        "10.0.0.1:48333",
        "10.0.0.2:48333",
    )


def test_extract_eligible_peer_maps():
    peer_info = [
        {"id": 10, "addr": "1.1.1.1:48333", "connection_type": "manual"},
        {"id": 11, "addr": "127.0.0.1:48332", "connection_type": "manual"},
        {"id": 12, "addr": "2.2.2.2:48333", "connection_type": "block-relay-only"},
        {"id": 13, "addr": "abc.onion:48333", "connection_type": "outbound-full-relay"},
        {"id": None, "addr": "3.3.3.3:48333", "connection_type": "manual"},
    ]
    addr_to_id, id_to_addr = extract_eligible_peer_maps(peer_info)
    assert addr_to_id == {"1.1.1.1:48333": 10, "abc.onion:48333": 13}
    assert id_to_addr == {10: "1.1.1.1:48333", 13: "abc.onion:48333"}


def test_parse_getdata_by_tx_from_log_txid_and_wtxid(tmp_path: Path):
    tx0 = _make_tx("mtx", 0)
    tx1 = _make_tx("mtx", 1)
    tx2 = _make_tx("mtx", 2)

    log_file = tmp_path / "txprobe_0.log"
    log_file.write_text(
        "\n".join(
            [
                # Match tx0 by txid via BLOCKED_NOTFOUND with explicit addr
                f"2026-09-30T12:00:00Z [txprobe] BLOCKED_NOTFOUND peer=10 addr=1.1.1.1:48333 type=wtx hash={tx0.txid.upper()}",
                # Match tx1 by wtxid via BLOCKED_NOTFOUND with addr=unknown resolved by peer_id_to_addr
                f"2026-09-30T12:00:01Z [txprobe] BLOCKED_NOTFOUND peer=11 addr=unknown type=wtx hash={tx1.wtxid}",
                # Match tx2 by wtxid via net 'received getdata for:'
                f"2026-09-30T12:00:02Z [net] received getdata for: wtx {tx2.wtxid} peer=10",
                # Unrelated hash should be ignored
                "2026-09-30T12:00:03Z [txprobe] BLOCKED_NOTFOUND peer=10 addr=1.1.1.1:48333 type=wtx hash="
                + "f" * 64,
            ]
        ),
        encoding="utf-8",
    )

    id_to_addr = {10: "1.1.1.1:48333", 11: "2.2.2.2:48333"}
    res = parse_getdata_by_tx_from_log(log_file, [tx0, tx1, tx2], id_to_addr)

    assert res == {
        "1.1.1.1:48333": {0, 2},
        "2.2.2.2:48333": {1},
    }


def test_detect_malfunctioning_sources():
    s0 = NodeIdentity("10.0.0.1:48333")
    s1 = NodeIdentity("10.0.0.2:48333")
    s2 = NodeIdentity("10.0.0.3:48333")

    # s0 requested ptx_0 in Step 2.5 (orphan resolution because ptx_0 was rejected)
    # s1 requested mtx_0 (another source's marker, NOT its own mtx_1 -> normal!)
    # s2 requested its own mtx_2 in Step 2.6 -> malfunctioning!
    parent_getdata = {"10.0.0.1:48333": {0}}
    marker_getdata = {
        "10.0.0.2:48333": {0},
        "10.0.0.3:48333": {2},
    }

    malf = detect_malfunctioning_sources([s0, s1, s2], parent_getdata, marker_getdata)
    assert malf == {s0, s2}


def test_build_cleanup_batch_calls():
    s0 = NodeIdentity("10.0.0.1:48333")
    s1 = NodeIdentity("10.0.0.2:48333")
    ptx0 = _make_tx("ptx", 0)
    ptx1 = _make_tx("ptx", 1)
    ftx = _make_tx("ftx", 0)

    addr_to_id = {
        "10.0.0.1:48333": 1,
        "10.0.0.2:48333": 2,
        "10.0.0.3:48333": 3,
        "10.0.0.4:48333": 4,
    }
    all_pids = [1, 2, 3, 4]

    calls = build_cleanup_batch_calls([s0, s1], [ptx0, ptx1], ftx, addr_to_id, all_pids)
    assert len(calls) == 3
    # ptx0 sent to everyone except s0 (pid 1)
    assert calls[0] == ("sendrawtransaction_orphan", ptx0.hexstr, 0, 0, [2, 3, 4])
    # ptx1 sent to everyone except s1 (pid 2)
    assert calls[1] == ("sendrawtransaction_orphan", ptx1.hexstr, 0, 0, [1, 3, 4])
    # flood_tx sent to all active sources [1, 2]
    assert calls[2] == ("sendrawtransaction_orphan", ftx.hexstr, 0, 0, [1, 2])


def test_build_inferred_snapshot_from_edges():
    n0 = NodeIdentity("10.0.0.1:48333")
    n1 = NodeIdentity("10.0.0.2:48333")
    n2 = NodeIdentity("10.0.0.3:48333")

    edges = [
        canonical_edge(n0.addr, n2.addr),
        canonical_edge(n1.addr, n2.addr),
        canonical_edge(n0.addr, n0.addr),  # self-loop ignored
    ]
    snap = build_inferred_snapshot_from_edges([n0, n1, n2], edges)
    assert snap.num_nodes == 3
    assert snap.num_edges == 2
    assert snap.adj_list[n0] == (n2,)
    assert snap.adj_list[n1] == (n2,)
    assert snap.adj_list[n2] == (n0, n1)


@pytest.mark.asyncio
async def test_execute_single_round_double_log_clear_and_edge_discard(tmp_path: Path):
    s0 = NodeIdentity("10.0.0.1:48333")
    s1 = NodeIdentity("10.0.0.2:48333")
    k0 = NodeIdentity("10.0.0.3:48333")
    k1 = NodeIdentity("10.0.0.4:48333")

    ptx0 = _make_tx("ptx", 0)
    ptx1 = _make_tx("ptx", 1)
    ftx = _make_tx("ftx", 0)
    mtx0 = _make_tx("mtx", 0)
    mtx1 = _make_tx("mtx", 1)

    round_txs = TxProbeRoundTxs(
        round_index=0,
        source_nodes=(s0, s1),
        sink_nodes=(k0, k1),
        utxo=UtxoInfo(txid="00" * 32, vout=0, amount_sats=2000),
        parent_txs=(ptx0, ptx1),
        flood_tx=ftx,
        marker_txs=(mtx0, mtx1),
    )

    peers = [
        {"id": 1, "addr": s0.addr, "connection_type": "manual"},
        {"id": 2, "addr": s1.addr, "connection_type": "manual"},
        {"id": 3, "addr": k0.addr, "connection_type": "manual"},
        {"id": 4, "addr": k1.addr, "connection_type": "manual"},
    ]

    log_file = tmp_path / "txprobe_0.log"
    # Pre-seed stale noise in log file
    log_file.write_text(
        f"STALE LOG ENTRY BLOCKED_NOTFOUND peer=1 addr={s0.addr} type=wtx hash={mtx0.wtxid}\n",
        encoding="utf-8",
    )

    # During Step 2.2 (INVBLOCK), suppose s0 requests mtx0 (noise that must be cleared in Step 2.5!)
    invblock_noise = (
        f"2026-09-30T12:00:00Z [txprobe] BLOCKED_NOTFOUND peer=1 addr={s0.addr} type=wtx hash={mtx0.wtxid}\n"
    )
    # During Step 2.6 (Marker INV), suppose:
    # - k0 is connected to s0 (already has mtx0 in txorphanage), so k0 only requests mtx1
    # - k1 is connected to neither s0 nor s1, so k1 requests both mtx0 and mtx1
    marker_inv_log = "\n".join(
        [
            f"2026-09-30T12:00:10Z [txprobe] BLOCKED_NOTFOUND peer=3 addr={k0.addr} type=wtx hash={mtx1.wtxid}",
            f"2026-09-30T12:00:11Z [txprobe] BLOCKED_NOTFOUND peer=4 addr={k1.addr} type=wtx hash={mtx0.txid}",
            f"2026-09-30T12:00:12Z [txprobe] BLOCKED_NOTFOUND peer=4 addr={k1.addr} type=wtx hash={mtx1.wtxid}",
        ]
    )

    fake_rpc = FakeProbe0Rpc(
        start_peers=peers,
        log_path=log_file,
        on_invblock=invblock_noise,
        on_markers_batch="",
        on_markers_inv=marker_inv_log,
    )
    fast_cfg = TxProbeExecutionConfig(
        invblock_wait_sec=0.0,
        flood_wait_sec=0.0,
        parent_wait_sec=0.0,
        marker_propagation_wait_sec=0.0,
        getdata_wait_sec=0.0,
        cleanup_wait_sec=0.0,
    )

    res, tested, discarded = await execute_single_round(
        round_txs=round_txs,
        probe_0=fake_rpc,  # type: ignore[arg-type]
        probe_0_log_path=log_file,
        config=fast_cfg,
    )

    # Verify stale INVBLOCK noise was cleared before Step 2.5/2.6 so s0 is NOT marked malfunctioning
    assert res.malfunctioning_sources == ()
    assert res.dropped_nodes == ()
    assert res.active_sources == (s0, s1)
    assert res.active_sinks == (k0, k1)
    assert dict(res.requested_markers_by_sink) == {
        k0.addr: (1,),
        k1.addr: (0, 1),
    }

    # All 4 (source, sink) pairs were tested; 3 were discarded, leaving {s0, k0} undiscarded
    assert len(tested) == 4
    assert discarded == {
        canonical_edge(s1.addr, k0.addr),
        canonical_edge(s0.addr, k1.addr),
        canonical_edge(s1.addr, k1.addr),
    }
    assert tested - discarded == {canonical_edge(s0.addr, k0.addr)}

    # Step 2.6 sendinv_orphan was sent to ALL active peers [1, 2, 3, 4] (sources + sinks)
    assert fake_rpc.sendinv_calls[1] == ([mtx0.hexstr, mtx1.hexstr], [1, 2, 3, 4])
    # Step 2.8 cleanup calls were executed via call_batch (3rd batch call)
    assert len(fake_rpc.batch_calls) == 3
    assert len(fake_rpc.batch_calls[2]) == 3
    # Log file was truncated at the end of Step 2.8
    assert log_file.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_execute_single_round_malfunctioning_source_and_midround_disconnect(
    tmp_path: Path,
):
    s0 = NodeIdentity("10.0.0.1:48333")
    s1 = NodeIdentity("10.0.0.2:48333")
    k0 = NodeIdentity("10.0.0.3:48333")
    k1 = NodeIdentity("10.0.0.4:48333")

    ptx0 = _make_tx("ptx", 0)
    ptx1 = _make_tx("ptx", 1)
    ftx = _make_tx("ftx", 0)
    mtx0 = _make_tx("mtx", 0)
    mtx1 = _make_tx("mtx", 1)

    round_txs = TxProbeRoundTxs(
        round_index=1,
        source_nodes=(s0, s1),
        sink_nodes=(k0, k1),
        utxo=UtxoInfo(txid="11" * 32, vout=1, amount_sats=2000),
        parent_txs=(ptx0, ptx1),
        flood_tx=ftx,
        marker_txs=(mtx0, mtx1),
    )

    start_peers = [
        {"id": 1, "addr": s0.addr, "connection_type": "manual"},
        {"id": 2, "addr": s1.addr, "connection_type": "manual"},
        {"id": 3, "addr": k0.addr, "connection_type": "manual"},
        {"id": 4, "addr": k1.addr, "connection_type": "manual"},
    ]
    # k1 disconnects mid-round before Step 2.7 getpeerinfo()
    end_peers = [
        {"id": 1, "addr": s0.addr, "connection_type": "manual"},
        {"id": 2, "addr": s1.addr, "connection_type": "manual"},
        {"id": 3, "addr": k0.addr, "connection_type": "manual"},
    ]

    log_file = tmp_path / "txprobe_0.log"
    # In Step 2.5, s1 rejected ptx1 so when mtx1 arrives, s1 sends GETDATA(ptx1) via orphan resolution!
    step25_log = (
        f"2026-09-30T12:01:00Z [txprobe] BLOCKED_NOTFOUND peer=2 addr={s1.addr} type=wtx hash={ptx1.wtxid}\n"
    )
    # In Step 2.6, k0 requests mtx1 (from malfunctioning s1) but NOT mtx0 (connected to s0)
    step26_log = (
        f"2026-09-30T12:01:10Z [txprobe] BLOCKED_NOTFOUND peer=3 addr={k0.addr} type=wtx hash={mtx1.wtxid}\n"
    )

    fake_rpc = FakeProbe0Rpc(
        start_peers=start_peers,
        end_peers=end_peers,
        log_path=log_file,
        on_markers_batch=step25_log,
        on_markers_inv=step26_log,
    )
    fast_cfg = TxProbeExecutionConfig(
        invblock_wait_sec=0.0,
        flood_wait_sec=0.0,
        parent_wait_sec=0.0,
        marker_propagation_wait_sec=0.0,
        getdata_wait_sec=0.0,
        cleanup_wait_sec=0.0,
    )

    res, tested, discarded = await execute_single_round(
        round_txs=round_txs,
        probe_0=fake_rpc,  # type: ignore[arg-type]
        probe_0_log_path=log_file,
        config=fast_cfg,
    )

    assert res.malfunctioning_sources == (s1,)
    assert res.dropped_nodes == (k1,)
    assert res.active_sources == (s0,)
    assert res.active_sinks == (k0,)
    # Only {s0, k0} was validly tested, and it was NOT discarded
    assert tested == {canonical_edge(s0.addr, k0.addr)}
    assert discarded == set()


@pytest.mark.asyncio
async def test_run_txprobe_execution_complete_graph_discard_multi_round(tmp_path: Path):
    """Verify Method 2 (Complete Graph K_V -> Discard on GETDATA) across 2 rounds."""
    n0 = NodeIdentity("10.0.0.1:48333")
    n1 = NodeIdentity("10.0.0.2:48333")
    n2 = NodeIdentity("10.0.0.3:48333")
    n3 = NodeIdentity("10.0.0.4:48333")

    # True topology: only {n0, n2} are connected
    initial_snapshot = GraphSnapshot(
        nodes=(n0, n1, n2, n3),
        adj_list=MappingProxyType(
            {
                n0: (n2,),
                n1: (),
                n2: (n0,),
                n3: (),
            }
        ),
    )

    # Round 0: sources=(n0, n1), sinks=(n2, n3) -> tests {n0,n2}, {n0,n3}, {n1,n2}, {n1,n3}
    r0_ptx0, r0_ptx1 = _make_tx("r0p", 0), _make_tx("r0p", 1)
    r0_ftx = _make_tx("r0f", 0)
    r0_mtx0, r0_mtx1 = _make_tx("r0m", 0), _make_tx("r0m", 1)
    round0 = TxProbeRoundTxs(
        round_index=0,
        source_nodes=(n0, n1),
        sink_nodes=(n2, n3),
        utxo=UtxoInfo(txid="a0" * 32, vout=0, amount_sats=2000),
        parent_txs=(r0_ptx0, r0_ptx1),
        flood_tx=r0_ftx,
        marker_txs=(r0_mtx0, r0_mtx1),
    )

    # Round 1: sources=(n0, n2), sinks=(n1, n3) -> tests {n0,n1}, {n0,n3}, {n2,n1}, {n2,n3}
    r1_ptx0, r1_ptx1 = _make_tx("r1p", 0), _make_tx("r1p", 1)
    r1_ftx = _make_tx("r1f", 0)
    r1_mtx0, r1_mtx1 = _make_tx("r1m", 0), _make_tx("r1m", 1)
    round1 = TxProbeRoundTxs(
        round_index=1,
        source_nodes=(n0, n2),
        sink_nodes=(n1, n3),
        utxo=UtxoInfo(txid="a1" * 32, vout=1, amount_sats=2000),
        parent_txs=(r1_ptx0, r1_ptx1),
        flood_tx=r1_ftx,
        marker_txs=(r1_mtx0, r1_mtx1),
    )

    crafting_result = TxProbeCraftingResult(
        snapshot=initial_snapshot,
        rounds=(round0, round1),
        stats=TxCraftingStats(
            total_nodes=4,
            matrix_width=2,
            matrix_height=2,
            total_rounds=2,
            total_parent_txs=4,
            total_flood_txs=2,
            total_marker_txs=4,
            split_txids=(),
        ),
    )

    peers = [
        {"id": 1, "addr": n0.addr, "connection_type": "manual"},
        {"id": 2, "addr": n1.addr, "connection_type": "manual"},
        {"id": 3, "addr": n2.addr, "connection_type": "manual"},
        {"id": 4, "addr": n3.addr, "connection_type": "manual"},
    ]
    log_file = tmp_path / "txprobe_0.log"

    class MultiRoundRpc(FakeProbe0Rpc):
        async def sendinv_orphan(
            self, hexstrings: list[str], peer_ids: list[int]
        ) -> dict[str, Any]:
            self.sendinv_calls.append((list(hexstrings), list(peer_ids)))
            call_num = len(self.sendinv_calls)
            if call_num == 2:
                # Round 0 Step 2.6: n2 requests r0_mtx1 (not r0_mtx0 because {n0,n2} connected);
                # n3 requests both r0_mtx0 and r0_mtx1
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(
                        f"[txprobe] BLOCKED_NOTFOUND peer=3 addr={n2.addr} type=wtx hash={r0_mtx1.wtxid}\n"
                        f"[txprobe] BLOCKED_NOTFOUND peer=4 addr={n3.addr} type=wtx hash={r0_mtx0.wtxid}\n"
                        f"[txprobe] BLOCKED_NOTFOUND peer=4 addr={n3.addr} type=wtx hash={r0_mtx1.wtxid}\n"
                    )
            elif call_num == 4:
                # Round 1 Step 2.6: n1 requests both r1_mtx0 and r1_mtx1;
                # n3 requests both r1_mtx0 and r1_mtx1
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(
                        f"[txprobe] BLOCKED_NOTFOUND peer=2 addr={n1.addr} type=wtx hash={r1_mtx0.wtxid}\n"
                        f"[txprobe] BLOCKED_NOTFOUND peer=2 addr={n1.addr} type=wtx hash={r1_mtx1.wtxid}\n"
                        f"[txprobe] BLOCKED_NOTFOUND peer=4 addr={n3.addr} type=wtx hash={r1_mtx0.wtxid}\n"
                        f"[txprobe] BLOCKED_NOTFOUND peer=4 addr={n3.addr} type=wtx hash={r1_mtx1.wtxid}\n"
                    )
            return {"inv_sent_to": peer_ids}

    rpc = MultiRoundRpc(start_peers=peers, log_path=log_file)
    fast_cfg = TxProbeExecutionConfig(
        invblock_wait_sec=0.0,
        flood_wait_sec=0.0,
        parent_wait_sec=0.0,
        marker_propagation_wait_sec=0.0,
        getdata_wait_sec=0.0,
        cleanup_wait_sec=0.0,
    )
    ckpt_file = tmp_path / "ckpt.json"
    out_file = tmp_path / "exec.json"

    exec_result = await run_txprobe_execution(
        crafting_result=crafting_result,
        probe_0=rpc,  # type: ignore[arg-type]
        probe_0_log_path=log_file,
        config=fast_cfg,
        checkpoint_path=ckpt_file,
    )

    # Only {n0, n2} survives in inferred_snapshot!
    assert exec_result.inferred_snapshot.num_nodes == 4
    assert exec_result.inferred_snapshot.num_edges == 1
    assert exec_result.inferred_snapshot.adj_list[n0] == (n2,)
    assert exec_result.inferred_snapshot.adj_list[n2] == (n0,)
    assert exec_result.inferred_snapshot.adj_list[n1] == ()
    assert exec_result.inferred_snapshot.adj_list[n3] == ()

    # Stats check
    assert exec_result.stats.total_rounds == 2
    assert exec_result.stats.completed_rounds == 2
    assert exec_result.stats.surviving_nodes_count == 4
    assert exec_result.stats.inferred_edges_count == 1
    assert exec_result.stats.filtered_groundtruth_edges_count == 1

    # Serialization roundtrip check
    exec_result.save(out_file)
    loaded = TxProbeExecutionResult.load(out_file)
    assert loaded.to_dict() == exec_result.to_dict()
    assert ckpt_file.is_file()
