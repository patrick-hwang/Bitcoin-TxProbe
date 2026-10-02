#!/usr/bin/env python3
"""CLI entry point for executing the full end-to-end TxProbe pipeline.

Usage:
    # Run entire pipeline from Step 0 to Step 6:
    python scripts/run_pipeline.py --config config/testnet4.yaml

    # Resume from Step 4 using previous artifacts:
    python scripts/run_pipeline.py --config config/testnet4.yaml --run-dir results/run_... --from-step 4

    # Run only Step 5 and Step 6:
    python scripts/run_pipeline.py --config config/testnet4.yaml --run-dir results/run_... --from-step 5 --to-step 6
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys

# Allow running directly as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from txprobe.config import load_config
from txprobe.orchestrator import MasterPipelineOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("txprobe.pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TxProbe End-to-End Master Pipeline Runner (Steps 0 through 6)"
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config/testnet4.yaml",
        help="Path to YAML configuration file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--run-dir",
        "-o",
        type=Path,
        default=None,
        help="Directory to store all run artifacts (default: results/run_YYYY-MM-DD_HH-MM-SS)",
    )
    parser.add_argument(
        "--from-step",
        type=int,
        default=0,
        choices=range(0, 7),
        help="Step to start execution from (0 to 6, default: 0)",
    )
    parser.add_argument(
        "--to-step",
        type=int,
        default=6,
        choices=range(0, 7),
        help="Step to finish execution at (0 to 6, default: 6)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args()


def print_banner(args: argparse.Namespace) -> None:
    print("\n" + "=" * 70)
    print("      TxProbe End-to-End Network Topology Inference Pipeline      ")
    print("=" * 70)
    print(f" Config File    : {args.config}")
    print(f" Target Steps   : Step {args.from_step} -> Step {args.to_step}")
    if args.run_dir:
        print(f" Run Directory  : {args.run_dir}")
    print("=" * 70 + "\n")


def main() -> None:
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print_banner(args)
    config = load_config(args.config)

    orchestrator = MasterPipelineOrchestrator(
        config=config,
        run_dir=args.run_dir,
        from_step=args.from_step,
        to_step=args.to_step,
    )

    try:
        artifacts = asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        logger.warning("\nPipeline execution cancelled by user.")
        sys.exit(130)
    except Exception as exc:
        logger.exception("Pipeline execution failed: %s", exc)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("                 Pipeline Execution Artifacts Summary                 ")
    print("=" * 70)
    print(f" Artifacts Directory      : {artifacts.run_dir.resolve()}")
    if artifacts.discovered_nodes.is_file():
        print(f" [Step 0] Discovered Peers: {artifacts.discovered_nodes.name}")
    if artifacts.initial_groundtruth.is_file():
        print(f" [Step 1] Initial GT      : {artifacts.initial_groundtruth.name}")
    if artifacts.filtered_groundtruth.is_file():
        print(f" [Step 2] Filtered GT     : {artifacts.filtered_groundtruth.name}")
    if artifacts.crafted_rounds.is_file():
        print(f" [Step 3] Crafted Rounds  : {artifacts.crafted_rounds.name}")
    if artifacts.txprobe_execution.is_file():
        print(f" [Step 4] Probing Result  : {artifacts.txprobe_execution.name}")
    if artifacts.full_inferred_topology.is_file():
        print(f" [Step 5] Full Topology   : {artifacts.full_inferred_topology.name}")
    if artifacts.evaluation_report_md.is_file():
        print(f" [Step 6] Eval Report MD  : {artifacts.evaluation_report_md.name}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
