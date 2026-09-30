"""CLI entry point for Step 4: TxProbe Execution Loop & Multi-Round Topology Inference.

Usage::

    python scripts/run_txprobe.py --config config/testnet4.yaml --crafted-file results/.../crafted_rounds.json
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
import logging
from pathlib import Path
import sys

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm
from txprobe.config import load_config
from txprobe.models.transaction import TxProbeCraftingResult
from txprobe.probing import run_txprobe_execution
from txprobe.rpc.client import AsyncBitcoinRpc

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 4: TxProbe Execution Loop & Multi-Round Topology Inference"
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config/testnet4.yaml",
        help="Path to YAML config file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--crafted-file",
        "-i",
        required=True,
        help="Path to Step 3 crafted_rounds.json",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Output directory (default: parent directory of --crafted-file)",
    )
    parser.add_argument(
        "--probe-0-log",
        default=None,
        help="Override path to Probe 0 txprobe log file",
    )
    parser.add_argument(
        "--invblock-wait",
        type=float,
        default=None,
        help="Override invblock_wait_sec (default from config: 5.0)",
    )
    parser.add_argument(
        "--flood-wait",
        type=float,
        default=None,
        help="Override flood_wait_sec (default from config: 1.0)",
    )
    parser.add_argument(
        "--parent-wait",
        type=float,
        default=None,
        help="Override parent_wait_sec (default from config: 5.0)",
    )
    parser.add_argument(
        "--marker-wait",
        type=float,
        default=None,
        help="Override marker_propagation_wait_sec (default from config: 10.0)",
    )
    parser.add_argument(
        "--getdata-wait",
        type=float,
        default=None,
        help="Override getdata_wait_sec (default from config: 5.0)",
    )
    parser.add_argument(
        "--cleanup-wait",
        type=float,
        default=None,
        help="Override cleanup_wait_sec (default from config: 2.0)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config(args.config)
    crafted_path = Path(args.crafted_file)
    crafting_result = TxProbeCraftingResult.load(crafted_path)

    exec_cfg = config.txprobe_execution
    if args.invblock_wait is not None:
        exec_cfg = replace(exec_cfg, invblock_wait_sec=args.invblock_wait)
    if args.flood_wait is not None:
        exec_cfg = replace(exec_cfg, flood_wait_sec=args.flood_wait)
    if args.parent_wait is not None:
        exec_cfg = replace(exec_cfg, parent_wait_sec=args.parent_wait)
    if args.marker_wait is not None:
        exec_cfg = replace(exec_cfg, marker_propagation_wait_sec=args.marker_wait)
    if args.getdata_wait is not None:
        exec_cfg = replace(exec_cfg, getdata_wait_sec=args.getdata_wait)
    if args.cleanup_wait is not None:
        exec_cfg = replace(exec_cfg, cleanup_wait_sec=args.cleanup_wait)

    probe_0_cfg = config.get_node(0)
    p0_log = Path(args.probe_0_log or probe_0_cfg.txprobe_log_file or "txprobe_0.log")

    out_dir = Path(args.output_dir) if args.output_dir else crafted_path.parent
    out_file = out_dir / "txprobe_execution.json"
    checkpoint_file = out_dir / "txprobe_execution_checkpoint.json"

    pbar = tqdm(total=100, desc="Step 4 TxProbe Execution", unit="%")

    def on_progress(stage: str, ratio: float) -> None:
        pbar.n = int(ratio * 100)
        pbar.set_postfix_str(stage)
        pbar.refresh()

    async def _execute():
        async with AsyncBitcoinRpc.from_node_config(
            probe_0_cfg, use_wallet=False
        ) as p0_client:
            res = await run_txprobe_execution(
                crafting_result=crafting_result,
                probe_0=p0_client,
                probe_0_log_path=p0_log,
                config=exec_cfg,
                progress_callback=on_progress,
                checkpoint_path=checkpoint_file,
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
    print("  Step 4 TxProbe Execution Summary")
    print("=" * 60)
    print(f"  Completed rounds:          {s.completed_rounds} / {s.total_rounds}")
    print(f"  Initial nodes:             {s.initial_nodes_count}")
    print(f"  Surviving nodes:           {s.surviving_nodes_count}")
    print(f"  Malfunctioning sources:    {s.malfunctioning_nodes_count} (log-detected)")
    print(f"  Dropped nodes:             {s.dropped_nodes_count}")
    print(f"  Total pairs tested:        {s.total_tested_pairs}")
    print(f"  Inferred edges:            {s.inferred_edges_count}")
    print(f"  Filtered GT edges:         {s.filtered_groundtruth_edges_count}")
    print(f"  Saved to:                  {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
