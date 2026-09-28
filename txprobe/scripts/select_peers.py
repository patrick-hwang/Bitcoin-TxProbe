"""CLI entry point for Phase 2 batch connection and peer selection.

Usage (from existing Phase 1 harvest.json)::

    python scripts/select_peers.py --config config/testnet4.yaml --harvest-file results/.../harvest.json

Or run Phase 1 + Phase 2 end-to-end::

    python scripts/select_peers.py --config config/testnet4.yaml
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

from txprobe.config import Config, load_config
from txprobe.discovery.harvester import HarvestResult, harvest_addresses
from txprobe.discovery.peer_scanner import ScanResult, scan_and_select_peers


async def _run_pipeline(
    config: Config,
    harvest_file: Path | None,
    out_dir: Path,
) -> tuple[HarvestResult, ScanResult]:
    if harvest_file is not None:
        harvest = HarvestResult.load(harvest_file)
    else:
        harvest = await harvest_addresses(config)
        harvest.save(out_dir / "harvest.json")

    scan_result = await scan_and_select_peers(config, harvest)
    return harvest, scan_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2: Batch connect probes and select mutually connected peers"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/testnet4.yaml",
        help="Path to YAML config file (default: config/testnet4.yaml)",
    )
    parser.add_argument(
        "--harvest-file", "-i",
        default=None,
        help="Optional path to Phase 1 harvest.json. If omitted, runs Phase 1 first.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Output directory (default: parent of --harvest-file or results/<timestamp>/)",
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
    harvest_path = Path(args.harvest_file) if args.harvest_file else None

    if args.output_dir:
        out_dir = Path(args.output_dir)
    elif harvest_path is not None:
        out_dir = harvest_path.parent
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_dir = Path("results") / ts

    _, scan_result = asyncio.run(_run_pipeline(config, harvest_path, out_dir))
    out_file = out_dir / "discovered_nodes.json"
    scan_result.save(out_file)

    s = scan_result.stats
    p_a, p_b = scan_result.probe_ids
    print()
    print("=" * 60)
    print("  Phase 2 Peer Selection Summary")
    print("=" * 60)
    print(f"  Candidates input:        {s.candidates_input}")
    print(f"  Onetry sent (Probe {p_a}):   {s.onetry_sent_probes.get(p_a, 0)}")
    print(f"  Onetry sent (Probe {p_b}):   {s.onetry_sent_probes.get(p_b, 0)}")
    print(f"  ────────────────────────")
    print(f"  Connected (Probe {p_a}):     {s.connected_probes.get(p_a, 0)}")
    print(f"  Connected (Probe {p_b}):     {s.connected_probes.get(p_b, 0)}")
    print(f"  Mutual connected:        {s.mutual_connected}")
    print(f"  Selected nodes:          {s.selected_count}")
    print(f"  ────────────────────────")
    print(f"  Disconnected (Probe {p_a}):  {s.excess_disconnected_probes.get(p_a, 0)}")
    print(f"  Disconnected (Probe {p_b}):  {s.excess_disconnected_probes.get(p_b, 0)}")
    print(f"  Early exit:              {s.early_exit}")
    print(f"  Polls count:             {s.polls_count}")
    print(f"  Time elapsed:            {s.elapsed_sec:.1f}s")
    print(f"  Saved to:                {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
