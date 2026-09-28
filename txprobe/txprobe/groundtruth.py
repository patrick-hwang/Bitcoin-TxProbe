"""Step 1 — Groundtruth topology capture."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

from .config import Config, NodeConfig
from .discovery.peer_scanner import _disconnect_excess_peers, _extract_valid_probe_peers
from .models.graph import GraphSnapshot
from .models.node import NodeIdentity, normalize_addr
from .rpc.client import AsyncBitcoinRpc

log = logging.getLogger(__name__)


@dataclass
class GroundtruthStats:
    """Statistics from the Step 1 initial groundtruth capture."""
    groundtruth_nodes_configured: int = 0
    groundtruth_nodes_online: int = 0
    input_target_nodes: int = 0
    active_nodes_count: int = 0
    pruned_disconnected_count: int = 0
    groundtruth_edges_count: int = 0
    elapsed_sec: float = 0.0
    timestamp: str = ""


@dataclass
class GroundtruthResult:
    """Output of Step 1 groundtruth capture."""
    snapshot: GraphSnapshot
    groundtruth_identities: dict[int, NodeIdentity] = field(default_factory=dict)
    stats: GroundtruthStats = field(default_factory=GroundtruthStats)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "timestamp": self.stats.timestamp,
            "elapsed_sec": round(self.stats.elapsed_sec, 2),
            "stats": {
                "groundtruth_nodes_configured": self.stats.groundtruth_nodes_configured,
                "groundtruth_nodes_online": self.stats.groundtruth_nodes_online,
                "input_target_nodes": self.stats.input_target_nodes,
                "active_nodes_count": self.stats.active_nodes_count,
                "pruned_disconnected_count": self.stats.pruned_disconnected_count,
                "groundtruth_edges_count": self.stats.groundtruth_edges_count,
            },
            "groundtruth_identities": {
                str(node_id): identity.addr
                for node_id, identity in sorted(self.groundtruth_identities.items())
            },
            "snapshot": self.snapshot.to_dict(),
        }

    def save(self, path: str | Path) -> None:
        """Write groundtruth result to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> GroundtruthResult:
        """Deserialize a GroundtruthResult from a JSON dict."""
        raw_stats = data.get("stats", {})
        stats = GroundtruthStats(
            groundtruth_nodes_configured=int(
                raw_stats.get("groundtruth_nodes_configured", 0)
            ),
            groundtruth_nodes_online=int(raw_stats.get("groundtruth_nodes_online", 0)),
            input_target_nodes=int(raw_stats.get("input_target_nodes", 0)),
            active_nodes_count=int(raw_stats.get("active_nodes_count", 0)),
            pruned_disconnected_count=int(
                raw_stats.get("pruned_disconnected_count", 0)
            ),
            groundtruth_edges_count=int(raw_stats.get("groundtruth_edges_count", 0)),
            elapsed_sec=float(data.get("elapsed_sec", 0.0)),
            timestamp=str(data.get("timestamp", "")),
        )

        gt_identities: dict[int, NodeIdentity] = {
            int(k): NodeIdentity(addr=str(v))
            for k, v in data.get("groundtruth_identities", {}).items()
        }

        snapshot = GraphSnapshot.from_dict(data["snapshot"])
        return cls(
            snapshot=snapshot,
            groundtruth_identities=gt_identities,
            stats=stats,
        )

    @classmethod
    def load(cls, path: str | Path) -> GroundtruthResult:
        """Load a GroundtruthResult from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


async def get_node_onion_identity(
    nc: NodeConfig, default_port: int = 48333
) -> NodeIdentity | None:
    """Query getnetworkinfo() on *nc* and extract its .onion (or external) NodeIdentity.

    Args:
        nc: Node configuration.
        default_port: Default network port if missing in localaddresses.

    Returns:
        NodeIdentity if available, or None if the node is offline or has no localaddresses.
    """
    try:
        async with AsyncBitcoinRpc(nc.rpchost, nc.rpcport, nc.rpcuser, nc.rpcpassword) as rpc:
            info = await rpc.getnetworkinfo()
    except Exception as e:
        log.warning("getnetworkinfo failed on node %d: %s", nc.id, e)
        return None

    local_addrs: list[dict] = info.get("localaddresses", [])
    if not local_addrs:
        log.warning("Node %d has no localaddresses in getnetworkinfo", nc.id)
        return None

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
        log.warning("Node %d has no non-local address in localaddresses", nc.id)
        return None

    raw_addr = str(chosen["address"])
    port = int(chosen.get("port", default_port))
    network = "onion" if raw_addr.endswith(".onion") else ("ipv6" if ":" in raw_addr else "ipv4")
    return NodeIdentity(addr=normalize_addr(raw_addr, port, network))


async def fetch_groundtruth_identities(config: Config) -> dict[int, NodeIdentity]:
    """Fetch NodeIdentity for all groundtruth nodes in parallel.

    Args:
        config: Experiment configuration.

    Returns:
        Mapping of groundtruth node id → NodeIdentity for online groundtruth nodes.
    """
    gt_configs = config.groundtruth_nodes
    tasks = [
        get_node_onion_identity(nc, config.default_port) for nc in gt_configs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    identities: dict[int, NodeIdentity] = {}
    for nc, res in zip(gt_configs, results):
        if isinstance(res, Exception):
            log.warning("Failed to get identity for groundtruth node %d: %s", nc.id, res)
        elif res is not None:
            identities[nc.id] = res
    return identities


async def capture_initial_groundtruth(
    config: Config,
    target_nodes: Iterable[NodeIdentity],
    *,
    disconnect_chunk_size: int = 50,
) -> GroundtruthResult:
    """Main Step 1 entry point — capture initial groundtruth topology snapshot.

    Steps:
        1.1  Fetch .onion (or external) identities of groundtruth nodes [2..6]
             in parallel via ``getnetworkinfo``.
        1.2  Query ``getpeerinfo`` on Probe 0 and Probe 1 in parallel to determine
             currently active mutual peers; prune any target node that dropped
             since Step 0 and disconnect it on the remaining probe.
        1.3  Query ``getpeerinfo`` on groundtruth nodes [2..6] in parallel (excluding
             ``127.0.0.1*``, ``feeler``, ``addr-fetch``, ``block-relay-only``, and
             unhandshaked ``version <= 0`` peers) and record undirected edges
             ``(gt_i, peer_j)`` where both endpoints belong to ``active_nodes``.
        1.4  Return immutable ``GraphSnapshot`` wrapped in ``GroundtruthResult``.

    Args:
        config: Experiment configuration.
        target_nodes: Target node identities selected in Step 0 Phase 2.
        disconnect_chunk_size: Batch size for disconnecting half-dropped peers.

    Returns:
        GroundtruthResult containing the initial GraphSnapshot, groundtruth
        node identities, and capture statistics.

    Raises:
        ValueError: If fewer than 2 probe nodes are configured in *config*.
    """
    probes = config.probe_nodes
    if len(probes) < 2:
        raise ValueError(
            f"At least 2 probe nodes are required, found {len(probes)}"
        )

    probe_a, probe_b = probes[0], probes[1]
    t0 = time.monotonic()

    target_list = list(dict.fromkeys(target_nodes))
    target_set = set(target_list)

    stats = GroundtruthStats(
        groundtruth_nodes_configured=len(config.groundtruth_nodes),
        input_target_nodes=len(target_list),
    )

    # ── Step 1.1: Fetch groundtruth self-identities & probe peer lists in parallel ──
    log.info("Step 1.1: Fetching groundtruth identities and probe peer lists...")
    gt_identities, peers_a, peers_b = await asyncio.gather(
        fetch_groundtruth_identities(config),
        _fetch_probe_peers(probe_a),
        _fetch_probe_peers(probe_b),
    )

    mutual_probe_peers = peers_a & peers_b
    candidate_universe = target_set | set(gt_identities.values())
    active_set = candidate_universe & mutual_probe_peers

    # Count how many groundtruth nodes are online and mutually connected to both probes
    online_gt_identities = {
        node_id: ident
        for node_id, ident in gt_identities.items()
        if ident in active_set
    }
    stats.groundtruth_nodes_online = len(online_gt_identities)

    # Preserve ordering: groundtruth identities first, then remaining target_list order
    ordered_active: list[NodeIdentity] = []
    seen_active: set[NodeIdentity] = set()
    for _, ident in sorted(online_gt_identities.items()):
        if ident in active_set and ident not in seen_active:
            ordered_active.append(ident)
            seen_active.add(ident)
    for ident in target_list:
        if ident in active_set and ident not in seen_active:
            ordered_active.append(ident)
            seen_active.add(ident)

    stats.active_nodes_count = len(ordered_active)
    stats.pruned_disconnected_count = len(target_set - active_set)

    # ── Step 1.2: Disconnect any half-connected peers on Probe A and Probe B ──
    if (peers_a - active_set) or (peers_b - active_set):
        async with (
            AsyncBitcoinRpc(probe_a.rpchost, probe_a.rpcport, probe_a.rpcuser, probe_a.rpcpassword) as rpc_a,
            AsyncBitcoinRpc(probe_b.rpchost, probe_b.rpcport, probe_b.rpcuser, probe_b.rpcpassword) as rpc_b,
        ):
            await asyncio.gather(
                _disconnect_excess_peers(rpc_a, active_set, peers_a, disconnect_chunk_size),
                _disconnect_excess_peers(rpc_b, active_set, peers_b, disconnect_chunk_size),
            )

    # ── Step 1.3: Query getpeerinfo on online groundtruth nodes and build adj_list ──
    log.info(
        "Step 1.2: Querying peer lists on %d online groundtruth nodes...",
        len(online_gt_identities),
    )
    gt_configs_online = [
        config.get_node(node_id) for node_id in sorted(online_gt_identities)
    ]
    gt_peer_sets = await asyncio.gather(
        *[_fetch_probe_peers(nc) for nc in gt_configs_online]
    )

    adj_raw: dict[NodeIdentity, set[NodeIdentity]] = defaultdict(set)
    for nc, peer_set in zip(gt_configs_online, gt_peer_sets):
        gt_ident = online_gt_identities[nc.id]
        for peer_ident in peer_set:
            if peer_ident in active_set and peer_ident != gt_ident:
                adj_raw[gt_ident].add(peer_ident)
                adj_raw[peer_ident].add(gt_ident)

    adj_immutable = MappingProxyType({
        node: tuple(sorted(neighbors, key=lambda n: n.addr))
        for node, neighbors in sorted(adj_raw.items(), key=lambda item: item[0].addr)
    })

    snapshot = GraphSnapshot(
        nodes=tuple(ordered_active),
        adj_list=adj_immutable,
    )
    stats.groundtruth_edges_count = snapshot.num_edges
    stats.elapsed_sec = time.monotonic() - t0
    stats.timestamp = datetime.now(timezone.utc).isoformat()

    log.info(
        "Step 1 complete: %d active nodes (%d groundtruth online), %d groundtruth edges in %.2fs",
        stats.active_nodes_count,
        stats.groundtruth_nodes_online,
        stats.groundtruth_edges_count,
        stats.elapsed_sec,
    )

    return GroundtruthResult(
        snapshot=snapshot,
        groundtruth_identities=online_gt_identities,
        stats=stats,
    )


async def _fetch_probe_peers(nc: NodeConfig) -> set[NodeIdentity]:
    """Call getpeerinfo() on a node and return valid full-relay peer identities."""
    try:
        async with AsyncBitcoinRpc(nc.rpchost, nc.rpcport, nc.rpcuser, nc.rpcpassword) as rpc:
            peers_raw = await rpc.getpeerinfo()
        return _extract_valid_probe_peers(peers_raw)
    except Exception as e:
        log.warning("getpeerinfo failed on node %d: %s", nc.id, e)
        return set()
