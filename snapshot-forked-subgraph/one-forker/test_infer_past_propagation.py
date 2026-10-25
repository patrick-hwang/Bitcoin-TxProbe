"""Unit tests for backward block propagation inference and snapshot evaluation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
for p in (CURRENT_DIR, TXPROBE_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import DEFAULT_INFERRED_TOPOLOGY_PATH, DEFAULT_RESULTS_DIR, DEFAULT_TOPOLOGY_PATH, load_topology
from infer_past_propagation import (
    BlockPropagationSnapshot,
    InferenceMetrics,
    compare_topologies_evaluation,
    compute_metrics,
    evaluate_inference,
    evaluate_snapshot_data,
    extract_known_nodes,
    generate_block_propagation_snapshots,
    get_propagation_snapshot_at,
    infer_past_block_propagation_snapshot,
    infer_past_propagation,
    resolve_target_block_hash,
)


def test_backward_propagation_line_graph() -> None:
    """Line graph: 1 - 2 - 3 - 4 - 5.

    If at time t, node 4 and 5 are unknown:
    Neighbors of 4: {3, 5}.
    Neighbors of 5: {4}.
    At time (t - delta): {3, 4, 5} must be unknown.
    Nodes {1, 2} are inferred known.
    """
    adjacency = {
        1: [2],
        2: [1, 3],
        3: [2, 4],
        4: [3, 5],
        5: [4],
    }
    known_t = {1, 2, 3}
    all_nodes = [1, 2, 3, 4, 5]

    inferred_known, inferred_unknown = infer_past_propagation(known_t, adjacency, all_nodes)
    assert inferred_known == {1, 2}
    assert inferred_unknown == {3, 4, 5}


def test_backward_propagation_all_known_and_all_unknown() -> None:
    """Verify boundary conditions: all known and all unknown."""
    adjacency = {
        1: [2],
        2: [1, 3],
        3: [2],
    }
    all_nodes = [1, 2, 3]

    # All known at t
    inf_k, inf_u = infer_past_propagation([1, 2, 3], adjacency, all_nodes)
    assert inf_k == {1, 2, 3}
    assert inf_u == set()

    # All unknown at t
    inf_k, inf_u = infer_past_propagation([], adjacency, all_nodes)
    assert inf_k == set()
    assert inf_u == {1, 2, 3}


def test_backward_propagation_star_graph() -> None:
    """Star graph: Center 0 connected to 1, 2, 3, 4."""
    adjacency = {
        0: [1, 2, 3, 4],
        1: [0],
        2: [0],
        3: [0],
        4: [0],
    }
    all_nodes = [0, 1, 2, 3, 4]

    # If center 0 is unknown, all leaves become unknown
    inf_k, inf_u = infer_past_propagation([1, 2, 3, 4], adjacency, all_nodes)
    assert inf_k == set()
    assert inf_u == {0, 1, 2, 3, 4}

    # If leaf 1 is unknown, center 0 becomes unknown, but leaves 2, 3, 4 have all known neighbors {0} at t?
    # Leaf 1 unknown -> 1 and its neighbor 0 become unknown.
    # Leaves 2, 3, 4 were known at t, but are their neighbors unknown? Leaf 2's neighbor is 0, which is in inferred_unknown!
    # Wait: U_inferred = U_t U N(U_t). U_t = {1}. N(1) = {0}.
    # So U_inferred = {1, 0}.
    # K_inferred = {2, 3, 4}!
    inf_k, inf_u = infer_past_propagation([0, 2, 3, 4], adjacency, all_nodes)
    assert inf_u == {1, 0}
    assert inf_k == {2, 3, 4}


def test_compute_metrics_various_cases() -> None:
    """Verify metric calculations for perfect, partial, and empty sets."""
    all_nodes = set(range(10))

    # Case 1: Perfect match with 4 positives
    y_true = {0, 1, 2, 3}
    y_pred = {0, 1, 2, 3}
    tp, fp, tn, fn, acc, prec, rec, f1 = compute_metrics(y_true, y_pred, all_nodes)
    assert tp == 4
    assert fp == 0
    assert fn == 0
    assert tn == 6
    assert acc == 1.0
    assert prec == 1.0
    assert rec == 1.0
    assert f1 == 1.0

    # Case 2: Zero positives true, zero positives predicted
    tp, fp, tn, fn, acc, prec, rec, f1 = compute_metrics(set(), set(), all_nodes)
    assert tp == 0 and fp == 0 and fn == 0 and tn == 10
    assert acc == 1.0
    assert prec == 1.0
    assert rec == 1.0
    assert f1 == 1.0

    # Case 3: Partial overlap
    y_true = {1, 2, 3}  # 3 positives
    y_pred = {2, 3, 4}  # 3 positives
    # TP={2,3} (2), FP={4} (1), FN={1} (1), TN={0,5,6,7,8,9} (6)
    tp, fp, tn, fn, acc, prec, rec, f1 = compute_metrics(y_true, y_pred, all_nodes)
    assert tp == 2
    assert fp == 1
    assert fn == 1
    assert tn == 6
    assert acc == 0.8
    assert prec == 2.0 / 3.0
    assert rec == 2.0 / 3.0
    assert round(f1, 4) == round(2.0 / 3.0, 4)


def test_infer_past_block_propagation_snapshot() -> None:
    """Verify snapshot object creation and metadata during past inference."""
    curr_snap = BlockPropagationSnapshot(
        snapshot_index=5,
        rel_time_ms=50.0,
        timestamp=1000.050,
        target_block_hash="target_hash_mock",
        known_nodes=[1, 2, 3],
        unknown_nodes=[4, 5],
        total_nodes=5,
    )
    adjacency = {
        1: [2],
        2: [1, 3],
        3: [2, 4],
        4: [3, 5],
        5: [4],
    }

    inferred = infer_past_block_propagation_snapshot(
        current_snapshot=curr_snap,
        adjacency=adjacency,
        target_block_hash="target_hash_mock",
        delta_ms=10.0,
        all_nodes=[1, 2, 3, 4, 5],
    )

    assert inferred.is_inferred is True
    assert inferred.source_snapshot_index == 5
    assert inferred.snapshot_index == 4
    assert inferred.rel_time_ms == 40.0
    assert inferred.timestamp == 1000.040
    assert inferred.known_nodes == [1, 2]
    assert inferred.unknown_nodes == [3, 4, 5]

    d = inferred.to_dict()
    assert d["is_inferred"] is True
    assert d["known_count"] == 2
    assert d["unknown_count"] == 3


def test_get_propagation_snapshot_at_from_timings() -> None:
    """Verify slicing continuous node_timings into discrete BlockPropagationSnapshots."""
    node_timings = {
        1: {"block_received_at": {"b_mock": 100.0}},
        2: {"block_received_at": {"b_mock": 100.010}},
        3: {"block_received_at": {"b_mock": 100.020}},
        4: {"block_received_at": {}},
    }

    # At t=100.005 -> only node 1 knows
    snap1 = get_propagation_snapshot_at(
        node_timings=node_timings,
        target_block_hash="b_mock",
        t=100.005,
        snapshot_index=0,
        rel_origin_t=100.0,
        all_nodes=[1, 2, 3, 4],
    )
    assert snap1.known_nodes == [1]
    assert snap1.unknown_nodes == [2, 3, 4]
    assert snap1.rel_time_ms == 5.0

    # At t=100.015 -> nodes 1 and 2 know
    snap2 = get_propagation_snapshot_at(
        node_timings=node_timings,
        target_block_hash="b_mock",
        t=100.015,
        snapshot_index=1,
        rel_origin_t=100.0,
        all_nodes=[1, 2, 3, 4],
    )
    assert snap2.known_nodes == [1, 2]
    assert snap2.unknown_nodes == [3, 4]


def test_generate_block_propagation_snapshots() -> None:
    """Verify generating complete time series of snapshots."""
    node_timings = {
        1: {"block_received_at": {"b_mock": 100.0}},
        2: {"block_received_at": {"b_mock": 100.020}},
    }
    snaps = generate_block_propagation_snapshots(
        node_timings=node_timings,
        target_block_hash="b_mock",
        start_time=100.0,
        end_time=100.030,
        step_ms=10.0,
        all_nodes=[1, 2],
    )
    assert len(snaps) == 4  # 0ms, 10ms, 20ms, 30ms
    assert snaps[0].known_nodes == [1]
    assert snaps[1].known_nodes == [1]
    assert snaps[2].known_nodes == [1, 2]
    assert snaps[3].known_nodes == [1, 2]


def test_extract_known_nodes_prioritizes_timings() -> None:
    """Verify that node_timings override misleading consensus tip subgraphs."""
    subgraphs_mock = {"other_reorg_block": [1, 2]}
    node_timings_mock = {
        1: {"block_received_at": {"b1_mock": 1000.010}},
        2: {"block_received_at": {"b1_mock": 1000.010}},
    }
    snap_dict = {
        "timestamp": 1000.015,
        "subgraphs": subgraphs_mock,
    }

    # Without timings, target 'b1_mock' is not in subgraphs -> empty set
    known_without_timings = extract_known_nodes(snap_dict, "b1_mock", node_timings=None, all_nodes=[1, 2])
    assert known_without_timings == set()

    # With timings, both nodes received b1_mock before t=1000.015 -> {1, 2}
    known_with_timings = extract_known_nodes(snap_dict, "b1_mock", node_timings=node_timings_mock, all_nodes=[1, 2])
    assert known_with_timings == {1, 2}


def test_evaluate_inference() -> None:
    """Verify evaluating an inferred snapshot against a real snapshot."""
    inferred = BlockPropagationSnapshot(
        snapshot_index=1,
        rel_time_ms=10.0,
        timestamp=1000.010,
        target_block_hash="b_mock",
        known_nodes=[1],
        unknown_nodes=[2, 3],
        total_nodes=3,
        is_inferred=True,
        source_snapshot_index=2,
    )
    ground_truth = BlockPropagationSnapshot(
        snapshot_index=1,
        rel_time_ms=10.0,
        timestamp=1000.010,
        target_block_hash="b_mock",
        known_nodes=[1, 2],
        unknown_nodes=[3],
        total_nodes=3,
        is_inferred=False,
    )

    metrics = evaluate_inference(inferred, ground_truth, all_nodes=[1, 2, 3])
    # Real known: {1, 2}, Inferred known: {1}
    # TP={1} (1), FP={} (0), FN={2} (1), TN={3} (1)
    assert metrics.tp == 1
    assert metrics.fp == 0
    assert metrics.fn == 1
    assert metrics.tn == 1
    assert metrics.accuracy == 2.0 / 3.0
    assert metrics.precision == 1.0
    assert metrics.recall == 0.5
    assert round(metrics.f1_score, 4) == round(2.0 * 1.0 * 0.5 / 1.5, 4)


def test_resolve_target_block_hash() -> None:
    data = {
        "fork_blocks": {
            "B1": "4a1f000000000000000000000000000000000000000000000000000000000001",
            "B2": "7c9d000000000000000000000000000000000000000000000000000000000002",
        }
    }
    assert resolve_target_block_hash(data, "B1") == "4a1f000000000000000000000000000000000000000000000000000000000001"
    assert resolve_target_block_hash(data, "b2") == "7c9d000000000000000000000000000000000000000000000000000000000002"
    assert resolve_target_block_hash(data, "4a1f000000000000000000000000000000000000000000000000000000000001") == "4a1f000000000000000000000000000000000000000000000000000000000001"


def test_evaluate_snapshot_data_real_sample() -> None:
    """Verify evaluation on actual results/fork_subgraph_height_102.json and groundtruth topology."""
    results_file = DEFAULT_RESULTS_DIR / "fork_subgraph_height_102.json"
    if not results_file.exists() or not DEFAULT_TOPOLOGY_PATH.exists():
        pytest.skip("Sample data or topology file not found")

    with open(results_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    adjacency = load_topology(DEFAULT_TOPOLOGY_PATH)

    # Test single step 2 (20ms -> 10ms)
    res_step2 = evaluate_snapshot_data(data, adjacency, target_block="B1", step_index=2, use_timings_groundtruth=True)
    assert res_step2["total_steps_evaluated"] == 1
    m2 = res_step2["step_metrics"][0]
    assert m2["snapshot_index"] == 1
    assert m2["source_snapshot_index"] == 2
    assert m2["precision"] == 1.0  # Zero false positives in early propagation
    assert m2["recall"] > 0.0

    # Test all steps for B1
    res_all_b1 = evaluate_snapshot_data(data, adjacency, target_block="B1", step_index=None, use_timings_groundtruth=True)
    assert res_all_b1["total_steps_evaluated"] == len(data["snapshots"]) - 1
    mean_m1 = res_all_b1["mean_metrics"]
    assert 0.0 <= mean_m1["accuracy"] <= 1.0
    assert 0.0 <= mean_m1["precision"] <= 1.0
    assert 0.0 <= mean_m1["recall"] <= 1.0
    assert 0.0 <= mean_m1["f1_score"] <= 1.0

    # Test all steps for B2 (isolated fork block)
    res_all_b2 = evaluate_snapshot_data(data, adjacency, target_block="B2", step_index=None, use_timings_groundtruth=True)
    assert res_all_b2["total_steps_evaluated"] == len(data["snapshots"]) - 1
    mean_m2 = res_all_b2["mean_metrics"]
    assert mean_m2["accuracy"] > 0.99
    assert 0.0 <= mean_m2["precision"] <= 1.0
    assert 0.0 <= mean_m2["recall"] <= 1.0
    assert 0.0 <= mean_m2["f1_score"] <= 1.0

    # Test all steps for B3 (winning fork block)
    res_all_b3 = evaluate_snapshot_data(data, adjacency, target_block="B3", step_index=None, use_timings_groundtruth=True)
    assert res_all_b3["total_steps_evaluated"] == len(data["snapshots"]) - 1
    mean_m3 = res_all_b3["mean_metrics"]
    assert mean_m3["accuracy"] >= 0.94
    assert mean_m3["precision"] >= 0.80
    assert mean_m3["recall"] >= 0.80
    assert mean_m3["f1_score"] >= 0.80


def test_compare_topologies_evaluation() -> None:
    """Verify side-by-side comparison between Ground Truth and TxProbe Inferred topologies."""
    test_snapshot_file = DEFAULT_RESULTS_DIR / "fork_subgraph_height_102.json"
    if not (test_snapshot_file.exists() and DEFAULT_TOPOLOGY_PATH.exists() and DEFAULT_INFERRED_TOPOLOGY_PATH.exists()):
        pytest.skip("Snapshot or topology files not present for integration test")

    with open(test_snapshot_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    gt_adj = load_topology(DEFAULT_TOPOLOGY_PATH)
    inf_adj = load_topology(DEFAULT_INFERRED_TOPOLOGY_PATH)

    comp = compare_topologies_evaluation(data, gt_adj, inf_adj, target_block="B1")
    assert "groundtruth_topology" in comp
    assert "inferred_topology" in comp
    assert "comparison" in comp

    mean_gt = comp["comparison"]["mean_gt_metrics"]
    mean_inf = comp["comparison"]["mean_inferred_metrics"]
    diffs = comp["comparison"]["metric_differences_inf_minus_gt"]

    # Verify both topologies achieve high inference metrics
    assert mean_gt["accuracy"] >= 0.94
    assert mean_inf["accuracy"] >= 0.94
    assert abs(diffs["accuracy"]) < 0.05


def test_generate_block_propagation_snapshots_stop_on_convergence() -> None:
    """Verify generate_block_propagation_snapshots stops immediately when all nodes know block."""
    node_timings = {
        2: {"block_received_at": {"mock_block": 10.010}},
        3: {"block_received_at": {"mock_block": 10.020}},
    }
    all_snaps = generate_block_propagation_snapshots(
        node_timings=node_timings,
        target_block_hash="mock_block",
        start_time=10.0,
        end_time=10.100,
        step_ms=10.0,
        all_nodes=[2, 3],
        stop_on_convergence=False,
    )
    assert len(all_snaps) == 11

    stopped_snaps = generate_block_propagation_snapshots(
        node_timings=node_timings,
        target_block_hash="mock_block",
        start_time=10.0,
        end_time=10.100,
        step_ms=10.0,
        all_nodes=[2, 3],
        stop_on_convergence=True,
    )
    assert len(stopped_snaps) == 3
    assert len(stopped_snaps[-1].known_nodes) == 2


def test_snapshot_tracker_slicing_and_convergence(tmp_path: Path) -> None:
    """Verify SubgraphTracker generates discrete snapshots and stops immediately upon convergence."""
    from prober import SubgraphTracker

    b1_h = "00000000000000000000000000000000000000000000000000000000000000b1"
    b2_h = "00000000000000000000000000000000000000000000000000000000000000b2"
    b3_h = "00000000000000000000000000000000000000000000000000000000000000b3"

    tracker = SubgraphTracker(
        height=100,
        parent_hash="0000000000000000000000000000000000000000000000000000000000000000",
        fork_block_hashes={"B1": b1_h, "B2": b2_h, "B3": b3_h},
        target_node_ids=[2, 3, 4, 5],
    )

    t0 = 1000.0
    for nid in [2, 3, 4, 5]:
        tracker.record_event(nid, b1_h, timestamp=t0 + (nid * 0.01))

    # All nodes have b1_h by 1000.05
    snaps = tracker.generate_sliced_snapshots(
        start_time=t0,
        end_time=t0 + 0.10,
        step_ms=10.0,
        stop_on_convergence_hash=b1_h,
    )
    assert len(snaps) > 0
    # Last snapshot stopped when all nodes reached B1
    assert snaps[-1].subgraph_counts[b1_h] == 4


def test_end_to_end_evaluation_on_snapshot() -> None:
    """Evaluate backward inference on recorded snapshot and export comparison."""
    from config import DEFAULT_RESULTS_DIR, DEFAULT_TOPOLOGY_PATH, DEFAULT_INFERRED_TOPOLOGY_PATH, load_topology

    snapshot_path = DEFAULT_RESULTS_DIR / "fork_subgraph_live_run.json"
    if not snapshot_path.exists():
        snapshot_path = DEFAULT_RESULTS_DIR / "fork_subgraph_height_102.json"

    if not (snapshot_path.exists() and DEFAULT_TOPOLOGY_PATH.exists() and DEFAULT_INFERRED_TOPOLOGY_PATH.exists()):
        pytest.skip("Snapshot or topology files not found for end-to-end test")

    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    gt_adj = load_topology(DEFAULT_TOPOLOGY_PATH, symmetrize=True)
    inf_adj = load_topology(DEFAULT_INFERRED_TOPOLOGY_PATH, symmetrize=True)

    for blk in ["B1", "B2", "B3"]:
        comp = compare_topologies_evaluation(data, gt_adj, inf_adj, target_block=blk)
        label = comp["target_block_label"]

        # Export comparison JSON
        comp_out = DEFAULT_RESULTS_DIR / f"eval_comparison_{label}.json"
        with open(comp_out, "w", encoding="utf-8") as f:
            json.dump(comp, f, indent=2)

        # Export standard GT inference JSON
        inf_out = DEFAULT_RESULTS_DIR / f"eval_inference_{label}.json"
        with open(inf_out, "w", encoding="utf-8") as f:
            json.dump(comp["groundtruth_topology"], f, indent=2)

        assert comp_out.exists()
        assert inf_out.exists()

        if blk in ("B1", "B3"):
            assert comp["groundtruth_topology"]["mean_metrics"]["accuracy"] >= 0.94
            assert comp["inferred_topology"]["mean_metrics"]["accuracy"] >= 0.94


def test_delay_aware_edge_constraint_filters_slow_links() -> None:
    """Verify that edges with delay d(u, v) > delta_ms do NOT constrain neighbors."""
    adjacency = {
        1: [2],
        2: [1, 3],
        3: [2],
    }
    all_nodes = [1, 2, 3]
    known_t = {1, 2}  # Node 3 is unknown at time t
    delta_ms = 10.0

    # Case A: Unweighted (or edge delay <= delta_ms) -> node 3 constrains neighbor 2
    inf_k_unweighted, inf_u_unweighted = infer_past_propagation(known_t, adjacency, all_nodes)
    assert inf_k_unweighted == {1}
    assert inf_u_unweighted == {2, 3}

    # Case B: Delay-aware with edge (2, 3) = 15ms (> 10ms) -> node 3 does NOT constrain 2
    edge_delays = {
        (1, 2): 8.0,
        (2, 3): 15.0,
    }
    inf_k_delay, inf_u_delay = infer_past_propagation(
        current_known_nodes=known_t,
        adjacency=adjacency,
        all_nodes=all_nodes,
        edge_delays=edge_delays,
        delta_ms=delta_ms,
    )
    assert inf_k_delay == {1, 2}
    assert inf_u_delay == {3}


def test_dijkstra_earliest_arrival_time_lower_bound() -> None:
    """Verify Dijkstra lower bound marks distant nodes as unknown before physical arrival."""
    # Line graph: 1 - 2 - 3 - 4 with 10ms per link
    adjacency = {
        1: [2],
        2: [1, 3],
        3: [2, 4],
        4: [3],
    }
    all_nodes = [1, 2, 3, 4]
    edge_delays = {
        (1, 2): 10.0,
        (2, 3): 10.0,
        (3, 4): 10.0,
    }

    # At target time tau = 15.0ms from source 1:
    # dist(1, 1) = 0ms <= 15 -> can be known
    # dist(1, 2) = 10ms <= 15 -> can be known
    # dist(1, 3) = 20ms > 15 -> CANNOT be known
    # dist(1, 4) = 30ms > 15 -> CANNOT be known
    inf_k, inf_u = infer_past_propagation(
        current_known_nodes=[1, 2, 3, 4],
        adjacency=adjacency,
        all_nodes=all_nodes,
        edge_delays=edge_delays,
        delta_ms=10.0,
        source_node=1,
        target_rel_time_ms=15.0,
    )
    assert inf_k == {1, 2}
    assert inf_u == {3, 4}


def test_load_empirical_edge_delays_file() -> None:
    """Verify that default empirical live 30-round min delay file loads correctly."""
    from config import DEFAULT_EDGE_DELAYS_PATH, load_edge_delays

    if not DEFAULT_EDGE_DELAYS_PATH.exists():
        pytest.skip(f"Edge delays file {DEFAULT_EDGE_DELAYS_PATH} not generated yet")

    delays = load_edge_delays(DEFAULT_EDGE_DELAYS_PATH)
    assert len(delays) >= 3900  # 4005 total edges in 1000-node topology
    all_delays = list(delays.values())
    assert min(all_delays) >= 0.05
    assert max(all_delays) <= 100.0





