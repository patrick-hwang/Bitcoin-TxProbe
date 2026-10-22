"""Unit tests for snapshot-forked-subgraph configuration and topology loader."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root and module to path
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

import pytest
from config import (
    DEFAULT_TOPOLOGY_PATH,
    FORKER_NODE_ID,
    NUM_TARGET_NODES,
    PROBE_NODE_IDS,
    TOTAL_NODES,
    ExperimentConfig,
    compute_bfs_distances,
    get_node_config,
    get_ports,
    load_all_nodes,
    load_topology,
)


def test_ports_generation() -> None:
    """Verify deterministic port mapping across network nodes."""
    p2p_0, rpc_0 = get_ports(0)
    assert p2p_0 == 10000
    assert rpc_0 == 20000

    p2p_2, rpc_2 = get_ports(2)
    assert p2p_2 == 10002
    assert rpc_2 == 20002

    p2p_1001, rpc_1001 = get_ports(1001)
    assert p2p_1001 == 11001
    assert rpc_1001 == 21001


def test_node_roles_and_credentials() -> None:
    """Verify role assignment and credential consistency."""
    node_0 = get_node_config(0)
    assert node_0.role == "probe"
    assert node_0.rpc_user == "regtestuser0"
    assert node_0.rpc_pass == "regtestpassword0"

    node_1 = get_node_config(1)
    assert node_1.role == "probe"

    node_2 = get_node_config(2)
    assert node_2.role == "forker"

    node_3 = get_node_config(3)
    assert node_3.role == "target"

    node_1001 = get_node_config(1001)
    assert node_1001.role == "target"


def test_load_all_nodes() -> None:
    """Verify loading full 1002-node configuration map."""
    all_nodes = load_all_nodes()
    assert len(all_nodes) == TOTAL_NODES
    assert 0 in all_nodes
    assert FORKER_NODE_ID in all_nodes
    assert 1001 in all_nodes


def test_load_topology_graph() -> None:
    """Verify topology loading, reciprocity, and graph metrics."""
    assert DEFAULT_TOPOLOGY_PATH.exists(), f"Missing groundtruth topology at {DEFAULT_TOPOLOGY_PATH}"
    adj = load_topology(DEFAULT_TOPOLOGY_PATH)

    assert len(adj) == NUM_TARGET_NODES
    assert all(nid in adj for nid in range(2, 2 + NUM_TARGET_NODES))

    # Test edge symmetry (undirected graph)
    edge_count = 0
    for u, neighbors in adj.items():
        edge_count += len(neighbors)
        for v in neighbors:
            assert u in adj[v], f"Asymmetric edge found: {u} -> {v} but not {v} -> {u}"

    total_undirected_edges = edge_count // 2
    assert total_undirected_edges == 4005, f"Expected 4005 edges, got {total_undirected_edges}"


def test_bfs_distances_from_forker() -> None:
    """Verify all 1000 target nodes are reachable from Forker (Node 2) and diameter is bounded."""
    adj = load_topology(DEFAULT_TOPOLOGY_PATH)
    distances = compute_bfs_distances(adj, FORKER_NODE_ID)

    # 1. Full connectivity: all 1000 target nodes must be reached
    assert len(distances) == NUM_TARGET_NODES
    assert distances[FORKER_NODE_ID] == 0

    # 2. Diameter from Forker must be <= 6 hops (typical random graph diameter is 4-5)
    max_hop = max(distances.values())
    assert 3 <= max_hop <= 6, f"Unexpected max hop distance from Forker: {max_hop}"

    # 3. Direct neighbors of Node 2 must have distance 1
    for neighbor in adj[FORKER_NODE_ID]:
        assert distances[neighbor] == 1

    # Print hop distribution summary for documentation
    hop_counts: dict[int, int] = {}
    for d in distances.values():
        hop_counts[d] = hop_counts.get(d, 0) + 1

    print("\nHop distance distribution from Forker (Node 2):")
    for hop in sorted(hop_counts.keys()):
        print(f"  Hop {hop}: {hop_counts[hop]} nodes")


def test_experiment_config_initialization() -> None:
    """Verify ExperimentConfig initializes correctly and creates results directory."""
    cfg = ExperimentConfig()
    assert cfg.forker_id == 2
    assert cfg.probe_ids == [0, 1]
    assert cfg.funding_target_sats == 100_000  # Default 0.001 BTC
    assert cfg.results_dir.exists()

    custom_cfg = ExperimentConfig(funding_target_sats=50_000)
    assert custom_cfg.funding_target_sats == 50_000


def test_parse_node_id() -> None:
    """Verify parse_node_id correctly converts various ID formats."""
    from config import parse_node_id

    assert parse_node_id(2) == 2
    assert parse_node_id("2") == 2
    assert parse_node_id("127.0.0.1:10002") == 2
    assert parse_node_id("127.0.0.1:10500") == 500
    assert parse_node_id("10002") == 2
    assert parse_node_id(10002) == 2


def test_load_inferred_topology() -> None:
    """Verify loading TxProbe full_inferred_topology.json format."""
    from config import DEFAULT_INFERRED_TOPOLOGY_PATH, load_topology

    if DEFAULT_INFERRED_TOPOLOGY_PATH.exists():
        adj = load_topology(DEFAULT_INFERRED_TOPOLOGY_PATH)
        assert len(adj) == 1000
        assert 2 in adj
        assert 1001 in adj
        # Check sample edges
        assert len(adj[2]) > 0
        assert all(isinstance(neighbor, int) for neighbor in adj[2])
