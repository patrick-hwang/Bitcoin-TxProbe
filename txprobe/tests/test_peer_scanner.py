"""Tests for Phase 2 peer scanner and selection."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from txprobe.config import Config, DiscoveryConfig, NodeConfig, ReachabilityConfig
from txprobe.discovery.harvester import HarvestResult, HarvestStats
from txprobe.discovery.peer_scanner import (
    ScanResult,
    ScanStats,
    _disconnect_excess_peers,
    _extract_valid_probe_peers,
    _split_clearnet_and_tor,
    scan_and_select_peers,
)
from txprobe.models.node import CandidateNode, CandidatePriority, NodeIdentity


def _make_config(**overrides) -> Config:
    """Build a minimal Config with Probe 0 and Probe 1 for tests."""
    defaults = dict(
        network="testnet4",
        default_port=48333,
        nodes=[
            NodeConfig(0, "probe", 48347, "u0", "p0"),
            NodeConfig(1, "probe", 48332, "u1", "p1"),
            NodeConfig(2, "groundtruth", 48335, "u2", "p2"),
        ],
        discovery=DiscoveryConfig(
            target_count=3,
            crawling_time_sec=5.0,
            poll_interval_sec=0.05,
            clearnet_onetry_concurrency=4,
            tor_onetry_concurrency=2,
        ),
        reachability=ReachabilityConfig(),
        dns_seeds=[],
    )
    defaults.update(overrides)
    return Config(**defaults)


def _cand(
    addr: str,
    priority: CandidatePriority = CandidatePriority.GROUNDTRUTH_PEER,
    network: str = "ipv4",
    source_id: int = 2,
) -> CandidateNode:
    return CandidateNode(
        identity=NodeIdentity(addr=addr),
        priority=priority,
        network=network,
        source_node_id=source_id,
        last_seen=0,
    )


def _peer(
    addr: str,
    conn_type: str = "manual",
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


# ── Unit tests for internal helpers ──


def test_split_clearnet_and_tor_separates_and_skips_already_connected():
    """_split_clearnet_and_tor separates clearnet and onion queues while skipping already connected."""
    c_onion_p0 = _cand("gt2.onion:48333", CandidatePriority.GROUNDTRUTH_PEER, "onion")
    c_ipv4_p0 = _cand("1.1.1.1:48333", CandidatePriority.GROUNDTRUTH_PEER, "ipv4")
    c_ipv4_p2 = _cand("2.2.2.2:48333", CandidatePriority.DNS_SEED, "ipv4")

    clearnet, tor = _split_clearnet_and_tor(
        [c_onion_p0, c_ipv4_p0, c_ipv4_p2],
        already_connected={NodeIdentity("1.1.1.1:48333")},
    )

    assert clearnet == ["2.2.2.2:48333"]
    assert tor == ["gt2.onion:48333"]


def test_extract_valid_probe_peers_filters_invalid_types():
    """_extract_valid_probe_peers filters localhost, feeler, addr-fetch, block-relay-only, and version<=0."""
    raw = [
        _peer("127.0.0.1:48332", conn_type="manual", version=70016),
        _peer("1.0.0.1:48333", conn_type="feeler", version=70016),
        _peer("1.0.0.2:48333", conn_type="addr-fetch", version=70016),
        _peer("1.0.0.3:48333", conn_type="block-relay-only", version=70016),
        _peer("1.0.0.4:48333", conn_type="manual", version=0),  # unhandshaked
        _peer("1.0.0.5:48333", conn_type="manual", version=70016),
        _peer("1.0.0.6:48333", conn_type="outbound-full-relay", version=70016),
    ]

    valid = _extract_valid_probe_peers(raw)
    assert valid == {
        NodeIdentity("1.0.0.5:48333"),
        NodeIdentity("1.0.0.6:48333"),
    }


@pytest.mark.asyncio
async def test_disconnect_excess_peers_batches_only_non_selected():
    """_disconnect_excess_peers only disconnects peers not in selected_identities."""
    mock_rpc = AsyncMock()
    mock_rpc.call_batch = AsyncMock(return_value=[None, None])

    selected = {NodeIdentity("1.1.1.1:48333"), NodeIdentity("2.2.2.2:48333")}
    current = {
        NodeIdentity("1.1.1.1:48333"),
        NodeIdentity("3.3.3.3:48333"),
        NodeIdentity("4.4.4.4:48333"),
    }

    disconnected = await _disconnect_excess_peers(
        mock_rpc, selected, current, chunk_size=1,
    )

    assert disconnected == 2
    assert mock_rpc.call_batch.call_count == 2
    mock_rpc.call_batch.assert_any_call(
        [("disconnectnode", "3.3.3.3:48333")], raise_on_error=False
    )
    mock_rpc.call_batch.assert_any_call(
        [("disconnectnode", "4.4.4.4:48333")], raise_on_error=False
    )


# ── End-to-end Phase 2 orchestration tests ──


@pytest.mark.asyncio
async def test_scan_requires_two_probes():
    """scan_and_select_peers raises ValueError if fewer than 2 probe nodes are configured."""
    cfg = _make_config(nodes=[NodeConfig(0, "probe", 48347, "u0", "p0")])
    harvest = HarvestResult(candidates=[])

    with pytest.raises(ValueError, match="At least 2 probe nodes"):
        await scan_and_select_peers(cfg, harvest)


@pytest.mark.asyncio
async def test_scan_early_exit_and_priority_preservation():
    """scan_and_select_peers exits early at target_count, preserves priority, and disconnects excess."""
    c_p3 = _cand("4.0.0.1:48333", CandidatePriority.ADDRMAN)
    c_p0 = _cand("gt2.onion:48333", CandidatePriority.GROUNDTRUTH_PEER, "onion")
    c_p1 = _cand("2.0.0.1:48333", CandidatePriority.PROBE_PEER)
    c_p2 = _cand("3.0.0.1:48333", CandidatePriority.DNS_SEED)

    harvest = HarvestResult(
        candidates=[c_p3, c_p0, c_p1, c_p2],
        already_connected_probes={
            0: {NodeIdentity("gt2.onion:48333")},  # already connected on Probe 0
            1: set(),
        },
        stats=HarvestStats(total_unique=4),
    )

    cfg = _make_config(
        discovery=DiscoveryConfig(
            target_count=3,
            crawling_time_sec=10.0,
            poll_interval_sec=0.02,
            clearnet_onetry_concurrency=4,
            tor_onetry_concurrency=2,
        )
    )

    rpc_0 = AsyncMock()
    rpc_1 = AsyncMock()

    # Both probes connect to all 4 candidates + 1 non-candidate excess peer
    rpc_0.getpeerinfo = AsyncMock(return_value=[
        _peer("gt2.onion:48333", network="onion"),
        _peer("2.0.0.1:48333"),
        _peer("3.0.0.1:48333"),
        _peer("4.0.0.1:48333"),
        _peer("9.9.9.9:48333"),
    ])
    rpc_1.getpeerinfo = AsyncMock(return_value=[
        _peer("gt2.onion:48333", network="onion"),
        _peer("2.0.0.1:48333"),
        _peer("3.0.0.1:48333"),
        _peer("4.0.0.1:48333"),
    ])

    def _rpc_factory(host, port, user, password, wallet=""):
        ctx = AsyncMock()
        client = rpc_0 if port == 48347 else rpc_1
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    with patch("txprobe.discovery.peer_scanner.AsyncBitcoinRpc", side_effect=_rpc_factory):
        result = await scan_and_select_peers(cfg, harvest)

    assert result.probe_ids == (0, 1)
    assert result.stats.early_exit is True
    assert result.stats.mutual_connected == 4
    assert result.stats.selected_count == 3

    # Selected nodes MUST be top 3 by priority (P0, P1, P2), dropping P3 (4.0.0.1)
    assert [n.identity.addr for n in result.selected_nodes] == [
        "gt2.onion:48333",
        "2.0.0.1:48333",
        "3.0.0.1:48333",
    ]

    # Probe 0 had 5 peers (3 selected + 4.0.0.1 + 9.9.9.9) → 2 excess disconnected
    assert result.stats.excess_disconnected_probes[0] == 2
    # Probe 1 had 4 peers (3 selected + 4.0.0.1) → 1 excess disconnected
    assert result.stats.excess_disconnected_probes[1] == 1

    # Verify Probe 0 did NOT send onetry to gt2.onion:48333 since it was in already_connected_probes[0]
    onetry_addrs_p0 = [call.args[0] for call in rpc_0.addnode.call_args_list]
    assert "gt2.onion:48333" not in onetry_addrs_p0


@pytest.mark.asyncio
async def test_scan_graceful_when_below_target():
    """When fewer than target_count peers connect, returns all available mutual peers without error."""
    c1 = _cand("1.0.0.1:48333", CandidatePriority.GROUNDTRUTH_PEER)
    c2 = _cand("2.0.0.1:48333", CandidatePriority.DNS_SEED)

    harvest = HarvestResult(
        candidates=[c1, c2],
        already_connected_probes={0: set(), 1: set()},
    )

    cfg = _make_config(
        discovery=DiscoveryConfig(
            target_count=10,
            crawling_time_sec=0.2,
            poll_interval_sec=0.05,
            clearnet_onetry_concurrency=2,
            tor_onetry_concurrency=2,
        )
    )

    rpc_0 = AsyncMock()
    rpc_1 = AsyncMock()
    # Only 1.0.0.1 is mutually connected
    rpc_0.getpeerinfo = AsyncMock(return_value=[_peer("1.0.0.1:48333"), _peer("2.0.0.1:48333")])
    rpc_1.getpeerinfo = AsyncMock(return_value=[_peer("1.0.0.1:48333")])

    def _rpc_factory(host, port, user, password, wallet=""):
        ctx = AsyncMock()
        client = rpc_0 if port == 48347 else rpc_1
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    with patch("txprobe.discovery.peer_scanner.AsyncBitcoinRpc", side_effect=_rpc_factory):
        result = await scan_and_select_peers(cfg, harvest)

    assert result.stats.early_exit is False
    assert result.stats.mutual_connected == 1
    assert result.stats.selected_count == 1
    assert result.selected_identities() == [NodeIdentity("1.0.0.1:48333")]
    # Probe 0 disconnects 2.0.0.1:48333 (not mutually connected)
    assert result.stats.excess_disconnected_probes[0] == 1
    assert result.stats.excess_disconnected_probes[1] == 0


def test_scan_result_save_and_load(tmp_path):
    """ScanResult.save() and ScanResult.load() should preserve all fields."""
    original = ScanResult(
        selected_nodes=[
            _cand("1.2.3.4:48333", CandidatePriority.GROUNDTRUTH_PEER, "ipv4", 2),
            _cand("xyz.onion:48333", CandidatePriority.DNS_SEED, "onion", -1),
        ],
        probe_ids=(0, 1),
        stats=ScanStats(
            candidates_input=50,
            onetry_sent_probes={0: 45, 1: 48},
            connected_probes={0: 30, 1: 28},
            mutual_connected=25,
            selected_count=2,
            excess_disconnected_probes={0: 28, 1: 26},
            early_exit=True,
            polls_count=3,
            elapsed_sec=21.5,
            timestamp="2026-09-29T00:30:00Z",
        ),
    )

    out_file = tmp_path / "discovered_nodes.json"
    original.save(out_file)
    loaded = ScanResult.load(out_file)

    assert loaded.probe_ids == (0, 1)
    assert len(loaded.selected_nodes) == 2
    assert loaded.selected_identities() == [
        NodeIdentity("1.2.3.4:48333"),
        NodeIdentity("xyz.onion:48333"),
    ]
    assert loaded.stats.candidates_input == 50
    assert loaded.stats.onetry_sent_probes == {0: 45, 1: 48}
    assert loaded.stats.connected_probes == {0: 30, 1: 28}
    assert loaded.stats.excess_disconnected_probes == {0: 28, 1: 26}
    assert loaded.stats.early_exit is True
    assert loaded.stats.polls_count == 3
    assert loaded.stats.elapsed_sec == 21.5


@pytest.mark.asyncio
async def test_disconnect_excess_peers_preserves_block_relay_only():
    """_disconnect_excess_peers must NEVER disconnect block-relay-only nodes."""
    mock_rpc = AsyncMock()
    mock_rpc.call_batch = AsyncMock(return_value=[None])
    # 2.2.2.2 is block-relay-only, 3.3.3.3 is regular excess
    mock_rpc.getpeerinfo = AsyncMock(return_value=[
        {"addr": "2.2.2.2:48333", "connection_type": "block-relay-only"},
        {"addr": "3.3.3.3:48333", "connection_type": "inbound"},
    ])

    selected = {NodeIdentity("1.1.1.1:48333")}
    current = {
        NodeIdentity("1.1.1.1:48333"),
        NodeIdentity("2.2.2.2:48333"),
        NodeIdentity("3.3.3.3:48333"),
    }

    disconnected = await _disconnect_excess_peers(
        mock_rpc, selected, current, chunk_size=10,
    )

    # Only 3.3.3.3:48333 should be disconnected. 2.2.2.2:48333 must be preserved!
    assert disconnected == 1
    assert mock_rpc.call_batch.call_count == 1
    mock_rpc.call_batch.assert_called_once_with(
        [("disconnectnode", "3.3.3.3:48333")], raise_on_error=False,
    )


@pytest.mark.asyncio
async def test_scan_targets_all_candidates_when_target_count_is_zero():
    """When target_count=0, scan_and_select_peers targets all candidates in harvest."""
    c1 = _cand("1.0.0.1:48333", CandidatePriority.GROUNDTRUTH_PEER)
    c2 = _cand("2.0.0.1:48333", CandidatePriority.DNS_SEED)
    c3 = _cand("3.0.0.1:48333", CandidatePriority.ADDRMAN)

    harvest = HarvestResult(
        candidates=[c1, c2, c3],
        already_connected_probes={0: set(), 1: set()},
    )

    cfg = _make_config(
        discovery=DiscoveryConfig(
            target_count=0,  # 0 means connect to all candidates
            crawling_time_sec=10.0,
            poll_interval_sec=0.02,
        )
    )

    rpc_0 = AsyncMock()
    rpc_1 = AsyncMock()
    rpc_0.getpeerinfo = AsyncMock(return_value=[
        _peer("1.0.0.1:48333"), _peer("2.0.0.1:48333"), _peer("3.0.0.1:48333"),
    ])
    rpc_1.getpeerinfo = AsyncMock(return_value=[
        _peer("1.0.0.1:48333"), _peer("2.0.0.1:48333"), _peer("3.0.0.1:48333"),
    ])

    def _rpc_factory(host, port, user, password, wallet=""):
        ctx = AsyncMock()
        client = rpc_0 if port == 48347 else rpc_1
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    with patch("txprobe.discovery.peer_scanner.AsyncBitcoinRpc", side_effect=_rpc_factory):
        result = await scan_and_select_peers(cfg, harvest)

    assert result.stats.early_exit is True
    assert result.stats.mutual_connected == 3
    assert result.stats.selected_count == 3
    assert len(result.selected_nodes) == 3


@pytest.mark.asyncio
async def test_scan_retries_unconnected_candidates():
    """scan_and_select_peers re-dispatches onetry for missing candidates at retry_interval."""
    c1 = _cand("1.0.0.1:48333", CandidatePriority.GROUNDTRUTH_PEER)
    c2 = _cand("2.0.0.1:48333", CandidatePriority.DNS_SEED)

    harvest = HarvestResult(
        candidates=[c1, c2],
        already_connected_probes={0: set(), 1: set()},
    )

    cfg = _make_config(
        discovery=DiscoveryConfig(
            target_count=0,
            crawling_time_sec=0.3,
            poll_interval_sec=0.02,
            retry_interval_sec=0.04,
        )
    )

    rpc_0 = AsyncMock()
    rpc_1 = AsyncMock()
    rpc_0.addnode = AsyncMock(return_value=None)
    rpc_1.addnode = AsyncMock(return_value=None)

    # Initial state: only 1.0.0.1 is connected
    rpc_0.getpeerinfo = AsyncMock(return_value=[_peer("1.0.0.1:48333")])
    rpc_1.getpeerinfo = AsyncMock(return_value=[_peer("1.0.0.1:48333")])

    def _rpc_factory(host, port, user, password, wallet=""):
        ctx = AsyncMock()
        client = rpc_0 if port == 48347 else rpc_1
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    with patch("txprobe.discovery.peer_scanner.AsyncBitcoinRpc", side_effect=_rpc_factory):
        result = await scan_and_select_peers(cfg, harvest)

    # Candidate 2.0.0.1 should have received initial onetry + retry onetry
    addnode_0_calls = [call.args[0] for call in rpc_0.addnode.call_args_list]
    assert addnode_0_calls.count("2.0.0.1:48333") >= 2
