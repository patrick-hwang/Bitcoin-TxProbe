"""Unit tests for TxProbe Step 6 metric calculation and topology evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from txprobe.evaluation import (
    ComponentStats,
    ConfusionMatrix,
    DegreeStats,
    EvaluationReport,
    GlobalTopologyMetrics,
    PathStats,
    ValidationMetrics,
    compute_clustering_coefficient,
    compute_connected_components,
    compute_degree_stats,
    compute_global_topology_metrics,
    compute_groundtruth_metrics,
    compute_path_metrics,
    evaluate_reconciled_results,
    generate_markdown_report,
)
from txprobe.models.graph import GraphSnapshot
from txprobe.models.node import NodeIdentity


def test_validation_metrics_perfect_match():
    """Verify validation metrics when inferred edges perfectly match groundtruth."""
    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(1, 5))
    # Undirected square: (1,2), (2,3), (3,4), (4,1) -> 4 edges out of 6 pairs
    adj = {
        nodes[0]: (nodes[1], nodes[3]),
        nodes[1]: (nodes[0], nodes[2]),
        nodes[2]: (nodes[1], nodes[3]),
        nodes[3]: (nodes[0], nodes[2]),
    }
    graph = GraphSnapshot(nodes=nodes, adj_list=adj)

    metrics = compute_groundtruth_metrics(graph, graph)
    assert metrics.confusion_matrix.tp == 4
    assert metrics.confusion_matrix.fp == 0
    assert metrics.confusion_matrix.fn == 0
    assert metrics.confusion_matrix.tn == 2
    assert metrics.total_candidate_pairs == 6
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.accuracy == 1.0
    assert metrics.specificity == 1.0
    assert metrics.f1_score == 1.0
    assert metrics.fpr == 0.0
    assert metrics.fnr == 0.0


def test_validation_metrics_partial_match():
    """Verify precision, recall, accuracy with false positives and false negatives."""
    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(1, 5))
    # GT edges: (1,2), (2,3)
    gt_adj = {
        nodes[0]: (nodes[1],),
        nodes[1]: (nodes[0], nodes[2]),
        nodes[2]: (nodes[1],),
        nodes[3]: (),
    }
    gt_graph = GraphSnapshot(nodes=nodes, adj_list=gt_adj)

    # Inferred edges: (1,2), (3,4)
    inf_adj = {
        nodes[0]: (nodes[1],),
        nodes[1]: (nodes[0],),
        nodes[2]: (nodes[3],),
        nodes[3]: (nodes[2],),
    }
    inf_graph = GraphSnapshot(nodes=nodes, adj_list=inf_adj)

    metrics = compute_groundtruth_metrics(gt_graph, inf_graph)
    # Total pairs = 6
    # TP = {(1,2)} = 1
    # FP = {(3,4)} = 1
    # FN = {(2,3)} = 1
    # TN = 6 - (1 + 1 + 1) = 3
    assert metrics.confusion_matrix.tp == 1
    assert metrics.confusion_matrix.fp == 1
    assert metrics.confusion_matrix.fn == 1
    assert metrics.confusion_matrix.tn == 3
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert pytest.approx(metrics.accuracy, 1e-4) == 4 / 6
    assert pytest.approx(metrics.specificity, 1e-4) == 3 / 4
    assert metrics.f1_score == 0.5
    assert pytest.approx(metrics.fpr, 1e-4) == 1 / 4
    assert metrics.fnr == 0.5


def test_validation_metrics_zero_and_edge_cases():
    """Verify boundary conditions: empty graphs, single nodes, no edges."""
    empty_graph = GraphSnapshot(nodes=(), adj_list={})
    m_empty = compute_groundtruth_metrics(empty_graph, empty_graph)
    assert m_empty.total_candidate_pairs == 0
    assert m_empty.accuracy == 1.0

    single = NodeIdentity(addr="10.0.0.1:48333")
    single_graph = GraphSnapshot(nodes=(single,), adj_list={single: ()})
    m_single = compute_groundtruth_metrics(single_graph, single_graph)
    assert m_single.total_candidate_pairs == 0
    assert m_single.accuracy == 1.0

    # No edges in GT, but FP in Inferred
    nodes = (
        NodeIdentity(addr="10.0.0.1:48333"),
        NodeIdentity(addr="10.0.0.2:48333"),
    )
    gt_no_edges = GraphSnapshot(nodes=nodes, adj_list={nodes[0]: (), nodes[1]: ()})
    inf_one_edge = GraphSnapshot(
        nodes=nodes, adj_list={nodes[0]: (nodes[1],), nodes[1]: (nodes[0],)}
    )
    m_no_gt = compute_groundtruth_metrics(gt_no_edges, inf_one_edge)
    assert m_no_gt.confusion_matrix.tp == 0
    assert m_no_gt.confusion_matrix.fp == 1
    assert m_no_gt.confusion_matrix.tn == 0
    assert m_no_gt.confusion_matrix.fn == 0
    assert m_no_gt.precision == 0.0
    assert m_no_gt.recall == 1.0  # No GT edges to recall


def test_degree_stats_and_hubs():
    """Verify degree statistics, histogram, and supernode hub ranking."""
    hub = NodeIdentity(addr="hub:48333")
    spokes = tuple(NodeIdentity(addr=f"spoke{i}:48333") for i in range(1, 5))
    nodes = (hub,) + spokes

    # Star graph: hub connected to spoke1..4
    adj = {hub: spokes}
    for s in spokes:
        adj[s] = (hub,)

    graph = GraphSnapshot(nodes=nodes, adj_list=adj)
    stats = compute_degree_stats(graph, top_k=2)

    assert stats.min_degree == 1
    assert stats.max_degree == 4
    assert stats.mean_degree == (4 + 4 * 1) / 5  # 1.6
    assert stats.median_degree == 1.0
    assert stats.degree_histogram["1-2"] == 4
    assert stats.degree_histogram["3-5"] == 1
    assert stats.degree_histogram["0"] == 0

    assert len(stats.top_hubs) == 2
    assert stats.top_hubs[0] == ("hub:48333", 4)


def test_clustering_coefficient():
    """Verify local and average clustering coefficient calculations."""
    # 1. Triangle K3: All nodes have degree 2, clustering = 1.0
    t_nodes = tuple(NodeIdentity(addr=f"t{i}:48333") for i in range(1, 4))
    t_adj = {
        t_nodes[0]: (t_nodes[1], t_nodes[2]),
        t_nodes[1]: (t_nodes[0], t_nodes[2]),
        t_nodes[2]: (t_nodes[0], t_nodes[1]),
    }
    t_graph = GraphSnapshot(nodes=t_nodes, adj_list=t_adj)
    assert compute_clustering_coefficient(t_graph) == 1.0

    # 2. Square C4 (no triangles): clustering = 0.0
    s_nodes = tuple(NodeIdentity(addr=f"s{i}:48333") for i in range(1, 5))
    s_adj = {
        s_nodes[0]: (s_nodes[1], s_nodes[3]),
        s_nodes[1]: (s_nodes[0], s_nodes[2]),
        s_nodes[2]: (s_nodes[1], s_nodes[3]),
        s_nodes[3]: (s_nodes[0], s_nodes[2]),
    }
    s_graph = GraphSnapshot(nodes=s_nodes, adj_list=s_adj)
    assert compute_clustering_coefficient(s_graph) == 0.0


def test_connected_components_and_path_metrics():
    """Verify connected components decomposition and BFS path metrics."""
    # Component 1: Line of 4 nodes: 1 - 2 - 3 - 4
    line_nodes = tuple(NodeIdentity(addr=f"l{i}:48333") for i in range(1, 5))
    # Component 2: 1 isolated node
    iso = NodeIdentity(addr="iso:48333")
    all_nodes = line_nodes + (iso,)

    adj = {
        line_nodes[0]: (line_nodes[1],),
        line_nodes[1]: (line_nodes[0], line_nodes[2]),
        line_nodes[2]: (line_nodes[1], line_nodes[3]),
        line_nodes[3]: (line_nodes[2],),
        iso: (),
    }
    graph = GraphSnapshot(nodes=all_nodes, adj_list=adj)

    components, comp_stats = compute_connected_components(graph)
    assert comp_stats.num_components == 2
    assert comp_stats.giant_component_size == 4
    assert comp_stats.giant_component_fraction == 4 / 5
    assert comp_stats.isolated_nodes_count == 1

    # Path metrics on giant component (Line graph of 4 nodes):
    # Distances: (1,2)=1, (1,3)=2, (1,4)=3, (2,3)=1, (2,4)=2, (3,4)=1 -> sum = 10
    # Pairs = 4*3/2 = 6 -> avg = 10/6 ≈ 1.6667
    # Diameter = 3 (from 1 to 4)
    # Eccentricities: 1:3, 2:2, 3:2, 4:3 -> min eccentricity (radius) = 2
    paths = compute_path_metrics(graph, giant_nodes=components[0])
    assert pytest.approx(paths.average_path_length, 1e-4) == 10 / 6
    assert paths.diameter == 3
    assert paths.radius == 2


def test_evaluate_reconciled_results_and_serialization(tmp_path: Path):
    """Verify end-to-end evaluation, JSON roundtrip, and markdown generation."""
    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(1, 4))
    triangle_adj = {
        nodes[0]: (nodes[1], nodes[2]),
        nodes[1]: (nodes[0], nodes[2]),
        nodes[2]: (nodes[0], nodes[1]),
    }
    full_graph = GraphSnapshot(nodes=nodes, adj_list=triangle_adj)

    payload = {
        "full_inferred_topology": full_graph.to_dict(),
        "reconciled_groundtruth": full_graph.to_dict(),
        "evaluation_inferred_topology": full_graph.to_dict(),
        "stats": {
            "initial_full_nodes": 3,
            "surviving_full_nodes": 3,
            "malfunctioning_nodes_count": 0,
        },
    }

    report = evaluate_reconciled_results(payload, compute_paths=True)
    assert report.validation is not None
    assert report.validation.accuracy == 1.0
    assert report.global_topology.num_nodes == 3
    assert report.global_topology.num_edges == 3
    assert report.global_topology.density == 1.0
    assert report.global_topology.average_clustering_coefficient == 1.0
    assert report.global_topology.path_stats is not None
    assert report.global_topology.path_stats.diameter == 1

    # Test JSON save and load
    out_json = tmp_path / "report.json"
    report.save_json(out_json)
    loaded_dict = json.loads(out_json.read_text(encoding="utf-8"))
    loaded_report = EvaluationReport.from_dict(loaded_dict)

    assert loaded_report.global_topology.num_nodes == report.global_topology.num_nodes
    assert (
        loaded_report.validation.confusion_matrix.tp
        == report.validation.confusion_matrix.tp
    )

    # Test Markdown rendering
    md_text = generate_markdown_report(report)
    assert "# TxProbe Network Topology Evaluation Report" in md_text
    assert "Executive Summary" in md_text
    assert "Groundtruth Validation Metrics" in md_text
    assert "Global Network Topology Characterization" in md_text
    assert "Supernodes" in md_text


def test_evaluate_topology_cli(tmp_path: Path, monkeypatch):
    """Test CLI script execution with --reconciled-topology."""
    import runpy
    import sys

    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(1, 4))
    triangle_adj = {
        nodes[0]: (nodes[1], nodes[2]),
        nodes[1]: (nodes[0], nodes[2]),
        nodes[2]: (nodes[0], nodes[1]),
    }
    graph = GraphSnapshot(nodes=nodes, adj_list=triangle_adj)

    payload = {
        "full_inferred_topology": graph.to_dict(),
        "reconciled_groundtruth": graph.to_dict(),
        "evaluation_inferred_topology": graph.to_dict(),
        "stats": {},
    }
    input_file = tmp_path / "reconciled_topology.json"
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    out_json = tmp_path / "out_report.json"
    out_md = tmp_path / "out_report.md"

    script_path = str(
        Path(__file__).resolve().parent.parent / "scripts" / "evaluate_topology.py"
    )
    test_args = [
        script_path,
        "--reconciled-topology",
        str(input_file),
        "--output-json",
        str(out_json),
        "--output-markdown",
        str(out_md),
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    runpy.run_path(script_path, run_name="__main__")

    assert out_json.is_file()
    assert out_md.is_file()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["global_topology"]["num_nodes"] == 3


def test_evaluate_topology_cli_standalone(tmp_path: Path, monkeypatch):
    """Test CLI script execution with --full-graph and --groundtruth-graph."""
    import runpy
    import sys

    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(1, 4))
    triangle_adj = {
        nodes[0]: (nodes[1], nodes[2]),
        nodes[1]: (nodes[0], nodes[2]),
        nodes[2]: (nodes[0], nodes[1]),
    }
    graph = GraphSnapshot(nodes=nodes, adj_list=triangle_adj)

    full_file = tmp_path / "full.json"
    gt_file = tmp_path / "gt.json"
    graph.save(full_file)
    graph.save(gt_file)

    out_json = tmp_path / "out_report_standalone.json"
    out_md = tmp_path / "out_report_standalone.md"

    script_path = str(
        Path(__file__).resolve().parent.parent / "scripts" / "evaluate_topology.py"
    )
    test_args = [
        script_path,
        "--full-graph",
        str(full_file),
        "--groundtruth-graph",
        str(gt_file),
        "--output-json",
        str(out_json),
        "--output-markdown",
        str(out_md),
        "--skip-paths",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    runpy.run_path(script_path, run_name="__main__")

    assert out_json.is_file()
    assert out_md.is_file()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["global_topology"]["num_nodes"] == 3
    assert data["global_topology"]["path_stats"] is None  # Skipped
    assert data["validation"]["accuracy"] == 1.0


def test_compute_groundtruth_metrics_with_groundtruth_nodes():
    """Verify that edges between non-GT nodes are not penalized as FP when groundtruth_nodes is set."""
    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(5))
    gt_node = nodes[0]  # Only node 0 is groundtruth

    # Real network: node 0 connected to node 1.
    gt_adj = {
        nodes[0]: (nodes[1],),
        nodes[1]: (nodes[0],),
        nodes[2]: (),
        nodes[3]: (),
        nodes[4]: (),
    }
    gt_graph = GraphSnapshot(nodes=nodes, adj_list=gt_adj)

    # Inferred: found edge (0, 1) AND correctly/incorrectly inferred edge (2, 3) between public nodes
    inf_adj = {
        nodes[0]: (nodes[1],),
        nodes[1]: (nodes[0],),
        nodes[2]: (nodes[3],),
        nodes[3]: (nodes[2],),
        nodes[4]: (),
    }
    inf_graph = GraphSnapshot(nodes=nodes, adj_list=inf_adj)

    # Case 1: Without groundtruth_nodes filter (Old behavior)
    metrics_all = compute_groundtruth_metrics(gt_graph, inf_graph)
    assert metrics_all.confusion_matrix.tp == 1
    assert metrics_all.confusion_matrix.fp == 1  # (2, 3) was penalized as FP
    assert metrics_all.precision == 0.5

    # Case 2: With groundtruth_nodes filter (Fixed behavior)
    metrics_gt = compute_groundtruth_metrics(
        gt_graph, inf_graph, groundtruth_nodes={gt_node.addr}
    )
    assert metrics_gt.confusion_matrix.tp == 1
    assert metrics_gt.confusion_matrix.fp == 0  # (2, 3) is outside GT scope, not penalized
    assert metrics_gt.confusion_matrix.fn == 0
    assert metrics_gt.precision == 1.0
    assert metrics_gt.recall == 1.0
    # Candidate pairs incident to node 0: 1 * (5 - 1) + 0 = 4 pairs
    assert metrics_gt.total_candidate_pairs == 4


def test_evaluate_reconciled_results_with_groundtruth_identities():
    """Verify evaluate_reconciled_results respects groundtruth_identities in payload."""
    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(4))
    gt_adj = {
        nodes[0]: (nodes[1],),
        nodes[1]: (nodes[0],),
        nodes[2]: (),
        nodes[3]: (),
    }
    inf_adj = {
        nodes[0]: (nodes[1],),
        nodes[1]: (nodes[0],),
        nodes[2]: (nodes[3],),
        nodes[3]: (nodes[2],),
    }
    gt_graph = GraphSnapshot(nodes=nodes, adj_list=gt_adj)
    inf_graph = GraphSnapshot(nodes=nodes, adj_list=inf_adj)

    payload = {
        "full_inferred_topology": inf_graph.to_dict(),
        "reconciled_groundtruth": gt_graph.to_dict(),
        "evaluation_inferred_topology": inf_graph.to_dict(),
        "groundtruth_identities": [nodes[0].addr],
        "stats": {},
    }

    report = evaluate_reconciled_results(payload, compute_paths=False)
    assert report.validation is not None
    assert report.validation.confusion_matrix.tp == 1
    assert report.validation.confusion_matrix.fp == 0
    assert report.validation.precision == 1.0




