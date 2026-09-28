"""CLI entry point for Phase 1 address harvesting.

Usage::

    python -m scripts.harvest_addresses --config config/testnet4.yaml

Or from the txprobe project root::

    python scripts/harvest_addresses.py --config config/testnet4.yaml
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
from txprobe.discovery.harvester import harvest_addresses


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1: Harvest testnet4 node addresses")
    parser.add_argument(
        "--config", "-c",
        default="config/testnet4.yaml",
        help="Path to YAML config file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Output directory (default: results/<timestamp>/)",
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

    result = asyncio.run(harvest_addresses(config))

    # Determine output directory
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_dir = Path("results") / ts

    out_file = out_dir / "harvest.json"
    result.save(out_file)

    # Print summary
    s = result.stats
    print()
    print("=" * 60)
    print("  Phase 1 Harvest Summary")
    print("=" * 60)
    print(f"  Groundtruth self (P0):   {s.groundtruth_self_count}")
    print(f"  Groundtruth peers (P0):  {s.groundtruth_peer_count}")
    print(f"  Probe peers (P1):        {s.probe_peer_count}")
    print(f"  DNS seed addrs (P2):     {s.dns_seed_count}")
    print(f"  Addrman addrs (P3):      {s.addrman_count}")
    print(f"  ────────────────────────")
    print(f"  Reachability tested:     {s.reachability_tested}")
    print(f"  Reachability passed:     {s.reachability_passed}")
    print(f"  ────────────────────────")
    print(f"  Total candidates:        {s.total_unique}")
    print(f"  Time elapsed:            {s.elapsed_sec:.1f}s")
    print(f"  Saved to:                {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
