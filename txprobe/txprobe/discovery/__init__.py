"""Discovery package — Phase 1 address harvesting and Phase 2 peer selection."""

from .harvester import HarvestResult, HarvestStats, harvest_addresses
from .peer_scanner import ScanResult, ScanStats, scan_and_select_peers

__all__ = [
    "HarvestResult",
    "HarvestStats",
    "harvest_addresses",
    "ScanResult",
    "ScanStats",
    "scan_and_select_peers",
]
