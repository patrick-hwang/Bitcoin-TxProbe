"""Continuous P2P Ingress Event Monitor & Subgraph Snapshotter.

Implements Role 2 (The Prober) using Probes 0 and 1 to monitor block announcements,
track exact arrival timestamps for every node, and dynamically generate subgraph snapshots
at continuous or discrete intervals (e.g. 10ms).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any

# Add project root and module to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
for p in (TXPROBE_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from txprobe.rpc.client import AsyncBitcoinRpc

try:
    from .config import DEFAULT_RESULTS_DIR, ExperimentConfig, compute_bfs_distances, load_topology
except ImportError:
    from config import DEFAULT_RESULTS_DIR, ExperimentConfig, compute_bfs_distances, load_topology

log = logging.getLogger("snapshot_fork.prober")


@dataclass(frozen=True)
class BlockArrivalEvent:
    """Raw observation of a block announcement from a target node."""
    timestamp: float
    node_id: int
    block_hash: str
    probe_id: int
    message_type: str = "inv"

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": self.timestamp,
            "node_id": self.node_id,
            "block_hash": self.block_hash,
            "probe_id": self.probe_id,
            "message_type": self.message_type,
        }


@dataclass
class NodeTimingInfo:
    """Arrival timings for tracked blocks on an individual node."""
    node_id: int
    hop_distance_from_forker: int = -1
    block_received_at: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hop_distance_from_forker": self.hop_distance_from_forker,
            "block_received_at": dict(self.block_received_at),
        }


@dataclass(frozen=True)
class SubgraphSnapshot:
    """Discrete state snapshot representing the network subgraph distribution at time t."""
    snapshot_index: int
    rel_time_ms: float
    timestamp: float
    subgraphs: dict[str, list[int]]
    subgraph_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_index": self.snapshot_index,
            "rel_time_ms": round(self.rel_time_ms, 2),
            "timestamp": round(self.timestamp, 6),
            "subgraphs": self.subgraphs,
            "subgraph_counts": self.subgraph_counts,
        }


class SubgraphTracker:
    """Stateful engine tracking block arrivals across 1000 nodes and generating snapshots."""

    def __init__(
        self,
        height: int,
        parent_hash: str,
        fork_block_hashes: dict[str, str],  # {"B1": hash1, "B2": hash2, "B3": hash3}
        target_node_ids: list[int] | None = None,
        hop_distances: dict[int, int] | None = None,
    ) -> None:
        self.height = height
        self.parent_hash = parent_hash
        self.fork_block_hashes = fork_block_hashes
        self.b1_hash = fork_block_hashes.get("B1", "")
        self.b2_hash = fork_block_hashes.get("B2", "")
        self.b3_hash = fork_block_hashes.get("B3", "")

        self.target_node_ids = target_node_ids or list(range(2, 1002))
        self.hop_distances = hop_distances or {}

        # Matrix: node_id -> NodeTimingInfo
        self.timings: dict[int, NodeTimingInfo] = {
            nid: NodeTimingInfo(
                node_id=nid,
                hop_distance_from_forker=self.hop_distances.get(nid, -1),
            )
            for nid in self.target_node_ids
        }

        # Chronological event log
        self.event_log: list[BlockArrivalEvent] = []

    def record_event(
        self,
        node_id: int,
        block_hash: str,
        timestamp: float | None = None,
        probe_id: int = 0,
        message_type: str = "inv",
    ) -> BlockArrivalEvent:
        """Record a block arrival observation from a target node."""
        if timestamp is None:
            timestamp = time.time()

        event = BlockArrivalEvent(
            timestamp=timestamp,
            node_id=node_id,
            block_hash=block_hash,
            probe_id=probe_id,
            message_type=message_type,
        )
        self.event_log.append(event)

        # Update node matrix if first time seeing this block on this node
        if node_id in self.timings:
            node_timing = self.timings[node_id]
            if block_hash not in node_timing.block_received_at:
                node_timing.block_received_at[block_hash] = timestamp

        return event

    def get_node_active_tip(self, node_id: int, t: float) -> str:
        """Determine which block node_id considers active at continuous timestamp t.

        Consensus rules applied:
        1. If B3 (reorg extension) has arrived at or before t, active tip is B3 (heavier work).
        2. Else if both B1 and B2 have arrived at or before t:
           - First-seen rule: earlier block arrival wins.
        3. Else if only B1 has arrived <= t, active tip is B1.
        4. Else if only B2 has arrived <= t, active tip is B2.
        5. If neither has arrived <= t, active tip is parent_hash.
        """
        node_timing = self.timings.get(node_id)
        if not node_timing:
            return self.parent_hash

        rec = node_timing.block_received_at
        t_b1 = rec.get(self.b1_hash)
        t_b2 = rec.get(self.b2_hash)
        t_b3 = rec.get(self.b3_hash)

        # Rule 1: Heavier chainwork (B3 at height H+2)
        if t_b3 is not None and t >= t_b3:
            return self.b3_hash

        # Rule 2: Competing blocks at height H+1
        b1_active = t_b1 is not None and t >= t_b1
        b2_active = t_b2 is not None and t >= t_b2

        if b1_active and b2_active:
            # First-seen tiebreaker
            return self.b1_hash if t_b1 <= t_b2 else self.b2_hash
        elif b1_active:
            return self.b1_hash
        elif b2_active:
            return self.b2_hash

        # Rule 3: Prior chain
        return self.parent_hash

    def get_subgraphs_at(self, t: float, snapshot_index: int = 0, rel_origin_t: float | None = None) -> SubgraphSnapshot:
        """Construct full subgraph partition of the network at continuous timestamp t."""
        if rel_origin_t is None:
            rel_origin_t = self.event_log[0].timestamp if self.event_log else t

        rel_time_ms = round((t - rel_origin_t) * 1000.0, 3)

        # Subgraph buckets: map block_hash -> list of node IDs
        subgraphs: dict[str, list[int]] = {
            self.parent_hash: [],
            self.b1_hash: [],
            self.b2_hash: [],
            self.b3_hash: [],
        }

        for nid in self.target_node_ids:
            tip = self.get_node_active_tip(nid, t)
            if tip not in subgraphs:
                subgraphs[tip] = []
            subgraphs[tip].append(nid)

        counts = {block: len(nodes) for block, nodes in subgraphs.items()}

        return SubgraphSnapshot(
            snapshot_index=snapshot_index,
            rel_time_ms=rel_time_ms,
            timestamp=round(t, 6),
            subgraphs=subgraphs,
            subgraph_counts=counts,
        )

    def get_convergence_time(self, block_hash: str) -> float | None:
        """Return the timestamp when 100% of target nodes received block_hash, or None if not fully converged."""
        rec_times: list[float] = []
        for nid in self.target_node_ids:
            node_timing = self.timings.get(nid)
            if not node_timing:
                return None
            t = node_timing.block_received_at.get(block_hash)
            if t is None:
                return None
            rec_times.append(t)
        return max(rec_times) if rec_times else None

    def generate_sliced_snapshots(
        self,
        start_time: float,
        end_time: float,
        step_ms: float = 10.0,
        stop_on_convergence_hash: str | None = None,
    ) -> list[SubgraphSnapshot]:
        """Slice the continuous timeline into discrete snapshots with step_ms intervals.

        If stop_on_convergence_hash is provided, snapshot generation stops immediately
        after recording the first snapshot in which 100% of target nodes have converged
        on that block, preventing redundant identical trailing snapshots.
        """
        if end_time < start_time:
            raise ValueError(f"end_time ({end_time}) cannot be earlier than start_time ({start_time})")

        step_sec = step_ms / 1000.0
        snapshots: list[SubgraphSnapshot] = []
        total_targets = len(self.target_node_ids)

        idx = 0
        while True:
            curr_t = round(start_time + idx * step_sec, 6)
            if curr_t > end_time + 1e-6:
                break
            snap = self.get_subgraphs_at(curr_t, snapshot_index=idx, rel_origin_t=start_time)
            snapshots.append(snap)

            # Check if 100% of target nodes have adopted stop_on_convergence_hash
            if stop_on_convergence_hash and snap.subgraph_counts.get(stop_on_convergence_hash, 0) == total_targets:
                log.info(
                    "100%% convergence reached on %s at snapshot index %d (%.1f ms). Stopping snapshot generation.",
                    stop_on_convergence_hash[:16], idx, snap.rel_time_ms
                )
                break

            idx += 1

        return snapshots

    def export_to_json(
        self,
        out_path: Path,
        fork_metadata: dict[str, Any] | None = None,
        snapshots: list[SubgraphSnapshot] | None = None,
        step_ms: float = 10.0,
    ) -> None:
        """Export the complete arrival timings, event log, and snapshots to JSON."""
        if snapshots is None:
            if self.event_log:
                start_t = self.event_log[0].timestamp
                end_t = self.event_log[-1].timestamp
                snapshots = self.generate_sliced_snapshots(start_t, end_t, step_ms=step_ms)
            else:
                snapshots = []

        data = {
            "height": self.height,
            "parent_block_hash": self.parent_hash,
            "fork_blocks": self.fork_block_hashes,
            "fork_metadata": fork_metadata or {},
            "total_nodes": len(self.target_node_ids),
            "snapshot_interval_ms": step_ms,
            "node_timings": {
                str(nid): info.to_dict() for nid, info in sorted(self.timings.items())
            },
            "event_log": [e.to_dict() for e in self.event_log],
            "snapshots": [s.to_dict() for s in snapshots],
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        log.info("Saved fork subgraph snapshots to %s (%d snapshots)", out_path, len(snapshots))


def create_subgraph_tracker_from_config(
    height: int,
    parent_hash: str,
    b1_hash: str,
    b2_hash: str,
    b3_hash: str,
    config: ExperimentConfig | None = None,
) -> SubgraphTracker:
    """Factory helper to instantiate SubgraphTracker initialized with topology distances."""
    if config is None:
        config = ExperimentConfig()

    adj = load_topology(config.topology_path)
    distances = compute_bfs_distances(adj, config.forker_id)
    target_ids = list(range(2, 2 + config.num_target_nodes))

    return SubgraphTracker(
        height=height,
        parent_hash=parent_hash,
        fork_block_hashes={
            "B1": b1_hash,
            "B2": b2_hash,
            "B3": b3_hash,
        },
        target_node_ids=target_ids,
        hop_distances=distances,
    )
