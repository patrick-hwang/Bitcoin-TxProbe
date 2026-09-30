"""Step 4: TxProbe Execution Loop & Multi-Round Topology Inference.

Executes all pre-crafted matrix rounds from Step 3 sequentially against the
live P2P network without waiting for new blocks:
1. Initializes the candidate topology as a Complete Graph (K_V) over all
   qualified nodes (Method 2: Complete Graph -> Discard on GETDATA).
2. For each round r:
   - Step 2.1: Queries Probe 0's active peers and filters out dropped or
     previously excluded nodes.
   - Step 2.2 (INVBLOCK): Announces [*parent_txs, flood_tx] via sendinv_orphan
     to all active peers in the round and waits invblock_wait_sec.
   - Step 2.3 (Flood Sinks): Sends flood_tx to all active sink nodes via
     sendrawtransaction_orphan and waits flood_wait_sec.
   - Step 2.4 (Distribute Parents 1-to-1): Sends parent_txs[i] to source_nodes[i]
     in a single JSON-RPC batch call and waits parent_wait_sec.
   - Step 2.5 (Clear INVBLOCK, Clear Log #1 & Distribute Markers 1-to-1):
     Calls clearinv_probe(), truncates txprobe_0.log (removing all INVBLOCK
     history), sends marker_txs[i] to source_nodes[i] via call_batch, and waits
     marker_propagation_wait_sec. Parses txprobe_0.log to detect any source s_i
     that requested GETDATA for its own parent_txs[i] (indicating s_i rejected
     parent_txs[i] due to receiving a conflicting tx).
   - Step 2.6 (Clear Log #2 & Query Markers): Truncates txprobe_0.log again,
     announces marker_txs via sendinv_orphan to all active peers (both sinks and
     sources, registering probe_0 as an announcer for 1P1C orphanage cleanup),
     and waits getdata_wait_sec.
   - Step 2.7 (Deduce & Discard Edges): Verifies end-of-round peer connectivity,
     parses txprobe_0.log for marker GETDATA requests, and discards any pair
     {s_i, k_j} where sink k_j requested marker_txs[i].
   - Step 2.8 (Post-Round Orphanage Cleanup): Calls clearinv_probe() and sends
     the remaining parent transactions (ptx_1..ptx_n, flood_tx) across active
     peers so all nodes evict marker_txs from their txorphanage before round r+1.
3. Produces the final inferred GraphSnapshot and filtered groundtruth GraphSnapshot.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
import logging
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .config import TxProbeExecutionConfig
from .invblock import RE_BLOCKED_NOTFOUND, RE_RECEIVED_GETDATA, clear_log_file
from .models.graph import GraphSnapshot
from .models.node import NodeIdentity
from .models.transaction import TxMessage, TxProbeCraftingResult, TxProbeRoundTxs
from .rpc.client import AsyncBitcoinRpc

log = logging.getLogger(__name__)


def canonical_edge(addr_a: str, addr_b: str) -> tuple[str, str]:
    """Return an ordered undirected edge tuple (min_addr, max_addr)."""
    return (addr_a, addr_b) if addr_a <= addr_b else (addr_b, addr_a)


@dataclass(frozen=True)
class RoundExecutionResult:
    """Telemetry and inference details for a single executed TxProbe round."""

    round_index: int
    active_sources: tuple[NodeIdentity, ...]
    active_sinks: tuple[NodeIdentity, ...]
    malfunctioning_sources: tuple[NodeIdentity, ...]
    dropped_nodes: tuple[NodeIdentity, ...]
    requested_markers_by_sink: Mapping[str, tuple[int, ...]]
    tested_pairs_count: int
    discarded_edges_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "round_index": self.round_index,
            "active_sources": [n.addr for n in self.active_sources],
            "active_sinks": [n.addr for n in self.active_sinks],
            "malfunctioning_sources": [n.addr for n in self.malfunctioning_sources],
            "dropped_nodes": [n.addr for n in self.dropped_nodes],
            "requested_markers_by_sink": {
                addr: list(indices)
                for addr, indices in self.requested_markers_by_sink.items()
            },
            "tested_pairs_count": self.tested_pairs_count,
            "discarded_edges_count": self.discarded_edges_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoundExecutionResult:
        """Deserialize from a dictionary."""
        req_map = {
            str(addr): tuple(int(i) for i in idx_list)
            for addr, idx_list in data.get("requested_markers_by_sink", {}).items()
        }
        return cls(
            round_index=int(data["round_index"]),
            active_sources=tuple(
                NodeIdentity(addr=a) for a in data.get("active_sources", [])
            ),
            active_sinks=tuple(
                NodeIdentity(addr=a) for a in data.get("active_sinks", [])
            ),
            malfunctioning_sources=tuple(
                NodeIdentity(addr=a) for a in data.get("malfunctioning_sources", [])
            ),
            dropped_nodes=tuple(
                NodeIdentity(addr=a) for a in data.get("dropped_nodes", [])
            ),
            requested_markers_by_sink=MappingProxyType(req_map),
            tested_pairs_count=int(data.get("tested_pairs_count", 0)),
            discarded_edges_count=int(data.get("discarded_edges_count", 0)),
        )


@dataclass(frozen=True)
class TxProbeExecutionStats:
    """Aggregate statistics for Step 4 TxProbe execution."""

    total_rounds: int
    completed_rounds: int
    initial_nodes_count: int
    surviving_nodes_count: int
    malfunctioning_nodes_count: int
    dropped_nodes_count: int
    total_tested_pairs: int
    inferred_edges_count: int
    filtered_groundtruth_edges_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "total_rounds": self.total_rounds,
            "completed_rounds": self.completed_rounds,
            "initial_nodes_count": self.initial_nodes_count,
            "surviving_nodes_count": self.surviving_nodes_count,
            "malfunctioning_nodes_count": self.malfunctioning_nodes_count,
            "dropped_nodes_count": self.dropped_nodes_count,
            "total_tested_pairs": self.total_tested_pairs,
            "inferred_edges_count": self.inferred_edges_count,
            "filtered_groundtruth_edges_count": self.filtered_groundtruth_edges_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxProbeExecutionStats:
        """Deserialize from a dictionary."""
        return cls(
            total_rounds=int(data["total_rounds"]),
            completed_rounds=int(data["completed_rounds"]),
            initial_nodes_count=int(data["initial_nodes_count"]),
            surviving_nodes_count=int(data["surviving_nodes_count"]),
            malfunctioning_nodes_count=int(data["malfunctioning_nodes_count"]),
            dropped_nodes_count=int(data["dropped_nodes_count"]),
            total_tested_pairs=int(data.get("total_tested_pairs", 0)),
            inferred_edges_count=int(data["inferred_edges_count"]),
            filtered_groundtruth_edges_count=int(
                data["filtered_groundtruth_edges_count"]
            ),
        )


@dataclass(frozen=True)
class TxProbeExecutionResult:
    """Complete output of Step 4 TxProbe execution."""

    inferred_snapshot: GraphSnapshot
    filtered_groundtruth_snapshot: GraphSnapshot
    malfunctioning_nodes: tuple[NodeIdentity, ...]
    dropped_nodes: tuple[NodeIdentity, ...]
    round_results: tuple[RoundExecutionResult, ...]
    stats: TxProbeExecutionStats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "inferred_snapshot": self.inferred_snapshot.to_dict(),
            "filtered_groundtruth_snapshot": self.filtered_groundtruth_snapshot.to_dict(),
            "malfunctioning_nodes": [n.addr for n in self.malfunctioning_nodes],
            "dropped_nodes": [n.addr for n in self.dropped_nodes],
            "round_results": [r.to_dict() for r in self.round_results],
            "stats": self.stats.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        """Save execution results to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxProbeExecutionResult:
        """Deserialize from a dictionary."""
        return cls(
            inferred_snapshot=GraphSnapshot.from_dict(data["inferred_snapshot"]),
            filtered_groundtruth_snapshot=GraphSnapshot.from_dict(
                data["filtered_groundtruth_snapshot"]
            ),
            malfunctioning_nodes=tuple(
                NodeIdentity(addr=a) for a in data.get("malfunctioning_nodes", [])
            ),
            dropped_nodes=tuple(
                NodeIdentity(addr=a) for a in data.get("dropped_nodes", [])
            ),
            round_results=tuple(
                RoundExecutionResult.from_dict(r)
                for r in data.get("round_results", [])
            ),
            stats=TxProbeExecutionStats.from_dict(data["stats"]),
        )

    @classmethod
    def from_json(cls, text: str) -> TxProbeExecutionResult:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> TxProbeExecutionResult:
        """Load a TxProbeExecutionResult from a JSON file."""
        p = Path(path)
        return cls.from_json(p.read_text(encoding="utf-8"))


