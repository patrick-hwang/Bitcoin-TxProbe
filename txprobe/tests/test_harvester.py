"""Tests for the Phase 1 address harvester."""

from unittest.mock import AsyncMock, patch

import pytest

from txprobe.config import Config, DiscoveryConfig, NodeConfig, ReachabilityConfig
from txprobe.discovery.harvester import (
    _harvest_addrman_one,
    _harvest_peers_one,
    harvest_addresses,
)
from txprobe.models.node import CandidateNode, CandidatePriority, NodeIdentity


def _make_config(**overrides) -> Config:
    """Build a minimal Config for tests."""
    defaults = dict(
        network="testnet4",
        default_port=48333,
        nodes=[
            NodeConfig(0, "probe", 48347, "u0", "p0"),
            NodeConfig(1, "groundtruth", 48332, "u1", "p1"),
            NodeConfig(6, "probe", 48350, "u6", "p6"),
        ],
        discovery=DiscoveryConfig(target_count=100),
        reachability=ReachabilityConfig(clearnet_concurrency=5, tor_concurrency=2),
        dns_seeds=["seed.example.com"],
    )
    defaults.update(overrides)
    return Config(**defaults)


def _peer(addr: str, network: str = "ipv4", conn_type: str = "outbound-full-relay") -> dict:
    """Build a mock getpeerinfo entry."""
    return {
        "addr": addr,
        "network": network,
        "connection_type": conn_type,
        "id": 1,
        "inbound": False,
    }


def _addrman_entry(address: str, port: int, network: str = "ipv4", time: int = 100) -> dict:
    """Build a mock getnodeaddresses entry."""
    return {"address": address, "port": port, "network": network, "time": time, "services": 1033}


# ── Peer harvesting tests ──


@pytest.mark.asyncio
async def test_harvest_peers_skips_local():
    """Peers with 127.0.0.1 addresses are skipped."""
    nc = NodeConfig(1, "groundtruth", 48332, "u", "p")
    seen: set[NodeIdentity] = set()
    candidates: list[CandidateNode] = []

    with patch("txprobe.discovery.harvester.AsyncBitcoinRpc") as MockRpc:
        mock_rpc = AsyncMock()
        mock_rpc.getpeerinfo = AsyncMock(return_value=[
            _peer("127.0.0.1:48347"),
            _peer("5.6.7.8:48333"),
        ])
        MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_rpc)
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        added = await _harvest_peers_one(
            nc, _make_config(), CandidatePriority.GROUNDTRUTH_PEER,
            seen, candidates, skip_block_relay=False, connected_out=None,
        )

    assert added == 1
    assert candidates[0].identity.addr == "5.6.7.8:48333"


@pytest.mark.asyncio
async def test_harvest_peers_skips_feeler():
    """Feeler connections are skipped."""
    nc = NodeConfig(1, "groundtruth", 48332, "u", "p")
    seen: set[NodeIdentity] = set()
    candidates: list[CandidateNode] = []

    with patch("txprobe.discovery.harvester.AsyncBitcoinRpc") as MockRpc:
        mock_rpc = AsyncMock()
        mock_rpc.getpeerinfo = AsyncMock(return_value=[
            _peer("1.2.3.4:48333", conn_type="feeler"),
        ])
        MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_rpc)
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        added = await _harvest_peers_one(
            nc, _make_config(), CandidatePriority.GROUNDTRUTH_PEER,
            seen, candidates, skip_block_relay=False, connected_out=None,
        )

    assert added == 0
    assert len(candidates) == 0


@pytest.mark.asyncio
async def test_harvest_groundtruth_includes_block_relay():
    """Groundtruth nodes include block-relay-only peers."""
    nc = NodeConfig(1, "groundtruth", 48332, "u", "p")
    seen: set[NodeIdentity] = set()
    candidates: list[CandidateNode] = []

    with patch("txprobe.discovery.harvester.AsyncBitcoinRpc") as MockRpc:
        mock_rpc = AsyncMock()
        mock_rpc.getpeerinfo = AsyncMock(return_value=[
            _peer("1.2.3.4:48333", conn_type="block-relay-only"),
        ])
        MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_rpc)
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        added = await _harvest_peers_one(
            nc, _make_config(), CandidatePriority.GROUNDTRUTH_PEER,
            seen, candidates, skip_block_relay=False, connected_out=None,
        )

    assert added == 1


