"""Unit tests for continuous P2P ingress event monitor and subgraph snapshotter."""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Add project root and module to path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
for p in (TXPROBE_DIR, CURRENT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest
from prober import (
    BlockArrivalEvent,
    NodeTimingInfo,
    SubgraphSnapshot,
    SubgraphTracker,
    create_subgraph_tracker_from_config,
)


def test_event_recording_and_idempotence() -> None:
    """Verify recording block arrival events updates matrix and ignores duplicate later arrivals."""
    tracker = SubgraphTracker(
        height=100,
        parent_hash="parent_mock",
        fork_block_hashes={"B1": "b1_mock", "B2": "b2_mock", "B3": "b3_mock"},
        target_node_ids=[2, 3, 4],
        hop_distances={2: 0, 3: 1, 4: 2},
    )

    t0 = 1000.0
    tracker.record_event(node_id=2, block_hash="b1_mock", timestamp=t0, probe_id=0)

    # First arrival recorded
    assert tracker.timings[2].block_received_at["b1_mock"] == t0
    assert len(tracker.event_log) == 1

    # Duplicate arrival later (e.g. from probe 1)
    tracker.record_event(node_id=2, block_hash="b1_mock", timestamp=t0 + 0.05, probe_id=1)
    assert len(tracker.event_log) == 2
    # Matrix keeps original earliest arrival time
    assert tracker.timings[2].block_received_at["b1_mock"] == t0


def test_active_tip_consensus_transitions() -> None:
    """Verify state transitions: parent -> B1 -> (ignore equal B2) -> reorg to heavier B3."""
    tracker = SubgraphTracker(
        height=100,
        parent_hash="parent_mock",
        fork_block_hashes={"B1": "b1_mock", "B2": "b2_mock", "B3": "b3_mock"},
        target_node_ids=[10],
    )

    t_b1 = 1000.100  # B1 arrives at 100ms
    t_b2 = 1000.200  # B2 arrives at 200ms
    t_b3 = 1000.300  # B3 arrives at 300ms

    tracker.record_event(node_id=10, block_hash="b1_mock", timestamp=t_b1)
    tracker.record_event(node_id=10, block_hash="b2_mock", timestamp=t_b2)
    tracker.record_event(node_id=10, block_hash="b3_mock", timestamp=t_b3)

    # 1. Before B1 arrived (t=50ms) -> parent_mock
    assert tracker.get_node_active_tip(10, 1000.050) == "parent_mock"

    # 2. At B1 arrival (t=100ms) -> b1_mock
    assert tracker.get_node_active_tip(10, 1000.100) == "b1_mock"

    # 3. After B2 arrived but before B3 (t=250ms) -> still b1_mock (first seen tiebreaker)
    assert tracker.get_node_active_tip(10, 1000.250) == "b1_mock"

    # 4. At B3 arrival (t=300ms) -> reorg to b3_mock
    assert tracker.get_node_active_tip(10, 1000.300) == "b3_mock"

    # 5. Long after B3 arrival (t=500ms) -> remains b3_mock
    assert tracker.get_node_active_tip(10, 1000.500) == "b3_mock"


def test_subgraph_snapshot_partitioning() -> None:
    """Verify network partitioning across nodes into distinct subgraphs."""
    tracker = SubgraphTracker(
        height=100,
        parent_hash="parent_mock",
        fork_block_hashes={"B1": "b1_mock", "B2": "b2_mock", "B3": "b3_mock"},
        target_node_ids=[2, 3, 4],
    )

    # Node 2 receives B1 at t=1.0, B3 at t=3.0
    tracker.record_event(node_id=2, block_hash="b1_mock", timestamp=1.0)
    tracker.record_event(node_id=2, block_hash="b3_mock", timestamp=3.0)

    # Node 3 receives B1 at t=1.5
    tracker.record_event(node_id=3, block_hash="b1_mock", timestamp=1.5)

    # Node 4 receives nothing yet

    # At t=0.5: All 3 nodes are on parent
    snap_0 = tracker.get_subgraphs_at(0.5)
    assert snap_0.subgraph_counts["parent_mock"] == 3
    assert snap_0.subgraph_counts["b1_mock"] == 0

    # At t=1.2: Node 2 is on B1, Nodes 3 and 4 on parent
    snap_1 = tracker.get_subgraphs_at(1.2)
    assert snap_1.subgraphs["b1_mock"] == [2]
    assert sorted(snap_1.subgraphs["parent_mock"]) == [3, 4]

    # At t=2.0: Nodes 2 and 3 on B1, Node 4 on parent
    snap_2 = tracker.get_subgraphs_at(2.0)
    assert sorted(snap_2.subgraphs["b1_mock"]) == [2, 3]
    assert snap_2.subgraphs["parent_mock"] == [4]

    # At t=3.5: Node 2 on B3, Node 3 on B1, Node 4 on parent
    snap_3 = tracker.get_subgraphs_at(3.5)
    assert snap_3.subgraphs["b3_mock"] == [2]
    assert snap_3.subgraphs["b1_mock"] == [3]
    assert snap_3.subgraphs["parent_mock"] == [4]


def test_sliced_snapshots_10ms_generation() -> None:
    """Verify slicing timeline with exact 10ms discrete time intervals."""
    tracker = SubgraphTracker(
        height=100,
        parent_hash="parent_mock",
        fork_block_hashes={"B1": "b1_mock", "B2": "b2_mock", "B3": "b3_mock"},
        target_node_ids=[2, 3],
    )

    t_start = 1000.000
    t_end = 1000.100  # 100ms total duration -> 11 snapshots at 0, 10, 20, ..., 100ms

    snapshots = tracker.generate_sliced_snapshots(start_time=t_start, end_time=t_end, step_ms=10.0)
    assert len(snapshots) == 11
    assert snapshots[0].rel_time_ms == 0.0
    assert snapshots[1].rel_time_ms == 10.0
    assert snapshots[10].rel_time_ms == 100.0


def test_export_to_json(tmp_path: Path) -> None:
    """Verify exporting result schema to JSON file."""
    tracker = SubgraphTracker(
        height=102,
        parent_hash="parent_mock_hash",
        fork_block_hashes={"B1": "b1_mock", "B2": "b2_mock", "B3": "b3_mock"},
        target_node_ids=[2, 3],
        hop_distances={2: 0, 3: 1},
    )

    tracker.record_event(node_id=2, block_hash="b1_mock", timestamp=10.0)
    tracker.record_event(node_id=3, block_hash="b1_mock", timestamp=10.02)

    out_file = tmp_path / "fork_subgraph_height_102.json"
    tracker.export_to_json(out_file, step_ms=10.0)

    assert out_file.exists()
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["height"] == 102
    assert data["parent_block_hash"] == "parent_mock_hash"
    assert "node_timings" in data
    assert data["node_timings"]["2"]["hop_distance_from_forker"] == 0
    assert data["node_timings"]["3"]["hop_distance_from_forker"] == 1
    assert len(data["event_log"]) == 2
    assert len(data["snapshots"]) >= 2


def test_create_subgraph_tracker_from_config() -> None:
    """Verify factory initializes tracker with all 1000 target nodes and BFS hop distances."""
    tracker = create_subgraph_tracker_from_config(
        height=100,
        parent_hash="mock_parent",
        b1_hash="mock_b1",
        b2_hash="mock_b2",
        b3_hash="mock_b3",
    )

    assert len(tracker.target_node_ids) == 1000
    assert 2 in tracker.timings
    assert 1001 in tracker.timings
    assert tracker.timings[2].hop_distance_from_forker == 0
    assert tracker.timings[1001].hop_distance_from_forker > 0
