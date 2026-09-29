"""CLI entry point for Step 2 INVBLOCK Pre-filtering.

Usage::

    python scripts/filter_invblock.py --config config/testnet4.yaml --groundtruth-file results/.../initial_groundtruth.json
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from txprobe.config import load_config
from txprobe.groundtruth import GroundtruthResult
from txprobe.invblock import run_invblock_prefilter
from txprobe.models.graph import GraphSnapshot
from txprobe.rpc.client import AsyncBitcoinRpc
from tqdm import tqdm

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 2: INVBLOCK Pre-filtering (filter non-responsive & non-compliant nodes)"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/testnet4.yaml",
        help="Path to YAML config file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--groundtruth-file", "-i",
        required=True,
        help="Path to Step 1 initial_groundtruth.json (or GraphSnapshot JSON)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Output directory (default: parent directory of --groundtruth-file)",
    )
    parser.add_argument(
        "--probe-0-log",
        default=None,
        help="Override path to Probe 0 txprobe log file",
    )
    parser.add_argument(
        "--probe-1-log",
        default=None,
        help="Override path to Probe 1 txprobe log file",
    )
    parser.add_argument(
        "--wait-time",
        type=float,
        default=None,
        help="Wait time in seconds after sending INVs (default from config)",
    )
    parser.add_argument(
        "--no-clear-logs",
        action="store_true",
        help="Do not truncate probe log files before running test",
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
    gt_path = Path(args.groundtruth_file)

    # Load GraphSnapshot from either GroundtruthResult JSON or plain GraphSnapshot JSON
    try:
        gt_result = GroundtruthResult.load(gt_path)
        snapshot = gt_result.snapshot
    except Exception:
        snapshot = GraphSnapshot.load(gt_path)

    # Determine probe log paths
    probe_0_cfg = config.get_node(0)
    probe_1_cfg = config.get_node(1)

    p0_log = Path(args.probe_0_log or probe_0_cfg.txprobe_log_file or "txprobe_0.log")
    p1_log = Path(args.probe_1_log or probe_1_cfg.txprobe_log_file or "txprobe_1.log")
    wait_sec = args.wait_time if args.wait_time is not None else config.invblock.wait_time_sec

    out_dir = Path(args.output_dir) if args.output_dir else gt_path.parent
    out_file = out_dir / "filtered_groundtruth.json"

    pbar = tqdm(total=100, desc="Step 2 INVBLOCK", unit="%")

    def on_progress(stage: str, ratio: float) -> None:
        pbar.n = int(ratio * 100)
        pbar.set_postfix_str(stage)
        pbar.refresh()

    async def _execute():
        async with AsyncBitcoinRpc.from_node_config(probe_0_cfg) as p0_client, \
                   AsyncBitcoinRpc.from_node_config(probe_1_cfg) as p1_client:
            res = await run_invblock_prefilter(
                graph=snapshot,
                probe_0=p0_client,
                probe_1=p1_client,
                probe_0_log_path=p0_log,
                probe_1_log_path=p1_log,
                wait_time_sec=wait_sec,
                clear_logs=not args.no_clear_logs,
                progress_callback=on_progress,
            )
            res.save(out_file)
            return res

    result = asyncio.run(_execute())
    pbar.n = 100
    pbar.set_postfix_str("Done")
    pbar.refresh()
    pbar.close()

    s = result.stats
    print()
    print("=" * 60)
    print("  Step 2 INVBLOCK Pre-filtering Summary")
    print("=" * 60)
    print(f"  Total initial nodes:       {s.total_initial_nodes}")
    print(f"  Probe 0 active peers:      {s.probe_0_active_peers}")
    print(f"  Probe 1 active peers:      {s.probe_1_active_peers}")
    print(f"  Mutually connected:        {s.mutually_connected_count}")
    print(f"  Probe 0 responsive:        {s.probe_0_responsive_count}")
    print(f"  Probe 0 non-responsive:    {s.probe_0_nonresponsive_count} (IBD/blocksonly/timeout)")
    print(f"  Probe 1 violating:         {s.probe_1_violating_count} (Duplicate GETDATA)")
    print(f"  Total eliminated:          {s.eliminated_count}")
    print(f"  Remaining qualified nodes: {s.remaining_qualified_count}")
    print(f"  Remaining edges:           {s.remaining_edges_count}")
    print(f"  Saved to:                  {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
