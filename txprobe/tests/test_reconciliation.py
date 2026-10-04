"""Unit tests for Step 5 reconciliation, transitory edge filtering, and full inference topology."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from txprobe.config import Config, DiscoveryConfig, NodeConfig, ReachabilityConfig
from txprobe.groundtruth import GroundtruthResult
from txprobe.models.graph import GraphSnapshot
from txprobe.models.node import NodeIdentity
from txprobe.reconciliation import (
    ReconciliationResult,
    ReconciliationStats,
    canonical_edge,
    capture_final_groundtruth,
    clean_full_inferred_topology,
    identify_invalid_nodes,
    identify_transitory_edges,
    reconcile_topology,
)


def _make_config() -> Config:
    return Config(
        network="testnet4",
        default_port=48333,
        nodes=[
            NodeConfig(0, "probe", 48347, "u0", "p0"),
            NodeConfig(1, "probe", 48332, "u1", "p1"),
            NodeConfig(2, "groundtruth", 48335, "u2", "p2"),
            NodeConfig(3, "groundtruth", 48338, "u3", "p3"),
        ],
        discovery=DiscoveryConfig(),
        reachability=ReachabilityConfig(),
        dns_seeds=[],
    )


def test_graph_snapshot_remove_edges():
    """GraphSnapshot.remove_edges removes specified edges symmetrically and preserves nodes."""
    n1 = NodeIdentity(addr="1.1.1.1:48333")
    n2 = NodeIdentity(addr="2.2.2.2:48333")
    n3 = NodeIdentity(addr="3.3.3.3:48333")
    snapshot = GraphSnapshot(
        nodes=(n1, n2, n3),
        adj_list=MappingProxyType({
            n1: (n2, n3),
            n2: (n1, n3),
            n3: (n1, n2),
        }),
    )
    assert snapshot.num_edges == 3

    # Remove edge (n1, n2) using (str, str)
    updated = snapshot.remove_edges([("2.2.2.2:48333", "1.1.1.1:48333")])
    assert updated.num_nodes == 3
    assert updated.num_edges == 2
    assert updated.adj_list[n1] == (n3,)
    assert updated.adj_list[n2] == (n3,)
    assert set(updated.adj_list[n3]) == {n1, n2}

    # Remove edge (n1, n3) using (NodeIdentity, NodeIdentity)
    updated2 = updated.remove_edges([(n1, n3)])
    assert updated2.num_edges == 1
    assert updated2.adj_list[n1] == ()
    assert updated2.adj_list[n2] == (n3,)
    assert updated2.adj_list[n3] == (n2,)


def test_canonical_edge():
    """canonical_edge sorts endpoint addresses lexicographically."""
    n1 = NodeIdentity(addr="20.0.0.1:48333")
    n2 = NodeIdentity(addr="10.0.0.2:48333")
    assert canonical_edge(n1, n2) == ("10.0.0.2:48333", "20.0.0.1:48333")
    assert canonical_edge("20.0.0.1:48333", "10.0.0.2:48333") == ("10.0.0.2:48333", "20.0.0.1:48333")


def test_identify_transitory_edges():
    """identify_transitory_edges detects dropped and newly formed edges."""
    gt = NodeIdentity(addr="10.0.0.2:48333")
    peer_stable = NodeIdentity(addr="1.1.1.1:48333")
    peer_dropped = NodeIdentity(addr="2.2.2.2:48333")
    peer_formed = NodeIdentity(addr="3.3.3.3:48333")

    gt_before = GraphSnapshot(
        nodes=(gt, peer_stable, peer_dropped),
        adj_list=MappingProxyType({
            gt: (peer_stable, peer_dropped),
            peer_stable: (gt,),
            peer_dropped: (gt,),
        }),
    )

    gt_after = GraphSnapshot(
        nodes=(gt, peer_stable, peer_formed),
        adj_list=MappingProxyType({
            gt: (peer_stable, peer_formed),
            peer_stable: (gt,),
            peer_formed: (gt,),
        }),
    )

    transitory = identify_transitory_edges(
        gt_before, gt_after, groundtruth_node_addrs={gt.addr}
    )
    assert len(transitory) == 2
    # dropped edge (gt, peer_dropped)
    assert canonical_edge(gt, peer_dropped) in transitory
    # formed edge (gt, peer_formed)
    assert canonical_edge(gt, peer_formed) in transitory
    # stable edge is NOT transitory
    assert canonical_edge(gt, peer_stable) not in transitory


def test_identify_invalid_nodes():
    """identify_invalid_nodes aggregates malfunctioning, dropped, and probe disconnects."""
    n1 = NodeIdentity(addr="1.1.1.1:48333")
    n2 = NodeIdentity(addr="2.2.2.2:48333")
    n3 = NodeIdentity(addr="3.3.3.3:48333")
    n4 = NodeIdentity(addr="4.4.4.4:48333")

    inferred = GraphSnapshot(
        nodes=(n1, n2, n3, n4),
        adj_list=MappingProxyType({n: () for n in (n1, n2, n3, n4)}),
    )

    malfunctioning = [n2]
    dropped_step4 = [n3]
    probe_active = {n1, n2, n3}  # n4 disconnected from probes post-probing

    all_inv, malf, drop = identify_invalid_nodes(
        inferred,
        malfunctioning_nodes=malfunctioning,
        dropped_nodes=dropped_step4,
        probe_active_peers=probe_active,
    )

    assert malf == {n2}
    assert drop == {n3, n4}
    assert all_inv == {n2, n3, n4}


def test_clean_full_inferred_topology():
    """clean_full_inferred_topology prunes invalid nodes and eliminates transitory edges."""
    n1 = NodeIdentity(addr="1.1.1.1:48333")
    n2 = NodeIdentity(addr="2.2.2.2:48333")
    n3 = NodeIdentity(addr="3.3.3.3:48333")
    n4 = NodeIdentity(addr="4.4.4.4:48333")

    inferred = GraphSnapshot(
        nodes=(n1, n2, n3, n4),
        adj_list=MappingProxyType({
            n1: (n2, n3, n4),
            n2: (n1,),
            n3: (n1,),
            n4: (n1,),
        }),
    )
    assert inferred.num_edges == 3

    # n2 is malfunctioning, edge (n1, n3) is transitory
    invalid_nodes = [n2]
    transitory_edges = [canonical_edge(n1, n3)]

    cleaned = clean_full_inferred_topology(inferred, invalid_nodes, transitory_edges)
    assert cleaned.nodes == (n1, n3, n4)
    assert cleaned.num_edges == 1
    assert cleaned.adj_list[n1] == (n4,)
    assert cleaned.adj_list[n3] == ()
    assert cleaned.adj_list[n4] == (n1,)


def test_reconcile_topology_end_to_end(tmp_path: Path):
    """reconcile_topology orchestrates full cleanup, groundtruth reconciliation and export."""
    gt = NodeIdentity(addr="10.0.0.2:48333")
    peer_stable = NodeIdentity(addr="1.1.1.1:48333")
    peer_transitory = NodeIdentity(addr="2.2.2.2:48333")
    peer_malfunctioning = NodeIdentity(addr="3.3.3.3:48333")
    peer_pure_public = NodeIdentity(addr="4.4.4.4:48333")

    # Step 4 full inferred snapshot over all 5 nodes
    inferred_snapshot = GraphSnapshot(
        nodes=(gt, peer_stable, peer_transitory, peer_malfunctioning, peer_pure_public),
        adj_list=MappingProxyType({
            gt: (peer_stable, peer_transitory, peer_pure_public),
            peer_stable: (gt, peer_pure_public),
            peer_transitory: (gt,),
            peer_malfunctioning: (gt,),
            peer_pure_public: (gt, peer_stable),
        }),
    )

    # Step 2 groundtruth (before probing)
    gt_before = GraphSnapshot(
        nodes=(gt, peer_stable, peer_transitory, peer_malfunctioning, peer_pure_public),
        adj_list=MappingProxyType({
            gt: (peer_stable, peer_transitory),
            peer_stable: (gt,),
            peer_transitory: (gt,),
            peer_malfunctioning: (),
            peer_pure_public: (),
        }),
    )

    # Post-probing groundtruth: peer_transitory dropped
    gt_after = GraphSnapshot(
        nodes=(gt, peer_stable, peer_malfunctioning, peer_pure_public),
        adj_list=MappingProxyType({
            gt: (peer_stable,),
            peer_stable: (gt,),
            peer_malfunctioning: (),
            peer_pure_public: (),
        }),
    )

    gt_identities = {2: gt}
    malfunctioning = [peer_malfunctioning]
    dropped: list[NodeIdentity] = []

    res = reconcile_topology(
        inferred_snapshot=inferred_snapshot,
        groundtruth_before=gt_before,
        groundtruth_after=gt_after,
        malfunctioning_nodes=malfunctioning,
        dropped_nodes=dropped,
        groundtruth_identities=gt_identities,
    )

    # Verify full inferred topology:
    # - peer_malfunctioning is removed
    # - (gt, peer_transitory) is removed because it was transitory
    # - surviving: gt, peer_stable, peer_transitory, peer_pure_public
    assert set(res.surviving_nodes) == {gt, peer_stable, peer_transitory, peer_pure_public}
    assert res.stats.malfunctioning_nodes_count == 1
    assert res.stats.transitory_edges_count == 1
    assert res.full_inferred_topology.num_nodes == 4
    # edges remaining in full inferred: (gt, peer_stable), (gt, peer_pure_public), (peer_stable, peer_pure_public)
    assert res.full_inferred_topology.num_edges == 3

    # Verify reconciled groundtruth:
    # only stable edge (gt, peer_stable) remains
    assert res.reconciled_groundtruth.num_edges == 1
    assert set(res.reconciled_groundtruth.adj_list[gt]) == {peer_stable}

    # Verify evaluation inferred topology:
    # aligned to groundtruth nodes
    assert res.evaluation_inferred_topology.num_nodes == res.reconciled_groundtruth.num_nodes

    # Test JSON serialization roundtrip
    out_file = tmp_path / "reconciled_topology.json"
    res.save(out_file)
    loaded = ReconciliationResult.load(out_file)

    assert loaded.stats.surviving_full_nodes == res.stats.surviving_full_nodes
    assert loaded.full_inferred_topology.num_edges == res.full_inferred_topology.num_edges
    assert loaded.reconciled_groundtruth.num_edges == res.reconciled_groundtruth.num_edges
    assert loaded.groundtruth_identities == (gt,)

    # Test saving standalone full topology
    full_out = tmp_path / "full_inferred_topology.json"
    res.save_full_inferred_topology(full_out)
    loaded_full = GraphSnapshot.load(full_out)
    assert loaded_full.num_nodes == res.full_inferred_topology.num_nodes
    assert loaded_full.num_edges == res.full_inferred_topology.num_edges


@pytest.mark.asyncio
async def test_capture_final_groundtruth():
    """capture_final_groundtruth queries groundtruth and probe nodes and builds post-probing snapshot."""
    cfg = _make_config()
    target_nodes = [
        NodeIdentity(addr="10.0.0.2:48333"),
        NodeIdentity(addr="1.1.1.1:48333"),
        NodeIdentity(addr="2.2.2.2:48333"),
    ]

    with (
        patch("txprobe.reconciliation.fetch_groundtruth_identities") as mock_fetch_gt,
        patch("txprobe.reconciliation._fetch_probe_peers") as mock_fetch_peers,
    ):
        gt2_ident = NodeIdentity(addr="10.0.0.2:48333")
        mock_fetch_gt.return_value = {2: gt2_ident}

        peer_1 = NodeIdentity(addr="1.1.1.1:48333")
        peer_2 = NodeIdentity(addr="2.2.2.2:48333")

        # mock_fetch_peers called for: probe 0, probe 1, then groundtruth node 2
        mock_fetch_peers.side_effect = [
            {gt2_ident, peer_1, peer_2},  # probe 0
            {gt2_ident, peer_1, peer_2},  # probe 1
            {peer_1},                    # gt node 2 (only connected to peer_1)
        ]

        gt_res = await capture_final_groundtruth(cfg, target_nodes)
        assert isinstance(gt_res, GroundtruthResult)
        assert gt_res.snapshot.num_nodes == 3
        # Edge between gt2 and peer_1 exists
        assert gt_res.snapshot.adj_list[gt2_ident] == (peer_1,)
        assert gt_res.snapshot.adj_list[peer_1] == (gt2_ident,)
        assert gt_res.snapshot.adj_list[peer_2] == ()