def extract_eligible_peer_maps(
    peer_info: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, int], dict[int, str]]:
    """Build addr->peer_id and peer_id->addr maps for eligible full-relay peers."""
    addr_to_id: dict[str, int] = {}
    id_to_addr: dict[int, str] = {}
    for p in peer_info:
        addr = str(p.get("addr", ""))
        pid = p.get("id")
        conn_type = str(p.get("connection_type", ""))
        if (
            addr
            and pid is not None
            and not addr.startswith("127.0.0.1")
            and conn_type != "block-relay-only"
        ):
            pid_int = int(pid)
            addr_to_id[addr] = pid_int
            id_to_addr[pid_int] = addr
    return addr_to_id, id_to_addr


def parse_getdata_by_tx_from_log(
    log_path: str | Path,
    txs: Sequence[TxMessage],
    peer_id_to_addr: Mapping[int, str] | None = None,
) -> dict[str, set[int]]:
    """Parse a custom bitcoind txprobe log file to map peer addrs to requested tx indices.

    Matches every transaction in ``txs`` by both its ``txid`` and ``wtxid``
    (case-insensitive) against:
    1. ``BLOCKED_NOTFOUND peer=<id> addr=<addr> type=<type> hash=<hash>``
    2. ``received getdata for: <type> <hash> peer=<id>``

    Args:
        log_path: Path to Probe 0's log file (e.g. ``txprobe_0.log``).
        txs: Ordered sequence of TxMessage objects (indices ``0..len(txs)-1``).
        peer_id_to_addr: Optional mapping of numeric peer ID to ``"host:port"``.

    Returns:
        Dictionary mapping ``peer_addr -> set of indices in txs`` requested by that peer.
    """
    path = Path(log_path)
    if not path.is_file() or not txs:
        return {}

    hash_to_indices: dict[str, list[int]] = defaultdict(list)
    for idx, tx in enumerate(txs):
        txid_lower = tx.txid.lower()
        wtxid_lower = tx.wtxid.lower()
        hash_to_indices[txid_lower].append(idx)
        if wtxid_lower != txid_lower:
            hash_to_indices[wtxid_lower].append(idx)

    requested_by_addr: dict[str, set[int]] = defaultdict(set)

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m_blocked = RE_BLOCKED_NOTFOUND.search(line)
                if m_blocked:
                    peer_id = int(m_blocked.group(1))
                    addr = m_blocked.group(2)
                    hash_str = m_blocked.group(3).lower()
                    if hash_str in hash_to_indices:
                        resolved_addr = (
                            peer_id_to_addr.get(peer_id, addr)
                            if peer_id_to_addr and (not addr or addr == "unknown")
                            else addr
                        )
                        if resolved_addr and resolved_addr != "unknown":
                            requested_by_addr[resolved_addr].update(
                                hash_to_indices[hash_str]
                            )
                    continue

                m_getdata = RE_RECEIVED_GETDATA.search(line)
                if m_getdata:
                    hash_str = m_getdata.group(1).lower()
                    peer_id = int(m_getdata.group(2))
                    if hash_str in hash_to_indices:
                        if peer_id_to_addr and peer_id in peer_id_to_addr:
                            addr = peer_id_to_addr[peer_id]
                            requested_by_addr[addr].update(hash_to_indices[hash_str])
    except Exception as e:
        log.error("Error reading log file %s: %s", log_path, e)

    return dict(requested_by_addr)


