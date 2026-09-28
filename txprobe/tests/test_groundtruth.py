"""Tests for Step 1 initial groundtruth capture."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from txprobe.config import Config, DiscoveryConfig, NodeConfig, ReachabilityConfig
from txprobe.groundtruth import (
    GroundtruthResult,
    GroundtruthStats,
    capture_initial_groundtruth,
    fetch_groundtruth_identities,
    get_node_onion_identity,
)
from txprobe.models.graph import GraphSnapshot
from txprobe.models.node import NodeIdentity


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


def _peer(
    addr: str,
    conn_type: str = "outbound-full-relay",
    version: int = 70016,
    network: str = "ipv4",
) -> dict:
    return {
        "addr": addr,
        "connection_type": conn_type,
        "version": version,
        "network": network,
        "inbound": False,
    }


@pytest.mark.asyncio
async def test_get_node_onion_identity_prefers_onion():
    """get_node_onion_identity extracts the .onion address when multiple localaddresses exist."""
    nc = NodeConfig(2, "groundtruth", 48335, "u2", "p2")

    with patch("txprobe.groundtruth.AsyncBitcoinRpc") as MockRpc:
        mock_rpc = AsyncMock()
        mock_rpc.getnetworkinfo = AsyncMock(return_value={
            "localaddresses": [
                {"address": "8.8.8.8", "port": 48333},
                {"address": "gt2abc.onion", "port": 48333},
            ],
        })
        MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_rpc)
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        ident = await get_node_onion_identity(nc, 48333)

    assert ident == NodeIdentity("gt2abc.onion:48333")


@pytest.mark.asyncio
async def test_get_node_onion_identity_offline_returns_none():
    """get_node_onion_identity returns None gracefully when the node is offline."""
    nc = NodeConfig(2, "groundtruth", 48335, "u2", "p2")

    with patch("txprobe.groundtruth.AsyncBitcoinRpc") as MockRpc:
        MockRpc.return_value.__aenter__ = AsyncMock(
            side_effect=ConnectionRefusedError("Node offline")
        )
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        ident = await get_node_onion_identity(nc, 48333)

    assert ident is None


@pytest.mark.asyncio
async def test_fetch_groundtruth_identities_parallel():
    """fetch_groundtruth_identities returns a mapping of online groundtruth node IDs to identities."""
    cfg = _make_config()

    def _rpc_factory(host, port, user, password, wallet=""):
        ctx = AsyncMock()
        client = AsyncMock()
        if port == 48335:
            client.getnetworkinfo = AsyncMock(return_value={
                "localaddresses": [{"address": "gt2.onion", "port": 48333}],
            })
        else:
            client.getnetworkinfo = AsyncMock(return_value={"localaddresses": []})
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    with patch("txprobe.groundtruth.AsyncBitcoinRpc", side_effect=_rpc_factory):
        identities = await fetch_groundtruth_identities(cfg)

    assert identities == {2: NodeIdentity("gt2.onion:48333")}


@pytest.mark.asyncio
async def test_capture_initial_groundtruth_builds_symmetric_adj_and_prunes_dropped():
    """capture_initial_groundtruth builds undirected edges, filters block-relay-only, and prunes dropped nodes."""
    cfg = _make_config()

    gt2 = NodeIdentity("gt2.onion:48333")
    gt3 = NodeIdentity("gt3.onion:48333")
    peer_a = NodeIdentity("1.1.1.1:48333")
    peer_b = NodeIdentity("2.2.2.2:48333")
    peer_dropped = NodeIdentity("9.9.9.9:48333")  # dropped from Probe 1

    target_nodes = [gt2, gt3, peer_a, peer_b, peer_dropped]

    def _rpc_factory(host, port, user, password, wallet=""):
        ctx = AsyncMock()
        client = AsyncMock()
        client.call_batch = AsyncMock(return_value=[None])

        if port == 48347:  # Probe 0 (still has peer_dropped)
            client.getpeerinfo = AsyncMock(return_value=[
                _peer(gt2.addr, conn_type="manual", network="onion"),
                _peer(gt3.addr, conn_type="manual", network="onion"),
                _peer(peer_a.addr, conn_type="manual"),
                _peer(peer_b.addr, conn_type="manual"),
                _peer(peer_dropped.addr, conn_type="manual"),
            ])
        elif port == 48332:  # Probe 1 (peer_dropped disconnected)
            client.getpeerinfo = AsyncMock(return_value=[
                _peer(gt2.addr, conn_type="manual", network="onion"),
                _peer(gt3.addr, conn_type="manual", network="onion"),
                _peer(peer_a.addr, conn_type="manual"),
                _peer(peer_b.addr, conn_type="manual"),
            ])
        elif port == 48335:  # Groundtruth 2
            client.getnetworkinfo = AsyncMock(return_value={
                "localaddresses": [{"address": "gt2.onion", "port": 48333}],
            })
            client.getpeerinfo = AsyncMock(return_value=[
                _peer(peer_a.addr, conn_type="outbound-full-relay"),
                # block-relay-only peer should be ignored for TxProbe groundtruth
                _peer(peer_b.addr, conn_type="block-relay-only"),
                # dropped peer should not appear in adj_list
                _peer(peer_dropped.addr, conn_type="outbound-full-relay"),
                # local 127.0.0.1 should be ignored
                _peer("127.0.0.1:55000", conn_type="inbound"),
            ])
        elif port == 48338:  # Groundtruth 3
            client.getnetworkinfo = AsyncMock(return_value={
                "localaddresses": [{"address": "gt3.onion", "port": 48333}],
            })
            client.getpeerinfo = AsyncMock(return_value=[
                _peer(peer_b.addr, conn_type="outbound-full-relay"),
                _peer(gt2.addr, conn_type="outbound-full-relay", network="onion"),
            ])

        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    with patch("txprobe.groundtruth.AsyncBitcoinRpc", side_effect=_rpc_factory):
        result = await capture_initial_groundtruth(cfg, target_nodes)

    assert result.stats.groundtruth_nodes_configured == 2
    assert result.stats.groundtruth_nodes_online == 2
    assert result.stats.input_target_nodes == 5
    assert result.stats.active_nodes_count == 4
    assert result.stats.pruned_disconnected_count == 1
    assert result.stats.groundtruth_edges_count == 3  # (gt2, peer_a), (gt3, peer_b), (gt3, gt2)

    snap = result.snapshot
    assert snap.num_nodes == 4
    assert snap.num_edges == 3
    assert peer_dropped not in snap.nodes

    # Verify symmetric undirected adjacency list
    assert set(snap.adj_list[gt2]) == {peer_a, gt3}
    assert set(snap.adj_list[peer_a]) == {gt2}
    assert set(snap.adj_list[gt3]) == {peer_b, gt2}
    assert set(snap.adj_list[peer_b]) == {gt3}


def test_groundtruth_result_save_and_load(tmp_path):
    """GroundtruthResult and GraphSnapshot save/load preserve all fields."""
    gt2 = NodeIdentity("gt2.onion:48333")
    p1 = NodeIdentity("1.2.3.4:48333")

    snap = GraphSnapshot.from_dict({
        "nodes": [gt2.addr, p1.addr],
        "adj_list": {
            gt2.addr: [p1.addr],
            p1.addr: [gt2.addr],
        },
    })

    res = GroundtruthResult(
        snapshot=snap,
        groundtruth_identities={2: gt2},
        stats=GroundtruthStats(
            groundtruth_nodes_configured=5,
            groundtruth_nodes_online=1,
            input_target_nodes=2,
            active_nodes_count=2,
            pruned_disconnected_count=0,
            groundtruth_edges_count=1,
            elapsed_sec=0.45,
            timestamp="2026-09-29T01:15:00Z",
        ),
    )

    out_path = tmp_path / "initial_groundtruth.json"
    res.save(out_path)
    loaded = GroundtruthResult.load(out_path)

    assert loaded.groundtruth_identities == {2: gt2}
    assert loaded.snapshot.num_nodes == 2
    assert loaded.snapshot.num_edges == 1
    assert loaded.stats.groundtruth_edges_count == 1

    # Also test GraphSnapshot.save / load directly
    snap_path = tmp_path / "snap.json"
    snap.save(snap_path)
    loaded_snap = GraphSnapshot.load(snap_path)
    assert loaded_snap.nodes == snap.nodes
    assert dict(loaded_snap.adj_list) == dict(snap.adj_list)
