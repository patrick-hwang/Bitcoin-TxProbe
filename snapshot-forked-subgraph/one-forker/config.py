"""Configuration and Environment Specification for Fork Propagation Experiment.

Defines network ports, node configurations, paths, and graph topology loaders
for the 1,000-node RegTest network with Node 2 as the forker and Nodes 0 & 1 as probers.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("snapshot_fork.config")

# Base filesystem paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REGTEST_DIR = Path("/mnt/ssd/hdhphat-mindfullab/regtest-node-data")
DEFAULT_TOPOLOGY_PATH = DEFAULT_REGTEST_DIR / "groundtruth_topology.json"
DEFAULT_INFERRED_TOPOLOGY_PATH = PROJECT_ROOT / "results-regtest" / "run_2026-10-12_22-12-42" / "full_inferred_topology.json"
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Default network configuration
BASE_P2P_PORT = 10000
BASE_RPC_PORT = 20000

PROBE_NODE_IDS = (0, 1)
FORKER_NODE_ID = 2
NUM_TARGET_NODES = 1000  # Nodes 2 .. 1001
TOTAL_NODES = NUM_TARGET_NODES + 2  # Nodes 0 .. 1001


@dataclass(frozen=True)
class NodeConfig:
    """Configuration metadata for an individual RegTest bitcoind node."""
    node_id: int
    role: str  # "probe" | "forker" | "target"
    p2p_port: int
    rpc_port: int
    rpc_user: str
    rpc_pass: str
    datadir: Path

    @property
    def rpc_url(self) -> str:
        return f"http://127.0.0.1:{self.rpc_port}"


DEFAULT_FUNDING_TARGET_SATS = 100_000  # 0.001 BTC


@dataclass
class ExperimentConfig:
    """High-level configuration for the fork experiment."""
    forker_id: int = FORKER_NODE_ID
    probe_ids: list[int] = field(default_factory=lambda: list(PROBE_NODE_IDS))
    num_target_nodes: int = NUM_TARGET_NODES
    base_dir: Path = DEFAULT_REGTEST_DIR
    topology_path: Path = DEFAULT_TOPOLOGY_PATH
    results_dir: Path = DEFAULT_RESULTS_DIR
    funding_target_sats: int = DEFAULT_FUNDING_TARGET_SATS  # Configurable (default: 100,000 sats / 0.001 BTC)
    dust_amount_sats: int = 10_000
    fee_sats: int = 1_000
    propagation_timeout_sec: float = 10.0
    snapshot_interval_ms: float = 10.0

    def __post_init__(self) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)


def get_ports(node_id: int, base_p2p: int = BASE_P2P_PORT, base_rpc: int = BASE_RPC_PORT) -> tuple[int, int]:
    """Return (p2p_port, rpc_port) for a given node ID."""
    return base_p2p + node_id, base_rpc + node_id


def parse_node_id(node_val: Any, base_p2p: int = BASE_P2P_PORT) -> int:
    """Parse node ID from int, string int, or IP:Port format (e.g. '127.0.0.1:10002' -> 2)."""
    s = str(node_val).strip()
    for prefix in ("bitcoin-", "bitcoin_", "node-", "node_"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
    if ":" in s:
        s = s.split(":")[-1]
    nid = int(s)
    if nid >= base_p2p:
        return nid - base_p2p
    return nid


def get_node_config(node_id: int, base_dir: Path = DEFAULT_REGTEST_DIR) -> NodeConfig:
    """Build NodeConfig dataclass for a specific node ID."""
    p2p, rpc = get_ports(node_id)
    if node_id in PROBE_NODE_IDS:
        role = "probe"
    elif node_id == FORKER_NODE_ID:
        role = "forker"
    else:
        role = "target"

    return NodeConfig(
        node_id=node_id,
        role=role,
        p2p_port=p2p,
        rpc_port=rpc,
        rpc_user=f"regtestuser{node_id}",
        rpc_pass=f"regtestpassword{node_id}",
        datadir=base_dir / f"bitcoin-{node_id}",
    )


def load_all_nodes(total_nodes: int = TOTAL_NODES, base_dir: Path = DEFAULT_REGTEST_DIR) -> dict[int, NodeConfig]:
    """Return dictionary of NodeConfig for all nodes in the network."""
    return {nid: get_node_config(nid, base_dir=base_dir) for nid in range(total_nodes)}


def load_topology(
    topology_path: Path = DEFAULT_TOPOLOGY_PATH,
    symmetrize: bool = True,
) -> dict[int, list[int]]:
    """Load network topology adjacency list from JSON (supports Groundtruth and TxProbe Inferred formats).

    Supported formats:
    - Ground Truth topology: {"adjacency": {"2": [213, 268, ...]}}
    - TxProbe Inferred topology: {"adj_list": {"127.0.0.1:10002": ["127.0.0.1:10213", ...]}}
    - Reconciled topology: {"full_inferred_topology": {"adj_list": ...}} or {"evaluation_inferred_topology": {"adj_list": ...}}

    Args:
        topology_path: Path to topology JSON file.
        symmetrize: If True, ensures all edges are bidirectional (u in adj[v] <=> v in adj[u]),
            reflecting the bidirectional physical reality of Bitcoin P2P connections.

    Returns:
        dict[int, list[int]]: mapping of node_id -> list of neighbor node_ids.
    """
    if not topology_path.exists():
        raise FileNotFoundError(f"Topology file not found at: {topology_path}")

    with open(topology_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_adj = (
        data.get("adjacency")
        or data.get("adj_list")
        or data.get("full_inferred_topology", {}).get("adj_list")
        or data.get("evaluation_inferred_topology", {}).get("adj_list")
        or data.get("reconciled_groundtruth", {}).get("adj_list")
        or {}
    )

    adj: dict[int, list[int]] = {}
    for node_str, neighbors in raw_adj.items():
        u = parse_node_id(node_str)
        adj[u] = [parse_node_id(n) for n in neighbors]

    if symmetrize:
        sym_adj: dict[int, set[int]] = {u: set(nbrs) for u, nbrs in adj.items()}
        for u, nbrs in adj.items():
            for v in nbrs:
                if v not in sym_adj:
                    sym_adj[v] = set()
                sym_adj[v].add(u)
        adj = {u: sorted(list(nbrs)) for u, nbrs in sorted(sym_adj.items())}

    return adj


def compute_bfs_distances(adj: dict[int, list[int]], source: int) -> dict[int, int]:
    """Compute shortest hop distance from source node to all reachable nodes using BFS.

    Returns:
        dict[int, int]: mapping of node_id -> hop distance from source.
    """
    if source not in adj:
        raise ValueError(f"Source node {source} not present in graph adjacency list.")

    distances: dict[int, int] = {source: 0}
    queue: deque[int] = deque([source])

    while queue:
        current = queue.popleft()
        current_dist = distances[current]
        for neighbor in adj.get(current, []):
            if neighbor not in distances:
                distances[neighbor] = current_dist + 1
                queue.append(neighbor)

    return distances


async def check_network_peered(probe_id: int = 0, timeout_sec: float = 2.0) -> bool:
    """Check if the given probe node currently has active peers."""
    from txprobe.rpc.client import AsyncBitcoinRpc
    cfg = get_node_config(probe_id)
    try:
        async with AsyncBitcoinRpc("127.0.0.1", cfg.rpc_port, cfg.rpc_user, cfg.rpc_pass, timeout_sec=timeout_sec) as rpc:
            peers = await rpc.call("getpeerinfo")
            return len(peers) > 0
    except Exception:
        return False


async def connect_network_topology(
    topology_path: Path = DEFAULT_TOPOLOGY_PATH,
    probe_ids: tuple[int, ...] = PROBE_NODE_IDS,
) -> None:
    """Connect all target nodes according to topology_path and peer Probes 0 & 1 to all targets."""
    import asyncio
    from txprobe.rpc.client import AsyncBitcoinRpc

    adj = load_topology(topology_path)
    target_ids = list(adj.keys())

    # 1. Connect inter-target node edges
    log.info("Dispatching addnode for %d target nodes across %d edges...", len(target_ids), sum(len(v) for v in adj.values()) // 2)

    async def _connect_one(u: int, neighbors: list[int]) -> None:
        cfg_u = get_node_config(u)
        try:
            async with AsyncBitcoinRpc("127.0.0.1", cfg_u.rpc_port, cfg_u.rpc_user, cfg_u.rpc_pass, timeout_sec=5.0) as client:
                for v in neighbors:
                    p2p_v, _ = get_ports(v)
                    try:
                        await client.call("addnode", f"127.0.0.1:{p2p_v}", "add")
                    except Exception:
                        pass
        except Exception:
            pass

    await asyncio.gather(*[_connect_one(u, neighbors) for u, neighbors in adj.items()])

    # 2. Connect Probes 0 and 1 to all target nodes
    log.info("Connecting Probes %s to all %d target nodes...", probe_ids, len(target_ids))

    async def _connect_probe(p: int) -> None:
        cfg_p = get_node_config(p)
        try:
            async with AsyncBitcoinRpc("127.0.0.1", cfg_p.rpc_port, cfg_p.rpc_user, cfg_p.rpc_pass, timeout_sec=10.0) as probe_rpc:
                for t in target_ids:
                    p2p_t, _ = get_ports(t)
                    try:
                        await probe_rpc.call("addnode", f"127.0.0.1:{p2p_t}", "add")
                    except Exception:
                        pass
        except Exception:
            pass

    await asyncio.gather(*[_connect_probe(p) for p in probe_ids])


async def wait_for_topology_ready(
    min_probe_peers: int = 50,
    timeout_sec: float = 30.0,
) -> None:
    """Wait until Probe 0 has established active peer connections."""
    import asyncio
    import time
    from txprobe.rpc.client import AsyncBitcoinRpc

    cfg = get_node_config(0)
    t0 = time.monotonic()
    while (time.monotonic() - t0) < timeout_sec:
        try:
            async with AsyncBitcoinRpc("127.0.0.1", cfg.rpc_port, cfg.rpc_user, cfg.rpc_pass, timeout_sec=2.0) as rpc:
                peers = await rpc.call("getpeerinfo")
                if len(peers) >= min_probe_peers:
                    log.info("Probe 0 connected to %d peers. Network topology ready!", len(peers))
                    return
        except Exception:
            pass
        await asyncio.sleep(1.0)
    log.warning("Proceeding after topology connection timeout (Probe 0 peers may still be handshaking).")
