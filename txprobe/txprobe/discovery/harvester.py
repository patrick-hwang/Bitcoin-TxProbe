"""Phase 1 — Initial address harvesting with priority ordering."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config, NodeConfig
from ..models.node import (
    CandidateNode,
    CandidatePriority,
    NodeIdentity,
    normalize_addr,
    split_addr_port,
)
from ..rpc.client import AsyncBitcoinRpc, RpcError
from .dns_seeds import resolve_dns_seeds
from .reachability import batch_test_reachability

log = logging.getLogger(__name__)

# Connection types to always skip (ephemeral)
_SKIP_CONN_TYPES = frozenset({"feeler", "addr-fetch"})


@dataclass
class HarvestStats:
    """Statistics from the harvest process."""
    groundtruth_self_count: int = 0
    groundtruth_peer_count: int = 0
    probe_peer_count: int = 0
    dns_seed_count: int = 0
    addrman_count: int = 0
    reachability_tested: int = 0
    reachability_passed: int = 0
    total_unique: int = 0
    timestamp: str = ""
    elapsed_sec: float = 0.0


@dataclass
class HarvestResult:
    """Output of Phase 1 address harvesting."""
    candidates: list[CandidateNode]
    already_connected_probes: dict[int, set[NodeIdentity]] = field(default_factory=dict)
    stats: HarvestStats = field(default_factory=HarvestStats)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "timestamp": self.stats.timestamp,
            "elapsed_sec": round(self.stats.elapsed_sec, 2),
            "stats": {
                "groundtruth_self_count": self.stats.groundtruth_self_count,
                "groundtruth_peer_count": self.stats.groundtruth_peer_count,
                "probe_peer_count": self.stats.probe_peer_count,
                "dns_seed_count": self.stats.dns_seed_count,
                "addrman_count": self.stats.addrman_count,
                "reachability_tested": self.stats.reachability_tested,
                "reachability_passed": self.stats.reachability_passed,
                "total_unique": self.stats.total_unique,
            },
            "already_connected_probes": {
                str(probe_id): sorted(n.addr for n in peers)
                for probe_id, peers in sorted(self.already_connected_probes.items())
            },
            "candidates": [
                {
                    "addr": c.identity.addr,
                    "priority": int(c.priority),
                    "network": c.network,
                    "source_node_id": c.source_node_id,
                    "last_seen": c.last_seen,
                }
                for c in self.candidates
            ],
        }

    def save(self, path: Path) -> None:
        """Write harvest result to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> HarvestResult:
        """Deserialize a HarvestResult from a JSON dict."""
        raw_stats = data.get("stats", {})
        stats = HarvestStats(
            groundtruth_self_count=int(raw_stats.get("groundtruth_self_count", 0)),
            groundtruth_peer_count=int(raw_stats.get("groundtruth_peer_count", 0)),
            probe_peer_count=int(raw_stats.get("probe_peer_count", 0)),
            dns_seed_count=int(raw_stats.get("dns_seed_count", 0)),
            addrman_count=int(raw_stats.get("addrman_count", 0)),
            reachability_tested=int(raw_stats.get("reachability_tested", 0)),
            reachability_passed=int(raw_stats.get("reachability_passed", 0)),
            total_unique=int(raw_stats.get("total_unique", 0)),
            timestamp=str(data.get("timestamp", "")),
            elapsed_sec=float(data.get("elapsed_sec", 0.0)),
        )

        already_connected_probes: dict[int, set[NodeIdentity]] = {}
        raw_probes = data.get("already_connected_probes", {})
        for probe_id_str, addr_list in raw_probes.items():
            already_connected_probes[int(probe_id_str)] = {
                NodeIdentity(addr=a) for a in addr_list
            }

        candidates = [
            CandidateNode(
                identity=NodeIdentity(addr=c["addr"]),
                priority=CandidatePriority(int(c["priority"])),
                network=str(c["network"]),
                source_node_id=int(c["source_node_id"]),
                last_seen=int(c.get("last_seen", 0)),
            )
            for c in data.get("candidates", [])
        ]

        return cls(
            candidates=candidates,
            already_connected_probes=already_connected_probes,
            stats=stats,
        )

    @classmethod
    def load(cls, path: str | Path) -> HarvestResult:
        """Load a HarvestResult from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


async def harvest_addresses(config: Config) -> HarvestResult:
    """Main Phase 1 entry point — collect and validate candidate addresses.

    Steps (in priority order):
        1.0  getnetworkinfo on groundtruth nodes [2,3,4,5,6] (self .onion) → priority 0
        1.1  getpeerinfo on groundtruth nodes [2,3,4,5,6]                  → priority 0
        1.2  getpeerinfo on probe nodes [0,1]                               → priority 1
        1.3  DNS seed resolution                                             → priority 2
        1.4  getnodeaddresses(0) on all nodes [0..6]                         → priority 3
        1.5  Batch reachability test on candidates that need it

    Args:
        config: Loaded experiment configuration.

    Returns:
        HarvestResult with prioritized, reachable candidates.
    """
    t0 = time.monotonic()
    seen: set[NodeIdentity] = set()
    gt_self_candidates: list[CandidateNode] = []  # confirmed online via RPC, skip reachability
    candidates: list[CandidateNode] = []
    probe_peers: list[CandidateNode] = []  # probe peers skip reachability test
    connected_probes: dict[int, set[NodeIdentity]] = {
        n.id: set() for n in config.probe_nodes
    }

    stats = HarvestStats()

    # ── Step 1.0: Groundtruth nodes' own identities (priority 0, front of queue) ──
    log.info("Step 1.0: Harvesting groundtruth nodes' own identities...")
    gt_self_count = await _harvest_groundtruth_self_parallel(
        config.groundtruth_nodes,
        config.default_port,
        seen,
        gt_self_candidates,
    )
    stats.groundtruth_self_count = gt_self_count
    log.info("  Found %d groundtruth self-identities", gt_self_count)

    # ── Step 1.1: Groundtruth peers (priority 0) ──
    log.info("Step 1.1: Harvesting peers of groundtruth nodes...")
    gt_count = await _harvest_peers_parallel(
        config.groundtruth_nodes,
        config,
        CandidatePriority.GROUNDTRUTH_PEER,
        seen,
        candidates,
        skip_block_relay=False,
    )
    stats.groundtruth_peer_count = gt_count
    log.info("  Found %d unique groundtruth peers", gt_count)

    # ── Step 1.2: Probe peers (priority 1) ──
    log.info("Step 1.2: Harvesting peers of probe nodes...")
    probe_count = await _harvest_peers_parallel(
        config.probe_nodes,
        config,
        CandidatePriority.PROBE_PEER,
        seen,
        probe_peers,  # separate list — these skip reachability
        skip_block_relay=True,
        connected_out=connected_probes,
    )
    stats.probe_peer_count = probe_count
    log.info("  Found %d unique probe peers", probe_count)

    # ── Step 1.3: DNS seeds (priority 2) ──
    log.info("Step 1.3: Resolving DNS seeds...")
    dns_count = await resolve_dns_seeds(
        config.dns_seeds, config.default_port, seen, candidates,
    )
    stats.dns_seed_count = dns_count
    log.info("  Found %d unique DNS seed addresses", dns_count)

    # ── Step 1.4: Address manager (priority 3) ──
    log.info("Step 1.4: Harvesting address manager on all nodes...")
    addrman_count = await _harvest_addrman_parallel(
        config.nodes, config, seen, candidates,
    )
    stats.addrman_count = addrman_count
    log.info("  Found %d unique addrman addresses", addrman_count)

    # ── Step 1.5: Batch reachability test ──
    log.info("Step 1.5: Testing reachability of %d candidates...", len(candidates))
    stats.reachability_tested = len(candidates)

    if candidates:
        test_inputs = []
        for c in candidates:
            host, port = split_addr_port(c.identity.addr)
            test_inputs.append((host, port, c.network))

        results = await batch_test_reachability(test_inputs, config.reachability)
        reachable = [c for c, ok in zip(candidates, results) if ok]
        stats.reachability_passed = len(reachable)
        log.info("  Reachability: %d / %d passed", len(reachable), len(candidates))
    else:
        reachable = []

    # ── Combine: groundtruth self + tested candidates + probe peers ──
    all_candidates = gt_self_candidates + reachable + probe_peers
    all_candidates.sort(key=lambda c: c.priority)
    stats.total_unique = len(all_candidates)

    elapsed = time.monotonic() - t0
    stats.elapsed_sec = elapsed
    stats.timestamp = datetime.now(timezone.utc).isoformat()
    log.info("Harvest complete: %d candidates in %.1f seconds", len(all_candidates), elapsed)

    return HarvestResult(
        candidates=all_candidates,
        already_connected_probes=connected_probes,
        stats=stats,
    )


# ── Internal helpers ──


async def _harvest_groundtruth_self_parallel(
    node_configs: list[NodeConfig],
    default_port: int,
    seen: set[NodeIdentity],
    candidates: list[CandidateNode],
) -> int:
    """Call getnetworkinfo() on groundtruth nodes to harvest their own .onion identities."""
    added = 0
    tasks = [
        _harvest_groundtruth_self_one(nc, default_port, seen, candidates)
        for nc in node_configs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for nc, result in zip(node_configs, results):
        if isinstance(result, Exception):
            log.warning("getnetworkinfo failed on groundtruth node %d: %s", nc.id, result)
        else:
            added += result
    return added


async def _harvest_groundtruth_self_one(
    nc: NodeConfig,
    default_port: int,
    seen: set[NodeIdentity],
    candidates: list[CandidateNode],
) -> int:
    """Extract the .onion (or external) localaddress of a groundtruth node via getnetworkinfo()."""
    try:
        async with AsyncBitcoinRpc(nc.rpchost, nc.rpcport, nc.rpcuser, nc.rpcpassword) as rpc:
            info = await rpc.getnetworkinfo()
    except Exception as e:
        log.warning("RPC getnetworkinfo on node %d failed: %s", nc.id, e)
        return 0

    local_addrs: list[dict] = info.get("localaddresses", [])
    if not local_addrs:
        return 0

    # Prefer .onion entry; fallback to first non-local address
    chosen = next(
        (item for item in local_addrs if str(item.get("address", "")).endswith(".onion")),
        None,
    )
    if chosen is None:
        chosen = next(
            (
                item
                for item in local_addrs
                if item.get("address") and not str(item.get("address")).startswith("127.0.0.1")
            ),
            None,
        )
    if chosen is None:
        return 0

    raw_addr = str(chosen["address"])
    port = int(chosen.get("port", default_port))
    network = "onion" if raw_addr.endswith(".onion") else ("ipv6" if ":" in raw_addr else "ipv4")
    addr_str = normalize_addr(raw_addr, port, network)
    identity = NodeIdentity(addr=addr_str)

    if identity in seen:
        return 0

    seen.add(identity)
    candidates.append(
        CandidateNode(
            identity=identity,
            priority=CandidatePriority.GROUNDTRUTH_PEER,
            network=network,
            source_node_id=nc.id,
            last_seen=0,
        )
    )
    return 1


async def _harvest_peers_parallel(
    node_configs: list[NodeConfig],
    config: Config,
    priority: CandidatePriority,
    seen: set[NodeIdentity],
    candidates: list[CandidateNode],
    skip_block_relay: bool,
    connected_out: dict[int, set[NodeIdentity]] | None = None,
) -> int:
    """Call getpeerinfo() on multiple nodes in parallel, append new candidates.

    Args:
        node_configs: Nodes to query.
        config: Global config (for RPC host).
        priority: Priority level for these candidates.
        seen: Shared dedup set (modified in-place).
        candidates: Output list (modified in-place).
        skip_block_relay: If True, skip block-relay-only peers.
        connected_out: If provided, map of node_id → set to collect
                       connected peer identities for that node.

    Returns:
        Number of new candidates added.
    """
    added = 0
    tasks = []
    for nc in node_configs:
        tasks.append(_harvest_peers_one(
            nc, config, priority, seen, candidates,
            skip_block_relay, connected_out,
        ))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for nc, result in zip(node_configs, results):
        if isinstance(result, Exception):
            log.warning("getpeerinfo failed on node %d: %s", nc.id, result)
        else:
            added += result
    return added


async def _harvest_peers_one(
    nc: NodeConfig,
    config: Config,
    priority: CandidatePriority,
    seen: set[NodeIdentity],
    candidates: list[CandidateNode],
    skip_block_relay: bool,
    connected_out: dict[int, set[NodeIdentity]] | None,
) -> int:
    """getpeerinfo() on one node, append new candidates."""
    added = 0
    try:
        async with AsyncBitcoinRpc(nc.rpchost, nc.rpcport, nc.rpcuser, nc.rpcpassword) as rpc:
            peers = await rpc.getpeerinfo()
    except Exception as e:
        log.warning("RPC to node %d failed: %s", nc.id, e)
        return 0

    for peer in peers:
        addr: str = peer.get("addr", "")
        conn_type: str = peer.get("connection_type", "")
        network: str = peer.get("network", "")

        # Skip local connections
        if addr.startswith("127.0.0.1"):
            continue

        # Skip ephemeral connection types
        if conn_type in _SKIP_CONN_TYPES:
            continue

        # Probe nodes: skip block-relay-only (can't use for TxProbe)
        if skip_block_relay and conn_type == "block-relay-only":
            continue

        identity = NodeIdentity(addr=addr)

        # Track connected peers for probe nodes
        if connected_out is not None and nc.id in connected_out:
            connected_out[nc.id].add(identity)

        if identity not in seen:
            seen.add(identity)
            candidates.append(CandidateNode(
                identity=identity,
                priority=priority,
                network=network,
                source_node_id=nc.id,
                last_seen=0,
            ))
            added += 1

    return added


async def _harvest_addrman_parallel(
    node_configs: list[NodeConfig],
    config: Config,
    seen: set[NodeIdentity],
    candidates: list[CandidateNode],
) -> int:
    """Call getnodeaddresses(0) on multiple nodes in parallel."""
    added = 0
    tasks = [_harvest_addrman_one(nc, seen, candidates) for nc in node_configs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for nc, result in zip(node_configs, results):
        if isinstance(result, Exception):
            log.warning("getnodeaddresses failed on node %d: %s", nc.id, result)
        else:
            added += result
    return added


async def _harvest_addrman_one(
    nc: NodeConfig,
    seen: set[NodeIdentity],
    candidates: list[CandidateNode],
) -> int:
    """getnodeaddresses(0) on one node, append new candidates."""
    added = 0
    try:
        async with AsyncBitcoinRpc(nc.rpchost, nc.rpcport, nc.rpcuser, nc.rpcpassword) as rpc:
            entries = await rpc.getnodeaddresses(0)
    except Exception as e:
        log.warning("RPC getnodeaddresses on node %d failed: %s", nc.id, e)
        return 0

    for entry in entries:
        raw_address: str = entry.get("address", "")
        port: int = entry.get("port", 0)
        network: str = entry.get("network", "")
        last_seen: int = entry.get("time", 0)

        addr_str = normalize_addr(raw_address, port, network)
        identity = NodeIdentity(addr=addr_str)

        if identity not in seen:
            seen.add(identity)
            candidates.append(CandidateNode(
                identity=identity,
                priority=CandidatePriority.ADDRMAN,
                network=network,
                source_node_id=nc.id,
                last_seen=last_seen,
            ))
            added += 1

    return added
