"""CLI entry point for Step 3: Matrix Partitioning, UTXO Splitting & Raw Transaction Crafting.

Usage::

    python scripts/craft_transactions.py --config config/testnet4.yaml --groundtruth-file results/.../filtered_groundtruth.json
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
from txprobe.groundtruth import GroundtruthResult
from txprobe.invblock import InvblockResult
from txprobe.models.graph import GraphSnapshot
from txprobe.rpc.client import AsyncBitcoinRpc
from txprobe.transactions import craft_all_rounds

log = logging.getLogger(__name__)


def _load_snapshot_from_file(path: Path) -> GraphSnapshot:
    """Load GraphSnapshot from InvblockResult, GroundtruthResult, or plain GraphSnapshot JSON."""
    try:
        return InvblockResult.load(path).snapshot
    except Exception:
        pass
    try:
        return GroundtruthResult.load(path).snapshot
    except Exception:
        pass
    return GraphSnapshot.load(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 3: Matrix Partitioning, UTXO Splitting & Raw Transaction Crafting"
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config/testnet4.yaml",
        help="Path to YAML config file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--groundtruth-file",
        "-i",
        required=True,
        help="Path to Step 2 filtered_groundtruth.json (or GraphSnapshot JSON)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Output directory (default: parent directory of --groundtruth-file)",
    )
    parser.add_argument(
        "--utxo-target-sats",
        type=int,
        default=None,
        help="Override target satoshis per split UTXO (default from config: 2000)",
    )
    parser.add_argument(
        "--parent-fee-sats",
        type=int,
        default=None,
        help="Override parent/flood transaction fee in satoshis (default from config: 500)",
    )
    parser.add_argument(
        "--marker-fee-sats",
        type=int,
        default=None,
        help="Override marker transaction fee in satoshis (default from config: 500)",
    )
    parser.add_argument(
        "--max-source-size",
        type=int,
        default=None,
        help="Override maximum source set size w (default from config: 75)",
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
    gt_path = Path(args.groundtruth_file)
    snapshot = _load_snapshot_from_file(gt_path)

    craft_cfg = config.tx_crafting
    if args.utxo_target_sats is not None:
        craft_cfg = replace(craft_cfg, utxo_target_sats=args.utxo_target_sats)
    if args.parent_fee_sats is not None:
        craft_cfg = replace(craft_cfg, parent_fee_sats=args.parent_fee_sats)
    if args.marker_fee_sats is not None:
        craft_cfg = replace(craft_cfg, marker_fee_sats=args.marker_fee_sats)
    if args.max_source_size is not None:
        craft_cfg = replace(craft_cfg, max_source_size=args.max_source_size)

    probe_0_cfg = config.get_node(0)
    out_dir = Path(args.output_dir) if args.output_dir else gt_path.parent
    out_file = out_dir / "crafted_rounds.json"

    pbar = tqdm(total=100, desc="Step 3 Tx Crafting", unit="%")

    def on_progress(stage: str, ratio: float) -> None:
        pbar.n = int(ratio * 100)
        pbar.set_postfix_str(stage)
        pbar.refresh()

    def on_funding_needed(deposit_addr: str, current_count: int, needed_count: int) -> None:
        pbar.set_postfix_str(
            f"Waiting for funding ({current_count}/{needed_count} UTXOs) -> {deposit_addr}"
        )
        pbar.refresh()

    async def _execute():
        # Ensure wallet is loaded via root endpoint first, then use wallet-scoped endpoint
        async with AsyncBitcoinRpc.from_node_config(
            probe_0_cfg, use_wallet=False
        ) as root_rpc:
            if probe_0_cfg.wallet:
                loaded = await root_rpc.listwallets()
                if probe_0_cfg.wallet not in loaded:
                    await root_rpc.loadwallet(probe_0_cfg.wallet)

        async with AsyncBitcoinRpc.from_node_config(
            probe_0_cfg, use_wallet=True
        ) as wallet_rpc:
            res = await craft_all_rounds(
                snapshot=snapshot,
                rpc=wallet_rpc,
                config=craft_cfg,
                wallet_name="",
                progress_callback=on_progress,
                funding_callback=on_funding_needed,
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
    print("  Step 3 Raw Transaction Crafting Summary")
    print("=" * 60)
    print(f"  Qualified nodes:          {s.total_nodes}")
    print(f"  Matrix dimensions (wxh):  {s.matrix_width} x {s.matrix_height}")
    print(f"  Total matrix rounds:      {s.total_rounds}")
    print(f"  Total parent txs:         {s.total_parent_txs}")
    print(f"  Total flood txs:          {s.total_flood_txs}")
    print(f"  Total marker txs:         {s.total_marker_txs}")
    print(f"  UTXO split txs broadcast: {len(s.split_txids)}")
    print(f"  Saved to:                 {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
