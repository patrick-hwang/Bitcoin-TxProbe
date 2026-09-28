"""CLI entry point for Step 1 initial groundtruth capture.

Usage::

    python scripts/capture_groundtruth.py --config config/testnet4.yaml --nodes-file results/.../discovered_nodes.json
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from txprobe.config import load_config
from txprobe.discovery.peer_scanner import ScanResult
from txprobe.groundtruth import capture_initial_groundtruth


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 1: Capture initial groundtruth topology snapshot"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/testnet4.yaml",
        help="Path to YAML config file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--nodes-file", "-i",
        required=True,
        help="Path to Step 0 discovered_nodes.json",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Output directory (default: parent directory of --nodes-file)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config(args.config)
    nodes_path = Path(args.nodes_file)
    scan_result = ScanResult.load(nodes_path)

    out_dir = Path(args.output_dir) if args.output_dir else nodes_path.parent
    out_file = out_dir / "initial_groundtruth.json"

    gt_result = asyncio.run(
        capture_initial_groundtruth(config, scan_result.selected_identities())
    )
    gt_result.save(out_file)

    s = gt_result.stats
    print()
    print("=" * 60)
    print("  Step 1 Initial Groundtruth Summary")
    print("=" * 60)
    print(f"  Groundtruth configured:  {s.groundtruth_nodes_configured}")
    print(f"  Groundtruth online:      {s.groundtruth_nodes_online}")
    print(f"  Input target nodes:      {s.input_target_nodes}")
    print(f"  Active graph nodes:      {s.active_nodes_count}")
    print(f"  Pruned disconnected:     {s.pruned_disconnected_count}")
    print(f"  Groundtruth edges:       {s.groundtruth_edges_count}")
    print(f"  Time elapsed:            {s.elapsed_sec:.2f}s")
    print(f"  Saved to:                {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
