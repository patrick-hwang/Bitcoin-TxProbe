"""Step 5 — Malfunction Filtering, Post-Probing Groundtruth Reconciliation & Full Inference Topology."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .config import Config, NodeConfig
from .groundtruth import (
    GroundtruthResult,
    _fetch_probe_peers,
    fetch_groundtruth_identities,
)
from .models.graph import GraphSnapshot
from .models.node import NodeIdentity
from .rpc.client import AsyncBitcoinRpc

log = logging.getLogger(__name__)


def canonical_edge(u: str | NodeIdentity, v: str | NodeIdentity) -> tuple[str, str]:
    """Return canonical undirected edge tuple sorted lexicographically."""
    u_addr = u.addr if hasattr(u, "addr") else str(u)
    v_addr = v.addr if hasattr(v, "addr") else str(v)
    return (u_addr, v_addr) if u_addr <= v_addr else (v_addr, u_addr)


@dataclass(frozen=True)
class ReconciliationStats:
    """Telemetry and counts for Step 5 reconciliation."""

    initial_full_nodes: int = 0
    surviving_full_nodes: int = 0
    full_inferred_edges_count: int = 0
    malfunctioning_nodes_count: int = 0
    dropped_nodes_count: int = 0
    transitory_edges_count: int = 0
    groundtruth_eval_nodes_count: int = 0
    groundtruth_eval_edges_count: int = 0
    elapsed_sec: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "initial_full_nodes": self.initial_full_nodes,
            "surviving_full_nodes": self.surviving_full_nodes,
            "full_inferred_edges_count": self.full_inferred_edges_count,
            "malfunctioning_nodes_count": self.malfunctioning_nodes_count,
            "dropped_nodes_count": self.dropped_nodes_count,
            "transitory_edges_count": self.transitory_edges_count,
            "groundtruth_eval_nodes_count": self.groundtruth_eval_nodes_count,
            "groundtruth_eval_edges_count": self.groundtruth_eval_edges_count,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReconciliationStats:
        """Deserialize from a dictionary."""
        return cls(
            initial_full_nodes=int(data.get("initial_full_nodes", 0)),
            surviving_full_nodes=int(data.get("surviving_full_nodes", 0)),
            full_inferred_edges_count=int(data.get("full_inferred_edges_count", 0)),
            malfunctioning_nodes_count=int(data.get("malfunctioning_nodes_count", 0)),
            dropped_nodes_count=int(data.get("dropped_nodes_count", 0)),
            transitory_edges_count=int(data.get("transitory_edges_count", 0)),
            groundtruth_eval_nodes_count=int(
                data.get("groundtruth_eval_nodes_count", 0)
            ),
            groundtruth_eval_edges_count=int(
                data.get("groundtruth_eval_edges_count", 0)
            ),
            elapsed_sec=float(data.get("elapsed_sec", 0.0)),
            timestamp=str(data.get("timestamp", "")),
        )


@dataclass(frozen=True)
class ReconciliationResult:
    """Complete output of Step 5 reconciliation."""

    full_inferred_topology: GraphSnapshot
    reconciled_groundtruth: GraphSnapshot
    evaluation_inferred_topology: GraphSnapshot
    surviving_nodes: tuple[NodeIdentity, ...]
    malfunctioning_nodes_removed: tuple[NodeIdentity, ...]
    dropped_nodes_removed: tuple[NodeIdentity, ...]
    transitory_edges_removed: tuple[tuple[str, str], ...]
    stats: ReconciliationStats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "timestamp": self.stats.timestamp,
            "elapsed_sec": round(self.stats.elapsed_sec, 2),
            "stats": self.stats.to_dict(),
            "surviving_nodes": [n.addr for n in self.surviving_nodes],
            "malfunctioning_nodes_removed": [
                n.addr for n in self.malfunctioning_nodes_removed
            ],
            "dropped_nodes_removed": [n.addr for n in self.dropped_nodes_removed],
            "transitory_edges_removed": [
                list(edge) for edge in self.transitory_edges_removed
            ],
            "full_inferred_topology": self.full_inferred_topology.to_dict(),
            "reconciled_groundtruth": self.reconciled_groundtruth.to_dict(),
            "evaluation_inferred_topology": self.evaluation_inferred_topology.to_dict(),
        }

    def save(self, path: str | Path) -> None:
        """Write complete reconciliation result to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def save_full_inferred_topology(self, path: str | Path) -> None:
        """Write standalone full inferred network topology to a JSON file."""
        self.full_inferred_topology.save(path)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReconciliationResult:
        """Deserialize from a dictionary."""
        stats = ReconciliationStats.from_dict(data.get("stats", {}))
        surviving = tuple(
            NodeIdentity(addr=a) for a in data.get("surviving_nodes", [])
        )
        malfunctioning = tuple(
            NodeIdentity(addr=a)
            for a in data.get("malfunctioning_nodes_removed", [])
        )
        dropped = tuple(
            NodeIdentity(addr=a) for a in data.get("dropped_nodes_removed", [])
        )
        transitory = tuple(
            (str(e[0]), str(e[1])) for e in data.get("transitory_edges_removed", [])
        )
        full_inf = GraphSnapshot.from_dict(data["full_inferred_topology"])
        rec_gt = GraphSnapshot.from_dict(data["reconciled_groundtruth"])
        eval_inf = GraphSnapshot.from_dict(data["evaluation_inferred_topology"])

        return cls(
            full_inferred_topology=full_inf,
            reconciled_groundtruth=rec_gt,
            evaluation_inferred_topology=eval_inf,
            surviving_nodes=surviving,
            malfunctioning_nodes_removed=malfunctioning,
            dropped_nodes_removed=dropped,
            transitory_edges_removed=transitory,
            stats=stats,
        )

    @classmethod
    def load(cls, path: str | Path) -> ReconciliationResult:
        """Load a ReconciliationResult from a JSON file."""
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


