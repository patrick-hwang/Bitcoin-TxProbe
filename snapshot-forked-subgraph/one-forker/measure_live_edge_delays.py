#!/usr/bin/env python3
"""Multi-Source 30-Round Live Block Propagation & Minimum Edge Delay Measurer.

Measures empirical link propagation delays across 30 live rounds on the running
1,000-node RegTest network:
1. Dispatches blocks from 30 diverse/random source nodes across the live network.
2. High-precision concurrent polling monitors the exact arrival timestamp T_r(v)
   for all 1,000 live bitcoind nodes as the block propagates.
3. For every adjacent link (u, v) in the ground truth topology, calculates:
     Delta_r(u, v) = |T_r(u) - T_r(v)|
   Filters out sibling arrivals where Delta_r <= epsilon (default 0.05 ms).
4. Extracts empirical minimum edge delay across all 30 rounds:
     d(u, v) = min_{r, Delta_r > epsilon} Delta_r(u, v)
5. Exports full delay matrix and statistics to JSON.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import random
import resource
import statistics
import sys
import time
from typing import Any

# Increase file descriptor limit for concurrent HTTP RPC polling
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, 65535), hard))

import aiohttp

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_DIR = Path(__file__).resolve().parent

for p in (MODULE_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import (
    DEFAULT_RESULTS_DIR,
    DEFAULT_TOPOLOGY_PATH,
    get_node_config,
    load_topology,
)
from txprobe.rpc.client import AsyncBitcoinRpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("snapshot_fork.measure_live_delays")

DEFAULT_LIVE_DELAYS_OUT = DEFAULT_RESULTS_DIR / "edge_delays_live_30rounds.json"
DEFAULT_MINING_ADDRESS = "bcrt1qq25myyqyfvfaug3ramvssxpna0zvpayy09t99j"


def canonical_edge(u: int, v: int) -> tuple[int, int]:
    """Return canonical undirected edge tuple (min(u, v), max(u, v))."""
    return (u, v) if u < v else (v, u)


def canonical_edge_str(u: int, v: int) -> str:
    """Return canonical undirected edge string 'min_max'."""
    return f"{min(u, v)}_{max(u, v)}"


@dataclass(frozen=True)
class LiveRoundTelemetry:
    """Telemetry from one live block propagation round."""
    round_index: int
    source_node: int
    block_hash: str
    mining_duration_ms: float
    nodes_reached: int
    total_propagation_duration_ms: float
    observed_edges_count: int


async def run_single_live_round(
    round_index: int,
    source_node: int,
    all_target_nodes: list[int],
    all_edges: set[tuple[int, int]],
    session: aiohttp.ClientSession,
    auth_headers: dict[int, dict[str, str]],
    mining_address: str = DEFAULT_MINING_ADDRESS,
    epsilon_ms: float = 0.05,
    timeout_sec: float = 10.0,
) -> tuple[LiveRoundTelemetry, dict[str, float]]:
    """Execute one live round: mine block at source_node, track arrivals, compute edge deltas."""
    cfg_src = get_node_config(source_node)

    # 1. Determine current best tip before mining
    async with AsyncBitcoinRpc("127.0.0.1", cfg_src.rpc_port, cfg_src.rpc_user, cfg_src.rpc_pass, timeout_sec=3.0) as rpc:
        old_tip = await rpc.call("getbestblockhash")

    arrival_times: dict[int, float] = {}
    stop_event = asyncio.Event()

    # 2. Poller coroutine for each target node
    async def poll_single_node(nid: int) -> None:
        cfg = get_node_config(nid)
        headers = auth_headers[nid]
        payload = {"jsonrpc": "1.0", "id": nid, "method": "getbestblockhash", "params": []}

        while not stop_event.is_set():
            try:
                async with session.post(cfg.rpc_url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tip = data.get("result")
                        if tip and tip != old_tip:
                            arrival_times[nid] = time.time()
                            return
            except Exception:
                pass
            await asyncio.sleep(0.005)

    # Start concurrent monitoring across all target nodes
    poll_tasks = [asyncio.create_task(poll_single_node(nid)) for nid in all_target_nodes]
    await asyncio.sleep(0.02)  # Allow pollers to initialize connections

    # 3. Mine block on source node
    t_mine_start = time.time()
    async with AsyncBitcoinRpc("127.0.0.1", cfg_src.rpc_port, cfg_src.rpc_user, cfg_src.rpc_pass, timeout_sec=5.0) as rpc:
        block_hashes = await rpc.call("generatetoaddress", 1, mining_address)
    new_hash = block_hashes[0]
    t_mined = time.time()
    mining_dur_ms = (t_mined - t_mine_start) * 1000.0

    # Ensure source node has arrival timestamp at mine completion
    if source_node not in arrival_times:
        arrival_times[source_node] = t_mined

    # 4. Wait until all nodes receive the block or timeout
    deadline = time.time() + timeout_sec
    while len(arrival_times) < len(all_target_nodes) and time.time() < deadline:
        await asyncio.sleep(0.02)

    stop_event.set()
    await asyncio.gather(*poll_tasks, return_exceptions=True)

    total_dur_ms = (max(arrival_times.values()) - min(arrival_times.values())) * 1000.0 if arrival_times else 0.0

    # 5. Measure edge delays for all adjacent links (u, v) in the topology
    round_edge_delays: dict[str, float] = {}
    for u, v in all_edges:
        if u in arrival_times and v in arrival_times:
            delta_ms = abs(arrival_times[u] - arrival_times[v]) * 1000.0
            # Condition: Delta_r > epsilon to reject simultaneous sibling reception from a 3rd node w
            if delta_ms > epsilon_ms:
                edge_key = canonical_edge_str(u, v)
                round_edge_delays[edge_key] = delta_ms

    telemetry = LiveRoundTelemetry(
        round_index=round_index,
        source_node=source_node,
        block_hash=new_hash,
        mining_duration_ms=round(mining_dur_ms, 2),
        nodes_reached=len(arrival_times),
        total_propagation_duration_ms=round(total_dur_ms, 2),
        observed_edges_count=len(round_edge_delays),
    )

    log.info(
        "Round %2d/30 | Source Node %4d | Reached: %d/%d nodes in %.1f ms | Valid Edges: %d/%d",
        round_index,
        source_node,
        len(arrival_times),
        len(all_target_nodes),
        total_dur_ms,
        len(round_edge_delays),
        len(all_edges),
    )

    return telemetry, round_edge_delays


async def measure_live_edge_delays_async(
    num_rounds: int = 30,
    topology_path: Path = DEFAULT_TOPOLOGY_PATH,
    out_path: Path = DEFAULT_LIVE_DELAYS_OUT,
    mining_address: str = DEFAULT_MINING_ADDRESS,
    epsilon_ms: float = 0.05,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute live rounds on running 1,000-node network and compute empirical minimum link delays."""
    adj = load_topology(topology_path, symmetrize=True)
    all_target_nodes = sorted(adj.keys())
    total_nodes = len(all_target_nodes)

    all_edges: set[tuple[int, int]] = set()
    for u in all_target_nodes:
        for v in adj[u]:
            all_edges.add(canonical_edge(u, v))
    total_edges = len(all_edges)

    log.info("Initialized live delay measurement for %d nodes and %d undirected links.", total_nodes, total_edges)

    rng = random.Random(seed)
    # Select distinct diverse source nodes across the network
    if total_nodes >= num_rounds:
        source_nodes = rng.sample(all_target_nodes, num_rounds)
    else:
        source_nodes = [rng.choice(all_target_nodes) for _ in range(num_rounds)]

    # Pre-build HTTP Basic Auth headers for all nodes
    auth_headers: dict[int, dict[str, str]] = {}
    for nid in all_target_nodes:
        cfg = get_node_config(nid)
        auth_headers[nid] = {
            "Authorization": aiohttp.BasicAuth(cfg.rpc_user, cfg.rpc_pass).encode(),
            "Content-Type": "application/json",
        }

    connector = aiohttp.TCPConnector(limit=0, limit_per_host=0)
    timeout = aiohttp.ClientTimeout(total=5.0)

    # Edge observations: edge_str -> list of observed valid delays across rounds
    edge_observations: dict[str, list[float]] = {}
    round_telemetries: list[dict[str, Any]] = []

    log.info("Beginning %d live measurement rounds on running RegTest daemons...", num_rounds)
    t_start_all = time.time()

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for r_idx, src in enumerate(source_nodes):
            telemetry, round_delays = await run_single_live_round(
                round_index=r_idx + 1,
                source_node=src,
                all_target_nodes=all_target_nodes,
                all_edges=all_edges,
                session=session,
                auth_headers=auth_headers,
                mining_address=mining_address,
                epsilon_ms=epsilon_ms,
            )

            round_telemetries.append({
                "round": telemetry.round_index,
                "source_node": telemetry.source_node,
                "block_hash": telemetry.block_hash,
                "mining_duration_ms": telemetry.mining_duration_ms,
                "nodes_reached": telemetry.nodes_reached,
                "total_propagation_duration_ms": telemetry.total_propagation_duration_ms,
                "observed_edges_count": telemetry.observed_edges_count,
            })

            for edge_key, delay in round_delays.items():
                if edge_key not in edge_observations:
                    edge_observations[edge_key] = []
                edge_observations[edge_key].append(delay)

            # Brief pause between rounds to ensure clean network steady-state
            await asyncio.sleep(0.1)

    t_total_all = time.time() - t_start_all
    log.info("Finished %d live rounds in %.2f seconds.", num_rounds, t_total_all)

    # Compute d(u, v) = min_{r} Delta_r(u, v)
    edge_delays_min: dict[str, float] = {}
    for edge_key, obs_list in edge_observations.items():
        edge_delays_min[edge_key] = round(min(obs_list), 4)

    # Fallback calculation for any unobserved edges
    all_observed_mins = list(edge_delays_min.values())
    fallback_delay = round(statistics.median(all_observed_mins), 4) if all_observed_mins else 10.0

    unobserved_count = 0
    for edge in all_edges:
        edge_key = canonical_edge_str(edge[0], edge[1])
        if edge_key not in edge_delays_min:
            edge_delays_min[edge_key] = fallback_delay
            unobserved_count += 1

    stats = {
        "num_rounds": num_rounds,
        "total_topology_edges": total_edges,
        "edges_directly_observed": len(edge_observations),
        "edges_fallback_filled": unobserved_count,
        "coverage_percentage": round(len(edge_observations) / total_edges * 100.0, 2),
        "min_delay_ms": round(min(edge_delays_min.values()), 4),
        "mean_delay_ms": round(statistics.mean(edge_delays_min.values()), 4),
        "median_delay_ms": round(statistics.median(edge_delays_min.values()), 4),
        "max_delay_ms": round(max(edge_delays_min.values()), 4),
        "fallback_default_delay_ms": fallback_delay,
        "total_measurement_time_sec": round(t_total_all, 2),
    }

    result_data = {
        "metadata": {
            "description": f"Empirical minimum edge delays d(u, v) = min_{{r}} |T_r(u) - T_r(v)| across {num_rounds} live RegTest rounds",
            "formula": f"Delta_r(u, v) = |T_r(u) - T_r(v)| > {epsilon_ms} ms; d(u, v) = min_r Delta_r(u, v)",
            "unit": "milliseconds",
            "source_nodes": source_nodes,
            "epsilon_ms": epsilon_ms,
        },
        "statistics": stats,
        "rounds": round_telemetries,
        "edge_delays": edge_delays_min,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    # Update link_latencies.json alias as well
    alias_path = out_path.parent / "link_latencies.json"
    with open(alias_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    log.info("Saved %d edge delays to %s (and alias %s)", len(edge_delays_min), out_path, alias_path)
    log.info(
        "Final Delay Statistics: coverage=%.1f%%, min=%.2fms, mean=%.2fms, median=%.2fms, max=%.2fms",
        stats["coverage_percentage"],
        stats["min_delay_ms"],
        stats["mean_delay_ms"],
        stats["median_delay_ms"],
        stats["max_delay_ms"],
    )

    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure 30 rounds of live block propagation delays on running RegTest network"
    )
    parser.add_argument("--rounds", type=int, default=30, help="Number of propagation rounds (default: 30)")
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY_PATH, help="Path to groundtruth_topology.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_LIVE_DELAYS_OUT, help="Output JSON path")
    parser.add_argument("--epsilon-ms", type=float, default=0.05, help="Minimum non-zero delta filter threshold (default: 0.05 ms)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for source selection (default: 42)")

    args = parser.parse_args()

    asyncio.run(
        measure_live_edge_delays_async(
            num_rounds=args.rounds,
            topology_path=args.topology,
            out_path=args.out,
            epsilon_ms=args.epsilon_ms,
            seed=args.seed,
        )
    )


if __name__ == "__main__":
    main()
