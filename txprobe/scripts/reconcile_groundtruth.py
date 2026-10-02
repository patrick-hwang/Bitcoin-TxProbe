"""CLI entry point for Step 5: Malfunction Filtering, Groundtruth Reconciliation & Full Inference Topology.

Usage::

    python scripts/reconcile_groundtruth.py \\
        --config config/testnet4.yaml \\
        --step4-results results/.../txprobe_execution.json \\
        --filtered-groundtruth results/.../filtered_groundtruth.json
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from txprobe.config import load_config
from txprobe.groundtruth import GroundtruthResult
from txprobe.models.graph import GraphSnapshot
from txprobe.probing import TxProbeExecutionResult
from txprobe.reconciliation import (
    capture_final_groundtruth,
    reconcile_topology,
)

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 5: Malfunction Filtering, Groundtruth Reconciliation & Full Inference Topology"
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config/testnet4.yaml",
        help="Path to YAML config file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--step4-results",
        "-s",
        required=True,
        help="Path to Step 4 txprobe_execution.json",
    )
    parser.add_argument(
        "--filtered-groundtruth",
        "-g",
        required=True,
        help="Path to Step 2 filtered_groundtruth.json (or initial_groundtruth.json)",
    )
    parser.add_argument(
        "--final-groundtruth",
        default=None,
        help="Optional path to pre-captured final_groundtruth.json (for offline analysis/replays)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Output directory (default: parent directory of --step4-results)",
    )
    parser.add_argument(
        "--output-full-graph",
        default=None,
        help="Optional filename/path for standalone full inferred network topology (default: full_inferred_topology.json)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = load_config(args.config)

    step4_path = Path(args.step4_results)
    if not step4_path.is_file():
        log.error("Step 4 results file not found: %s", step4_path)
        sys.exit(1)

    gt_before_path = Path(args.filtered-groundtruth if hasattr(args, "filtered-groundtruth") else args.filtered_groundtruth)
    if not gt_before_path.is_file():
        log.error("Filtered groundtruth file not found: %s", gt_before_path)
        sys.exit(1)

    log.info("Loading Step 4 results from %s...", step4_path)
    step4_res = TxProbeExecutionResult.load(step4_path)

    log.info("Loading pre-probing groundtruth from %s...", gt_before_path)
    try:
        gt_before_res = GroundtruthResult.load(gt_before_path)
        gt_before_snapshot = gt_before_res.snapshot
        gt_identities = gt_before_res.groundtruth_identities
    except Exception:
        gt_before_snapshot = GraphSnapshot.load(gt_before_path)
        gt_identities = None

    out_dir = Path(args.output_dir) if args.output_dir else step4_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Obtain post-probing groundtruth
    if args.final_groundtruth:
        final_gt_path = Path(args.final_groundtruth)
        log.info("Loading post-probing groundtruth from file %s...", final_gt_path)
        try:
            final_gt_res = GroundtruthResult.load(final_gt_path)
            final_gt_snapshot = final_gt_res.snapshot
            if gt_identities is None:
                gt_identities = final_gt_res.groundtruth_identities
        except Exception:
            final_gt_snapshot = GraphSnapshot.load(final_gt_path)
    else:
        log.info("Capturing live post-probing groundtruth via RPC...")
        final_gt_res = asyncio.run(
            capture_final_groundtruth(cfg, step4_res.inferred_snapshot.nodes)
        )
        final_gt_snapshot = final_gt_res.snapshot
        if gt_identities is None:
            gt_identities = final_gt_res.groundtruth_identities

        # Save post-probing groundtruth snapshot
        final_gt_save_path = out_dir / "final_groundtruth.json"
        final_gt_res.save(final_gt_save_path)
        log.info("Saved final groundtruth snapshot to %s", final_gt_save_path)

    log.info("Executing Step 5 reconciliation...")
    reconciled_res = reconcile_topology(
        inferred_snapshot=step4_res.inferred_snapshot,
        groundtruth_before=gt_before_snapshot,
        groundtruth_after=final_gt_snapshot,
        malfunctioning_nodes=step4_res.malfunctioning_nodes,
        dropped_nodes=step4_res.dropped_nodes,
        groundtruth_identities=gt_identities,
    )

    reconciled_output_path = out_dir / "reconciled_topology.json"
    reconciled_res.save(reconciled_output_path)
    log.info("Saved reconciled topology to %s", reconciled_output_path)

    # Save standalone full inferred topology
    full_graph_filename = args.output_full_graph or "full_inferred_topology.json"
    full_graph_path = out_dir / full_graph_filename
    reconciled_res.save_full_inferred_topology(full_graph_path)
    log.info("Saved full inferred network topology to %s", full_graph_path)

    stats = reconciled_res.stats
    print("\n" + "=" * 65)
    print("STEP 5 RECONCILIATION & FULL TOPOLOGY COMPLETE")
    print("=" * 65)
    print(f"Full Inferred Network Nodes : {stats.surviving_full_nodes} (initial: {stats.initial_full_nodes})")
    print(f"Full Inferred Network Edges : {stats.full_inferred_edges_count}")
    print(f"Malfunctioning Nodes Removed: {stats.malfunctioning_nodes_count}")
    print(f"Dropped / Disconnected Nodes: {stats.dropped_nodes_count}")
    print(f"Transitory Edges Removed    : {stats.transitory_edges_count}")
    print(f"Groundtruth Eval Nodes      : {stats.groundtruth_eval_nodes_count}")
    print(f"Stable Groundtruth Edges    : {stats.groundtruth_eval_edges_count}")
    print(f"Full Topology File          : {full_graph_path}")
    print(f"Reconciled File             : {reconciled_output_path}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