@pytest.mark.asyncio
async def test_harvest_probe_skips_block_relay():
    """Probe nodes skip block-relay-only peers."""
    nc = NodeConfig(0, "probe", 48347, "u", "p")
    seen: set[NodeIdentity] = set()
    candidates: list[CandidateNode] = []

    with patch("txprobe.discovery.harvester.AsyncBitcoinRpc") as MockRpc:
        mock_rpc = AsyncMock()
        mock_rpc.getpeerinfo = AsyncMock(return_value=[
            _peer("1.2.3.4:48333", conn_type="block-relay-only"),
            _peer("5.6.7.8:48333", conn_type="outbound-full-relay"),
        ])
        MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_rpc)
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        added = await _harvest_peers_one(
            nc, _make_config(), CandidatePriority.PROBE_PEER,
            seen, candidates, skip_block_relay=True, connected_out=None,
        )

    assert added == 1
    assert candidates[0].identity.addr == "5.6.7.8:48333"


@pytest.mark.asyncio
async def test_harvest_deduplication():
    """Same address from two nodes should only appear once."""
    nc1 = NodeConfig(1, "groundtruth", 48332, "u1", "p1")
    nc2 = NodeConfig(2, "groundtruth", 48335, "u2", "p2")
    seen: set[NodeIdentity] = set()
    candidates: list[CandidateNode] = []

    async def mock_peers(*args, **kwargs):
        return [_peer("1.2.3.4:48333")]

    with patch("txprobe.discovery.harvester.AsyncBitcoinRpc") as MockRpc:
        mock_rpc = AsyncMock()
        mock_rpc.getpeerinfo = mock_peers
        MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_rpc)
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        await _harvest_peers_one(
            nc1, _make_config(), CandidatePriority.GROUNDTRUTH_PEER,
            seen, candidates, False, None,
        )
        await _harvest_peers_one(
            nc2, _make_config(), CandidatePriority.GROUNDTRUTH_PEER,
            seen, candidates, False, None,
        )

    assert len(candidates) == 1
    assert candidates[0].source_node_id == 1  # first node wins


@pytest.mark.asyncio
async def test_harvest_addrman_normalizes_ipv6():
    """getnodeaddresses IPv6 should be normalized with brackets."""
    nc = NodeConfig(0, "probe", 48347, "u", "p")
    seen: set[NodeIdentity] = set()
    candidates: list[CandidateNode] = []

    with patch("txprobe.discovery.harvester.AsyncBitcoinRpc") as MockRpc:
        mock_rpc = AsyncMock()
        mock_rpc.getnodeaddresses = AsyncMock(return_value=[
            _addrman_entry("2001:db8::1", 48333, network="ipv6"),
        ])
        MockRpc.return_value.__aenter__ = AsyncMock(return_value=mock_rpc)
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        added = await _harvest_addrman_one(nc, seen, candidates)

    assert added == 1
    assert candidates[0].identity.addr == "[2001:db8::1]:48333"


@pytest.mark.asyncio
async def test_harvest_node_offline_graceful():
    """If a node's RPC fails, skip it and continue."""
    nc = NodeConfig(99, "groundtruth", 99999, "u", "p")
    seen: set[NodeIdentity] = set()
    candidates: list[CandidateNode] = []

    with patch("txprobe.discovery.harvester.AsyncBitcoinRpc") as MockRpc:
        MockRpc.return_value.__aenter__ = AsyncMock(
            side_effect=ConnectionRefusedError("Node offline")
        )
        MockRpc.return_value.__aexit__ = AsyncMock(return_value=False)

        added = await _harvest_peers_one(
            nc, _make_config(), CandidatePriority.GROUNDTRUTH_PEER,
            seen, candidates, False, None,
        )

    assert added == 0
    assert len(candidates) == 0


@pytest.mark.asyncio
async def test_priority_ordering():
    """Candidates from different sources should maintain priority order."""
    # Simulate: groundtruth gives A, probe gives B, addrman gives C
    gt_peer = CandidateNode(
        NodeIdentity("1.0.0.1:48333"), CandidatePriority.GROUNDTRUTH_PEER, "ipv4", 1, 0,
    )
    probe_peer = CandidateNode(
        NodeIdentity("2.0.0.1:48333"), CandidatePriority.PROBE_PEER, "ipv4", 0, 0,
    )
    dns_peer = CandidateNode(
        NodeIdentity("3.0.0.1:48333"), CandidatePriority.DNS_SEED, "ipv4", -1, 0,
    )
    addrman_peer = CandidateNode(
        NodeIdentity("4.0.0.1:48333"), CandidatePriority.ADDRMAN, "ipv4", 0, 100,
    )

    # Shuffle and sort
    candidates = [addrman_peer, probe_peer, dns_peer, gt_peer]
    candidates.sort(key=lambda c: c.priority)

    assert candidates[0].priority == CandidatePriority.GROUNDTRUTH_PEER
    assert candidates[1].priority == CandidatePriority.PROBE_PEER
    assert candidates[2].priority == CandidatePriority.DNS_SEED
    assert candidates[3].priority == CandidatePriority.ADDRMAN