def detect_malfunctioning_sources(
    active_sources: Sequence[NodeIdentity],
    parent_getdata_by_addr: Mapping[str, set[int]],
    marker_getdata_by_addr: Mapping[str, set[int]],
) -> set[NodeIdentity]:
    """Identify source nodes that failed to accept their own parent/marker transactions.

    If source ``active_sources[i]`` rejected ``parent_txs[i]`` (e.g., because
    ``flood_tx`` or another conflicting parent leaked into its mempool prior to
    Step 2.4), then:
    - Upon receiving ``marker_txs[i]`` in Step 2.5, ``marker_txs[i]`` fails with
      ``TX_MISSING_INPUTS`` and triggers Bitcoin Core's orphan resolution
      (``MaybeAddOrphanResolutionCandidate``), which sends ``GETDATA(parent_txs[i])``
      back to Probe 0 during Step 2.5.
    - Or during Step 2.6, ``active_sources[i]`` sends ``GETDATA(marker_txs[i])``
      back to Probe 0.
    """
    malfunctioning: set[NodeIdentity] = set()
    for idx, src in enumerate(active_sources):
        req_parents = parent_getdata_by_addr.get(src.addr, set())
        req_markers = marker_getdata_by_addr.get(src.addr, set())
        if idx in req_parents or idx in req_markers:
            malfunctioning.add(src)
    return malfunctioning


