#!/usr/bin/env python3
"""Evaluate inferred Bitcoin Testnet4 network topology and groundtruth validation metrics.

Usage:
    # Evaluate from Step 5 reconciled topology output:
    python -m txprobe.scripts.evaluate_topology --reconciled-topology reconciled_topology.json

    # Evaluate from separate graph files:
    python -m txprobe.scripts.evaluate_topology \\
        --full-graph full_inferred_topology.json \\
        --groundtruth-graph reconciled_groundtruth.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running directly as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from txprobe.evaluation import (
    EvaluationReport,
    compute_global_topology_metrics,
    compute_groundtruth_metrics,
    evaluate_reconciled_results,
    generate_markdown_report,
)
from txprobe.models.graph import GraphSnapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("txprobe.evaluate")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute network topology and groundtruth validation metrics for TxProbe."
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--reconciled-topology",
        type=Path,
        help="Path to Step 5 reconciled_topology.json containing full and evaluation topologies.",
    )
    input_group.add_argument(
        "--full-graph",
        type=Path,
        help="Path to standalone full_inferred_topology.json.",
    )

    parser.add_argument(
        "--groundtruth-graph",
        type=Path,
        default=None,
        help="Optional path to groundtruth GraphSnapshot JSON for standalone validation.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("topology_evaluation_report.json"),
        help="Path to save machine-readable evaluation report JSON (default: topology_evaluation_report.json).",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path("TOPOLOGY_EVALUATION_REPORT.md"),
        help="Path to save human-readable Markdown evaluation report (default: TOPOLOGY_EVALUATION_REPORT.md).",
    )
    parser.add_argument(
        "--skip-paths",
        action="store_true",
        help="Skip BFS shortest path & diameter calculation (useful for extremely large graphs).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    report: EvaluationReport
    if args.reconciled_topology:
        if not args.reconciled_topology.is_file():
            logger.error("Reconciled topology file not found: %s", args.reconciled_topology)
            sys.exit(1)

        logger.info("Loading reconciled topology from: %s", args.reconciled_topology)
        data = json.loads(args.reconciled_topology.read_text(encoding="utf-8"))
        report = evaluate_reconciled_results(data, compute_paths=not args.skip_paths)
    else:
        if not args.full_graph.is_file():
            logger.error("Full inferred graph file not found: %s", args.full_graph)
            sys.exit(1)

        logger.info("Loading full inferred topology from: %s", args.full_graph)
        full_graph = GraphSnapshot.load(args.full_graph)
        global_metrics = compute_global_topology_metrics(
            full_graph, compute_paths=not args.skip_paths
        )

        val_metrics = None
        if args.groundtruth_graph:
            if not args.groundtruth_graph.is_file():
                logger.error("Groundtruth graph file not found: %s", args.groundtruth_graph)
                sys.exit(1)
            logger.info("Loading groundtruth graph from: %s", args.groundtruth_graph)
            gt_graph = GraphSnapshot.load(args.groundtruth_graph)
            val_metrics = compute_groundtruth_metrics(gt_graph, full_graph)

        report = EvaluationReport(
            validation=val_metrics,
            global_topology=global_metrics,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "step": "step_6_evaluation",
                "source_file": str(args.full_graph),
                "groundtruth_file": str(args.groundtruth_graph) if args.groundtruth_graph else None,
            },
        )

    # Save outputs
    report.save_json(args.output_json)
    logger.info("Saved JSON evaluation report to: %s", args.output_json)

    markdown_text = generate_markdown_report(report)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(markdown_text, encoding="utf-8")
    logger.info("Saved Markdown evaluation report to: %s", args.output_markdown)

    # Print summary to console
    gt = report.global_topology
    print("\n" + "=" * 65)
    print("           TxProbe Network Topology Evaluation Summary           ")
    print("=" * 65)
    print(f"Nodes (|V|)              : {gt.num_nodes}")
    print(f"Edges (|E|)              : {gt.num_edges}")
    print(f"Graph Density            : {gt.density:.6f}")
    print(f"Degree (Mean / Median)   : {gt.degree_stats.mean_degree:.2f} / {gt.degree_stats.median_degree:.1f}")
    print(f"Degree (Min / Max)       : {gt.degree_stats.min_degree} / {gt.degree_stats.max_degree}")
    print(f"Average Clustering (C)   : {gt.average_clustering_coefficient:.4f} (ER baseline: {gt.er_clustering_comparison:.4f})")
    print(f"Giant Component Size     : {gt.component_stats.giant_component_size} ({gt.component_stats.giant_component_fraction * 100:.1f}%)")
    print(f"Isolated Nodes           : {gt.component_stats.isolated_nodes_count}")
    if gt.path_stats:
        print(f"Average Shortest Path    : {gt.path_stats.average_path_length:.2f} hops")
        print(f"Diameter / Radius        : {gt.path_stats.diameter} / {gt.path_stats.radius} hops")

    if report.validation:
        v = report.validation
        cm = v.confusion_matrix
        print("-" * 65)
        print("               Groundtruth Validation Metrics                    ")
        print("-" * 65)
        print(f"Confusion Matrix         : TP={cm.tp} | FP={cm.fp} | TN={cm.tn} | FN={cm.fn}")
        print(f"Precision                : {v.precision * 100:.2f}%")
        print(f"Recall (Sensitivity)     : {v.recall * 100:.2f}%")
        print(f"Accuracy                 : {v.accuracy * 100:.2f}%")
        print(f"F1-Score                 : {v.f1_score:.4f}")
        print(f"Specificity              : {v.specificity * 100:.2f}%")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