def identify_transitory_edges(
    groundtruth_before: GraphSnapshot,
    groundtruth_after: GraphSnapshot,
    groundtruth_node_addrs: set[str] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Find all edges incident to groundtruth nodes that connected or disconnected mid-probing.

    An edge (u, v) is transitory if:
    - (u, v) in E_before but (u, v) not in E_after (disconnected mid-probing), OR
    - (u, v) not in E_before but (u, v) in E_after (formed mid-probing).

    Args:
        groundtruth_before: Pre-probing groundtruth graph snapshot.
        groundtruth_after: Post-probing groundtruth graph snapshot.
        groundtruth_node_addrs: Optional set of groundtruth node addresses.
            If provided, only edges incident to at least one groundtruth node are considered.

    Returns:
        Sorted tuple of canonical edge pairs ((u_addr, v_addr), ...).
    """
    edges_before: set[tuple[str, str]] = set()
    for u, neighbors in groundtruth_before.adj_list.items():
        for v in neighbors:
            edge = canonical_edge(u, v)
            if groundtruth_node_addrs is None or (
                edge[0] in groundtruth_node_addrs or edge[1] in groundtruth_node_addrs
            ):
                edges_before.add(edge)

    edges_after: set[tuple[str, str]] = set()
    for u, neighbors in groundtruth_after.adj_list.items():
        for v in neighbors:
            edge = canonical_edge(u, v)
            if groundtruth_node_addrs is None or (
                edge[0] in groundtruth_node_addrs or edge[1] in groundtruth_node_addrs
            ):
                edges_after.add(edge)

    dropped_mid_probing = edges_before - edges_after
    formed_mid_probing = edges_after - edges_before
    transitory = dropped_mid_probing | formed_mid_probing

    return tuple(sorted(transitory))


def identify_invalid_nodes(
    inferred_snapshot: GraphSnapshot,
    malfunctioning_nodes: Iterable[NodeIdentity],
    dropped_nodes: Iterable[NodeIdentity],
    probe_active_peers: set[NodeIdentity] | None = None,
) -> tuple[set[NodeIdentity], set[NodeIdentity], set[NodeIdentity]]:
    """Identify all invalid nodes that cannot be reliably included in the topology.

    Args:
        inferred_snapshot: Graph snapshot from Step 4 inference.
        malfunctioning_nodes: Source nodes flagged as malfunctioning in Step 4.
        dropped_nodes: Nodes that dropped during Step 4 round execution.
        probe_active_peers: Set of mutual active peers verified on Probe 0 and Probe 1
            post-probing. If provided, any node in inferred_snapshot not in this set is
            treated as dropped.

    Returns:
        Tuple of (all_invalid_nodes, malfunctioning_set, dropped_set).
    """
    malfunction_set = set(malfunctioning_nodes)
    dropped_set = set(dropped_nodes)

    if probe_active_peers is not None:
        for node in inferred_snapshot.nodes:
            if node not in probe_active_peers:
                dropped_set.add(node)

    all_invalid = malfunction_set | dropped_set
    return all_invalid, malfunction_set, dropped_set


def clean_full_inferred_topology(
    inferred_snapshot: GraphSnapshot,
    invalid_nodes: Iterable[NodeIdentity],
    transitory_edges: Iterable[tuple[str, str] | tuple[NodeIdentity, NodeIdentity]],
) -> GraphSnapshot:
    """Clean the full network inferred topology by removing invalid nodes and transitory edges.

    Args:
        inferred_snapshot: Inferred graph snapshot across all nodes.
        invalid_nodes: Nodes to prune (malfunctioning or dropped).
        transitory_edges: Known transitory edges to remove.

    Returns:
        Clean GraphSnapshot representing the full surviving network topology.
    """
    cleaned = inferred_snapshot.remove_nodes(invalid_nodes)
    cleaned = cleaned.remove_edges(transitory_edges)
    return cleaned


def reconcile_topology(
    inferred_snapshot: GraphSnapshot,
    groundtruth_before: GraphSnapshot,
    groundtruth_after: GraphSnapshot,
    malfunctioning_nodes: Iterable[NodeIdentity],
    dropped_nodes: Iterable[NodeIdentity],
    *,
    probe_active_peers: set[NodeIdentity] | None = None,
    groundtruth_identities: Mapping[int, NodeIdentity] | None = None,
) -> ReconciliationResult:
    """Reconcile Step 4 inference with Step 1/2 and post-probing groundtruth snapshots.

    Symmetrically:
    1. Identifies transitory edges from groundtruth before & after probing.
    2. Identifies all invalid nodes (malfunctioning, mid-probing drops, post-probing drops).
    3. Cleans the full ~1000-node inferred topology by eliminating invalid nodes and transitory edges.
    4. Symmetrically eliminates transitory edges and invalid nodes from groundtruth.
    5. Extracts the aligned evaluation slice of the inferred topology.

    Args:
        inferred_snapshot: Full inferred graph snapshot from Step 4.
        groundtruth_before: Pre-probing groundtruth graph snapshot (Step 2 or Step 1).
        groundtruth_after: Post-probing groundtruth graph snapshot.
        malfunctioning_nodes: Nodes flagged as malfunctioning in Step 4.
        dropped_nodes: Nodes that dropped during Step 4.
        probe_active_peers: Optional mutual peer set from Probe 0 and Probe 1 post-probing.
        groundtruth_identities: Optional mapping of node ID -> NodeIdentity for Groundtruth nodes [2..6].

    Returns:
        ReconciliationResult with full_inferred_topology, reconciled_groundtruth, and evaluation slice.
    """
    t0 = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()

    gt_addrs = None
    if groundtruth_identities is not None:
        gt_addrs = {ident.addr for ident in groundtruth_identities.values()}

    # 1. Identify transitory edges incident to groundtruth nodes
    transitory_edges = identify_transitory_edges(
        groundtruth_before, groundtruth_after, groundtruth_node_addrs=gt_addrs
    )
    log.info("Identified %d transitory edges incident to groundtruth", len(transitory_edges))

    # 2. Identify all invalid nodes
    invalid_nodes, malfunction_set, dropped_set = identify_invalid_nodes(
        inferred_snapshot,
        malfunctioning_nodes=malfunctioning_nodes,
        dropped_nodes=dropped_nodes,
        probe_active_peers=probe_active_peers,
    )
    log.info(
        "Identified %d invalid nodes (%d malfunctioning, %d dropped)",
        len(invalid_nodes),
        len(malfunction_set),
        len(dropped_set),
    )

    # 3. Clean full inferred topology across all ~1000 nodes
    full_inferred_topology = clean_full_inferred_topology(
        inferred_snapshot,
        invalid_nodes=invalid_nodes,
        transitory_edges=transitory_edges,
    )
    surviving_nodes = full_inferred_topology.nodes
    surviving_set = set(surviving_nodes)

    # 4. Symmetrically reconcile groundtruth: remove transitory edges & prune invalid nodes
    rec_gt_temp = groundtruth_before.remove_edges(transitory_edges)
    reconciled_groundtruth = rec_gt_temp.prune_nodes(surviving_set)

    # 5. Extract evaluation slice of inference aligned with groundtruth nodes
    # For Step 6 evaluation, the vertex set is the groundtruth evaluation universe
    gt_eval_nodes = set(reconciled_groundtruth.nodes)
    evaluation_inferred_topology = full_inferred_topology.prune_nodes(gt_eval_nodes)

    elapsed = time.monotonic() - t0

    stats = ReconciliationStats(
        initial_full_nodes=inferred_snapshot.num_nodes,
        surviving_full_nodes=full_inferred_topology.num_nodes,
        full_inferred_edges_count=full_inferred_topology.num_edges,
        malfunctioning_nodes_count=len(malfunction_set),
        dropped_nodes_count=len(dropped_set),
        transitory_edges_count=len(transitory_edges),
        groundtruth_eval_nodes_count=reconciled_groundtruth.num_nodes,
        groundtruth_eval_edges_count=reconciled_groundtruth.num_edges,
        elapsed_sec=elapsed,
        timestamp=timestamp,
    )

    log.info(
        "Step 5 reconciliation complete: %d full surviving nodes (%d edges), "
        "%d groundtruth eval nodes (%d edges) in %.2fs",
        stats.surviving_full_nodes,
        stats.full_inferred_edges_count,
        stats.groundtruth_eval_nodes_count,
        stats.groundtruth_eval_edges_count,
        stats.elapsed_sec,
    )

    return ReconciliationResult(
        full_inferred_topology=full_inferred_topology,
        reconciled_groundtruth=reconciled_groundtruth,
        evaluation_inferred_topology=evaluation_inferred_topology,
        surviving_nodes=surviving_nodes,
        malfunctioning_nodes_removed=tuple(
            sorted(malfunction_set, key=lambda n: n.addr)
        ),
        dropped_nodes_removed=tuple(sorted(dropped_set, key=lambda n: n.addr)),
        transitory_edges_removed=transitory_edges,
        stats=stats,
    )


async def capture_final_groundtruth(
    config: Config,
    active_nodes: Iterable[NodeIdentity],
) -> GroundtruthResult:
    """Capture post-probing groundtruth snapshot from online groundtruth nodes [2..6] and probes [0, 1].

    Args:
        config: Experiment configuration.
        active_nodes: Target active nodes from Step 4.

    Returns:
        GroundtruthResult representing post-probing topology state.
    """
    t0 = time.monotonic()
    probes = config.probe_nodes
    if len(probes) < 2:
        raise ValueError(f"At least 2 probe nodes required, found {len(probes)}")

    probe_a, probe_b = probes[0], probes[1]
    active_set = set(active_nodes)

    # 1. Fetch groundtruth identities and probe peer sets in parallel
    gt_identities, peers_a, peers_b = await asyncio.gather(
        fetch_groundtruth_identities(config),
        _fetch_probe_peers(probe_a),
        _fetch_probe_peers(probe_b),
    )

    mutual_probe_peers = peers_a & peers_b
    online_gt_identities = {
        node_id: ident
        for node_id, ident in gt_identities.items()
        if ident in mutual_probe_peers
    }

    # 2. Query peer lists on online groundtruth nodes
    gt_configs_online = [
        config.get_node(node_id) for node_id in sorted(online_gt_identities)
    ]
    gt_peer_sets = await asyncio.gather(
        *[_fetch_probe_peers(nc) for nc in gt_configs_online]
    )

    ordered_nodes = list(dict.fromkeys(active_nodes))
    adj_raw: dict[NodeIdentity, set[NodeIdentity]] = {node: set() for node in ordered_nodes}
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
        nodes=tuple(ordered_nodes),
        adj_list=adj_immutable,
    )

    elapsed = time.monotonic() - t0
    timestamp = datetime.now(timezone.utc).isoformat()

    return GroundtruthResult(
        snapshot=snapshot,
        groundtruth_identities=online_gt_identities,
    )