def build_cleanup_batch_calls(
    active_sources: Sequence[NodeIdentity],
    active_parent_txs: Sequence[TxMessage],
    flood_tx: TxMessage,
    addr_to_id: Mapping[str, int],
    all_active_peer_ids: Sequence[int],
) -> list[tuple[Any, ...]]:
    """Build batched sendrawtransaction_orphan calls for Post-Round Orphanage Cleanup.

    Sends the remaining parent transactions (``ptx_1..ptx_n`` and ``flood_tx``) to
    all active peers that did not receive them earlier in the round, triggering
    1P1C package evaluation / conflict rejection so every node erases ``mtx_i``
    from its ``txorphanage``.
    """
    calls: list[tuple[Any, ...]] = []
    if not all_active_peer_ids:
        return calls

    for src, ptx in zip(active_sources, active_parent_txs):
        src_pid = addr_to_id.get(src.addr)
        target_pids = [pid for pid in all_active_peer_ids if pid != src_pid]
        if target_pids:
            calls.append(("sendrawtransaction_orphan", ptx.hexstr, 0, 0, target_pids))

    source_pids = [
        addr_to_id[src.addr] for src in active_sources if src.addr in addr_to_id
    ]
    if source_pids:
        calls.append(("sendrawtransaction_orphan", flood_tx.hexstr, 0, 0, source_pids))

    return calls


def build_inferred_snapshot_from_edges(
    nodes: Sequence[NodeIdentity],
    canonical_edges: Iterable[tuple[str, str]],
) -> GraphSnapshot:
    """Construct a symmetric undirected GraphSnapshot from canonical edge pairs."""
    node_tuple = tuple(dict.fromkeys(nodes))
    node_set = set(node_tuple)
    adj_sets: dict[NodeIdentity, set[NodeIdentity]] = {n: set() for n in node_tuple}

    for addr_u, addr_v in canonical_edges:
        if addr_u == addr_v:
            continue
        u = NodeIdentity(addr=addr_u)
        v = NodeIdentity(addr=addr_v)
        if u in node_set and v in node_set:
            adj_sets[u].add(v)
            adj_sets[v].add(u)

    # Preserve deterministic node ordering in adjacency lists
    node_order = {n: idx for idx, n in enumerate(node_tuple)}
    adj_list: dict[NodeIdentity, tuple[NodeIdentity, ...]] = {
        n: tuple(sorted(peers, key=lambda p: node_order[p]))
        for n, peers in adj_sets.items()
    }
    return GraphSnapshot(
        nodes=node_tuple,
        adj_list=MappingProxyType(adj_list),
    )


async def execute_single_round(
    round_txs: TxProbeRoundTxs,
    probe_0: AsyncBitcoinRpc,
    probe_0_log_path: str | Path,
    config: TxProbeExecutionConfig | None = None,
    excluded_nodes: set[NodeIdentity] | None = None,
) -> tuple[RoundExecutionResult, set[tuple[str, str]], set[tuple[str, str]]]:
    """Execute a single pre-crafted TxProbe matrix round.

    Args:
        round_txs: Pre-crafted transactions and partition for this round.
        probe_0: AsyncBitcoinRpc client for Probe 0.
        probe_0_log_path: Path to Probe 0's custom log file (``txprobe_0.log``).
        config: Optional timing configuration for Step 4 phases.
        excluded_nodes: Optional set of nodes already dropped or malfunctioning.

    Returns:
        Tuple of ``(round_result, tested_canonical_pairs, discarded_canonical_pairs)``.
    """
    cfg = config or TxProbeExecutionConfig()
    excluded = excluded_nodes or set()

    if len(round_txs.source_nodes) != len(round_txs.parent_txs) or len(
        round_txs.source_nodes
    ) != len(round_txs.marker_txs):
        raise ValueError(
            f"Round {round_txs.round_index}: mismatch between source_nodes "
            f"({len(round_txs.source_nodes)}), parent_txs ({len(round_txs.parent_txs)}), "
            f"and marker_txs ({len(round_txs.marker_txs)})"
        )

    # Step 2.1: Query Probe 0 active peers at the start of the round
    start_peer_info = await probe_0.getpeerinfo()
    start_addr_to_id, start_id_to_addr = extract_eligible_peer_maps(start_peer_info)

    active_sources: list[NodeIdentity] = []
    active_parent_txs: list[TxMessage] = []
    active_marker_txs: list[TxMessage] = []
    dropped_in_round: list[NodeIdentity] = []

    for src, ptx, mtx in zip(
        round_txs.source_nodes, round_txs.parent_txs, round_txs.marker_txs
    ):
        if src in excluded:
            continue
        if src.addr not in start_addr_to_id:
            dropped_in_round.append(src)
            continue
        active_sources.append(src)
        active_parent_txs.append(ptx)
        active_marker_txs.append(mtx)

    active_sinks: list[NodeIdentity] = []
    for sink in round_txs.sink_nodes:
        if sink in excluded:
            continue
        if sink.addr not in start_addr_to_id:
            dropped_in_round.append(sink)
            continue
        active_sinks.append(sink)

    if not active_sources or not active_sinks:
        log.warning(
            "Round %d skipped: %d active sources, %d active sinks",
            round_txs.round_index,
            len(active_sources),
            len(active_sinks),
        )
        empty_res = RoundExecutionResult(
            round_index=round_txs.round_index,
            active_sources=tuple(active_sources),
            active_sinks=tuple(active_sinks),
            malfunctioning_sources=(),
            dropped_nodes=tuple(dict.fromkeys(dropped_in_round)),
            requested_markers_by_sink=MappingProxyType({}),
            tested_pairs_count=0,
            discarded_edges_count=0,
        )
        return empty_res, set(), set()

    active_source_pids = [start_addr_to_id[s.addr] for s in active_sources]
    active_sink_pids = [start_addr_to_id[k.addr] for k in active_sinks]
    all_active_pids = active_source_pids + active_sink_pids

    # Step 2.2: INVBLOCK - announce [*active_parent_txs, flood_tx] to all active peers
    invblock_hexes = [
        *(ptx.hexstr for ptx in active_parent_txs),
        round_txs.flood_tx.hexstr,
    ]
    await probe_0.sendinv_orphan(invblock_hexes, all_active_pids)
    if cfg.invblock_wait_sec > 0:
        await asyncio.sleep(cfg.invblock_wait_sec)

    # Step 2.3: Send flood_tx to all active sink nodes
    await probe_0.sendrawtransaction_orphan(
        round_txs.flood_tx.hexstr, 0, 0, active_sink_pids
    )
    if cfg.flood_wait_sec > 0:
        await asyncio.sleep(cfg.flood_wait_sec)

    # Step 2.4: Send parent_txs[i] 1-to-1 to active_sources[i] in a single batch
    parent_batch_calls = [
        ("sendrawtransaction_orphan", ptx.hexstr, 0, 0, [pid])
        for ptx, pid in zip(active_parent_txs, active_source_pids)
    ]
    await probe_0.call_batch(parent_batch_calls, raise_on_error=False)
    if cfg.parent_wait_sec > 0:
        await asyncio.sleep(cfg.parent_wait_sec)

    # Step 2.5: Clear INVBLOCK state, Clear Log #1, and send marker_txs[i] 1-to-1
    await probe_0.clearinv_probe()
    clear_log_file(probe_0_log_path)

    marker_batch_calls = [
        ("sendrawtransaction_orphan", mtx.hexstr, 0, 0, [pid])
        for mtx, pid in zip(active_marker_txs, active_source_pids)
    ]
    await probe_0.call_batch(marker_batch_calls, raise_on_error=False)
    if cfg.marker_propagation_wait_sec > 0:
        await asyncio.sleep(cfg.marker_propagation_wait_sec)

    # Parse Step 2.5 log to check if any source node requested GETDATA for its own parent_txs[i]
    parent_getdata_by_addr = parse_getdata_by_tx_from_log(
        probe_0_log_path, active_parent_txs, start_id_to_addr
    )

    # Step 2.6: Clear Log #2 and announce marker_txs to all active peers
    clear_log_file(probe_0_log_path)
    marker_hexes = [mtx.hexstr for mtx in active_marker_txs]
    await probe_0.sendinv_orphan(marker_hexes, all_active_pids)
    if cfg.getdata_wait_sec > 0:
        await asyncio.sleep(cfg.getdata_wait_sec)

    # Step 2.7: Verify end-of-round peer connectivity and parse marker GETDATA responses
    end_peer_info = await probe_0.getpeerinfo()
    end_addr_to_id, end_id_to_addr = extract_eligible_peer_maps(end_peer_info)
    combined_id_to_addr = {**start_id_to_addr, **end_id_to_addr}

    for node in (*active_sources, *active_sinks):
        if node.addr not in end_addr_to_id:
            dropped_in_round.append(node)

    dropped_set = set(dropped_in_round)

    marker_getdata_by_addr = parse_getdata_by_tx_from_log(
        probe_0_log_path, active_marker_txs, combined_id_to_addr
    )

    malfunctioning_set = detect_malfunctioning_sources(
        active_sources, parent_getdata_by_addr, marker_getdata_by_addr
    )
    if malfunctioning_set:
        log.warning(
            "Round %d: detected %d malfunctioning source node(s) via log: %s",
            round_txs.round_index,
            len(malfunctioning_set),
            [n.addr for n in malfunctioning_set],
        )

    valid_source_indices = [
        idx
        for idx, src in enumerate(active_sources)
        if src not in malfunctioning_set and src not in dropped_set
    ]
    valid_sinks = [sink for sink in active_sinks if sink not in dropped_set]

    tested_pairs: set[tuple[str, str]] = set()
    discarded_pairs: set[tuple[str, str]] = set()
    requested_markers_by_sink: dict[str, tuple[int, ...]] = {}

    for sink in valid_sinks:
        req_indices = sorted(marker_getdata_by_addr.get(sink.addr, set()))
        requested_markers_by_sink[sink.addr] = tuple(req_indices)
        req_set = set(req_indices)

        for idx in valid_source_indices:
            src = active_sources[idx]
            edge = canonical_edge(src.addr, sink.addr)
            tested_pairs.add(edge)
            if idx in req_set:
                discarded_pairs.add(edge)

    # Step 2.8: Post-Round Orphanage Cleanup
    await probe_0.clearinv_probe()
    end_all_active_pids = [
        end_addr_to_id[n.addr]
        for n in (*active_sources, *active_sinks)
        if n.addr in end_addr_to_id
    ]
    cleanup_calls = build_cleanup_batch_calls(
        active_sources=active_sources,
        active_parent_txs=active_parent_txs,
        flood_tx=round_txs.flood_tx,
        addr_to_id=end_addr_to_id,
        all_active_peer_ids=end_all_active_pids,
    )
    if cleanup_calls:
        await probe_0.call_batch(cleanup_calls, raise_on_error=False)
        if cfg.cleanup_wait_sec > 0:
            await asyncio.sleep(cfg.cleanup_wait_sec)

    clear_log_file(probe_0_log_path)

    surviving_sources = tuple(
        s for s in active_sources if s not in malfunctioning_set and s not in dropped_set
    )
    malfunctioning_ordered = tuple(
        s for s in active_sources if s in malfunctioning_set
    )
    unique_dropped = tuple(dict.fromkeys(dropped_in_round))

    round_result = RoundExecutionResult(
        round_index=round_txs.round_index,
        active_sources=surviving_sources,
        active_sinks=tuple(valid_sinks),
        malfunctioning_sources=malfunctioning_ordered,
        dropped_nodes=unique_dropped,
        requested_markers_by_sink=MappingProxyType(requested_markers_by_sink),
        tested_pairs_count=len(tested_pairs),
        discarded_edges_count=len(discarded_pairs),
    )
    return round_result, tested_pairs, discarded_pairs


async def run_txprobe_execution(
    crafting_result: TxProbeCraftingResult,
    probe_0: AsyncBitcoinRpc,
    probe_0_log_path: str | Path,
    config: TxProbeExecutionConfig | None = None,
    progress_callback: Callable[[str, float], None] | None = None,
    checkpoint_path: str | Path | None = None,
) -> TxProbeExecutionResult:
    """Execute the complete Step 4 TxProbe loop across all pre-crafted rounds.

    Uses Method 2 (Complete Graph K_V -> Discard on GETDATA):
    1. Starts with all distinct pairs {u, v} in snapshot.nodes as candidate edges.
    2. In each round r, any pair {s_i, k_j} where sink k_j sends GETDATA for
       marker_txs[i] is permanently discarded from candidate_edges.
    3. Any node that disconnects or malfunctions (rejects its own parent_txs[i]
       and requests it via orphan resolution) is recorded and pruned from both
       inferred_snapshot and filtered_groundtruth_snapshot.
    4. Only pairs tested in at least 1 round and never discarded are retained
       in the final inferred GraphSnapshot.
    """
    cfg = config or TxProbeExecutionConfig()
    initial_snapshot = crafting_result.snapshot
    all_nodes = list(initial_snapshot.nodes)
    total_rounds = len(crafting_result.rounds)

    log.info(
        "Starting Step 4 TxProbe Execution: %d nodes, %d rounds",
        len(all_nodes),
        total_rounds,
    )

    # 1. Initialize Complete Graph (K_V) candidate edge set
    candidate_edges: set[tuple[str, str]] = set()
    for i in range(len(all_nodes)):
        for j in range(i + 1, len(all_nodes)):
            candidate_edges.add(canonical_edge(all_nodes[i].addr, all_nodes[j].addr))

    tested_pairs: set[tuple[str, str]] = set()
    all_malfunctioning: list[NodeIdentity] = []
    all_dropped: list[NodeIdentity] = []
    excluded_nodes: set[NodeIdentity] = set()
    round_results: list[RoundExecutionResult] = []

    for idx, round_txs in enumerate(crafting_result.rounds):
        if progress_callback:
            progress_callback(
                f"Round {idx + 1}/{total_rounds} (sources={ len(round_txs.source_nodes) })",
                idx / max(1, total_rounds),
            )

        round_res, r_tested, r_discarded = await execute_single_round(
            round_txs=round_txs,
            probe_0=probe_0,
            probe_0_log_path=probe_0_log_path,
            config=cfg,
            excluded_nodes=excluded_nodes,
        )
        round_results.append(round_res)

        tested_pairs.update(r_tested)
        candidate_edges.difference_update(r_discarded)

        for m_node in round_res.malfunctioning_sources:
            if m_node not in excluded_nodes:
                all_malfunctioning.append(m_node)
                excluded_nodes.add(m_node)

        for d_node in round_res.dropped_nodes:
            if d_node not in excluded_nodes:
                all_dropped.append(d_node)
                excluded_nodes.add(d_node)

        log.info(
            "Round %d/%d complete: tested=%d pairs, discarded=%d edges, remaining_candidates=%d",
            idx + 1,
            total_rounds,
            round_res.tested_pairs_count,
            round_res.discarded_edges_count,
            len(candidate_edges & tested_pairs),
        )

        if checkpoint_path is not None:
            surviving_now = [n for n in all_nodes if n not in excluded_nodes]
            inferred_now = build_inferred_snapshot_from_edges(
                surviving_now, candidate_edges & tested_pairs
            )
            filtered_gt_now = initial_snapshot.remove_nodes(excluded_nodes)
            partial_stats = TxProbeExecutionStats(
                total_rounds=total_rounds,
                completed_rounds=idx + 1,
                initial_nodes_count=len(all_nodes),
                surviving_nodes_count=inferred_now.num_nodes,
                malfunctioning_nodes_count=len(all_malfunctioning),
                dropped_nodes_count=len(all_dropped),
                total_tested_pairs=len(tested_pairs),
                inferred_edges_count=inferred_now.num_edges,
                filtered_groundtruth_edges_count=filtered_gt_now.num_edges,
            )
            partial_res = TxProbeExecutionResult(
                inferred_snapshot=inferred_now,
                filtered_groundtruth_snapshot=filtered_gt_now,
                malfunctioning_nodes=tuple(all_malfunctioning),
                dropped_nodes=tuple(all_dropped),
                round_results=tuple(round_results),
                stats=partial_stats,
            )
            partial_res.save(checkpoint_path)

    surviving_nodes = [n for n in all_nodes if n not in excluded_nodes]
    final_edges = candidate_edges & tested_pairs

    inferred_snapshot = build_inferred_snapshot_from_edges(surviving_nodes, final_edges)
    filtered_gt_snapshot = initial_snapshot.remove_nodes(excluded_nodes)

    if progress_callback:
        progress_callback("Completed Step 4 TxProbe Execution", 1.0)

    stats = TxProbeExecutionStats(
        total_rounds=total_rounds,
        completed_rounds=len(round_results),
        initial_nodes_count=len(all_nodes),
        surviving_nodes_count=inferred_snapshot.num_nodes,
        malfunctioning_nodes_count=len(all_malfunctioning),
        dropped_nodes_count=len(all_dropped),
        total_tested_pairs=len(tested_pairs),
        inferred_edges_count=inferred_snapshot.num_edges,
        filtered_groundtruth_edges_count=filtered_gt_snapshot.num_edges,
    )

    log.info(
        "Step 4 TxProbe finished: %d/%d surviving nodes (%d malfunctioning, %d dropped), "
        "%d inferred edges, %d filtered groundtruth edges",
        stats.surviving_nodes_count,
        stats.initial_nodes_count,
        stats.malfunctioning_nodes_count,
        stats.dropped_nodes_count,
        stats.inferred_edges_count,
        stats.filtered_groundtruth_edges_count,
    )

    return TxProbeExecutionResult(
        inferred_snapshot=inferred_snapshot,
        filtered_groundtruth_snapshot=filtered_gt_snapshot,
        malfunctioning_nodes=tuple(all_malfunctioning),
        dropped_nodes=tuple(all_dropped),
        round_results=tuple(round_results),
        stats=stats,
    )
