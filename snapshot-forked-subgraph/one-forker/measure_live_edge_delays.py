#!/usr/bin/env python3
"""Multi-Process Concurrent Live Block Propagation & Minimum Edge Delay Measurer.

Measures empirical link propagation delays across multiple rounds on the running
1,000-node RegTest network using a Multi-Process Concurrency Pool:
1. Divides the 1,000 nodes among N Worker Processes (default 20, matching CPU cores).
   Each worker process manages persistent HTTP Keep-Alive sessions for only ~50 nodes,
   eliminating Python asyncio event loop queuing skew (<2ms polling cycle per worker).
2. Uses shared memory (multiprocessing.Array) for zero-copy, lock-free timestamping.
3. For every adjacent link (u, v) in the ground truth topology, calculates:
     Delta_r(u, v) = |T_r(u) - T_r(v)|
   Filters out sibling arrivals where Delta_r <= epsilon (default 0.05 ms).
4. Extracts empirical minimum edge delay across all rounds:
     d(u, v) = min_{r, Delta_r > epsilon} Delta_r(u, v)
5. Exports full delay matrix and statistics to JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
import json
import logging
import math
import multiprocessing as mp
import os
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

DEFAULT_LIVE_DELAYS_OUT = DEFAULT_RESULTS_DIR / "edge_delays_live_100rounds_mp.json"
DEFAULT_MINING_ADDRESS = "bcrt1qq25myyqyfvfaug3ramvssxpna0zvpayy09t99j"


def canonical_edge(u: int, v: int) -> tuple[int, int]:
    """Return canonical undirected edge tuple (min(u, v), max(u, v))."""
    return (u, v) if u < v else (v, u)


def canonical_edge_str(u: int, v: int) -> str:
    """Return canonical undirected edge string 'min_max'."""
    return f"{min(u, v)}_{max(u, v)}"


def worker_process_main(
    worker_id: int,
    node_ids: list[int],
    shared_timestamps: mp.Array,
    shared_tip: mp.Array,
    arm_event: mp.Event,
    stop_event: mp.Event,
    done_event: mp.Event,
    shutdown_event: mp.Event,
) -> None:
    """Worker process body: runs independent asyncio event loop polling its dedicated node partition."""
    # Raise file descriptors inside worker
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 65535))
    except Exception:
        pass

    async def worker_loop() -> None:
        connector = aiohttp.TCPConnector(limit=0, limit_per_host=0)
        timeout = aiohttp.ClientTimeout(total=2.0)
        auth_headers: dict[int, dict[str, str]] = {}
        urls: dict[int, str] = {}
        payloads: dict[int, dict[str, Any]] = {}

        for nid in node_ids:
            cfg = get_node_config(nid)
            auth_str = f"{cfg.rpc_user}:{cfg.rpc_pass}"
            auth_token = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
            auth_headers[nid] = {
                "Authorization": auth_token,
                "Content-Type": "application/json",
            }
            urls[nid] = cfg.rpc_url
            payloads[nid] = {"jsonrpc": "1.0", "id": nid, "method": "getbestblockhash", "params": []}

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            while not shutdown_event.is_set():
                # Wait for Master arm signal
                while not arm_event.is_set() and not shutdown_event.is_set():
                    await asyncio.sleep(0.001)

                if shutdown_event.is_set():
                    break

                old_tip = shared_tip.value.decode("ascii")
                pending = set(node_ids)

                async def poll_single_node(nid: int) -> None:
                    url = urls[nid]
                    headers = auth_headers[nid]
                    payload = payloads[nid]

                    while nid in pending and not stop_event.is_set():
                        try:
                            async with session.post(url, json=payload, headers=headers) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    tip = data.get("result")
                                    if tip and tip != old_tip:
                                        shared_timestamps[nid] = time.time()
                                        pending.remove(nid)
                                        return
                        except Exception:
                            pass
                        await asyncio.sleep(0.002)

                # Poll all nodes in partition concurrently
                await asyncio.gather(*[poll_single_node(nid) for nid in list(node_ids)])
                done_event.set()

                # Wait until Master clears arm_event before accepting next round
                while arm_event.is_set() and not shutdown_event.is_set():
                    await asyncio.sleep(0.001)

    asyncio.run(worker_loop())


def measure_live_edge_delays_multiprocess(
    num_rounds: int = 100,
    num_workers: int = 20,
    topology_path: Path = DEFAULT_TOPOLOGY_PATH,
    out_path: Path = DEFAULT_LIVE_DELAYS_OUT,
    mining_address: str = DEFAULT_MINING_ADDRESS,
    epsilon_ms: float = 0.05,
    seed: int = 42,
    timeout_sec: float = 5.0,
) -> dict[str, Any]:
    """Execute live measurement across 1,000 nodes using 20 parallel worker processes."""
    adj = load_topology(topology_path, symmetrize=True)
    all_target_nodes = sorted(adj.keys())
    total_nodes = len(all_target_nodes)

    all_edges: set[tuple[int, int]] = set()
    for u in all_target_nodes:
        for v in adj[u]:
            all_edges.add(canonical_edge(u, v))
    total_edges = len(all_edges)

    actual_workers = min(num_workers, total_nodes, os.cpu_count() or 4)
    log.info(
        "Initializing Multi-Process delay measurement: %d rounds, %d workers on %d CPU cores, %d nodes, %d edges.",
        num_rounds,
        actual_workers,
        os.cpu_count() or 1,
        total_nodes,
        total_edges,
    )

    # Partition nodes evenly across workers
    chunk_size = math.ceil(total_nodes / actual_workers)
    node_chunks: list[list[int]] = []
    for i in range(actual_workers):
        chunk = all_target_nodes[i * chunk_size : (i + 1) * chunk_size]
        if chunk:
            node_chunks.append(chunk)

    actual_workers = len(node_chunks)

    # Shared memory structures
    shared_timestamps = mp.Array("d", 1002)
    shared_tip = mp.Array("c", 65)
    shared_tip.value = b"0" * 64

    # Synchronization primitives
    arm_events = [mp.Event() for _ in range(actual_workers)]
    stop_events = [mp.Event() for _ in range(actual_workers)]
    done_events = [mp.Event() for _ in range(actual_workers)]
    shutdown_event = mp.Event()

    # Launch worker processes
    workers: list[mp.Process] = []
    for i in range(actual_workers):
        p = mp.Process(
            target=worker_process_main,
            args=(
                i,
                node_chunks[i],
                shared_timestamps,
                shared_tip,
                arm_events[i],
                stop_events[i],
                done_events[i],
                shutdown_event,
            ),
            daemon=True,
        )
        p.start()
        workers.append(p)

    time.sleep(0.3)  # Allow workers to establish persistent connections
    log.info("All %d worker processes initialized and listening.", actual_workers)

    rng = random.Random(seed)
    if total_nodes >= num_rounds:
        source_nodes = rng.sample(all_target_nodes, num_rounds)
    else:
        source_nodes = [rng.choice(all_target_nodes) for _ in range(num_rounds)]

    edge_observations: dict[str, list[float]] = {}
    round_telemetries: list[dict[str, Any]] = []

    t_start_all = time.time()

    async def run_round_loop() -> None:
        for r_idx, src in enumerate(source_nodes):
            round_idx = r_idx + 1
            cfg_src = get_node_config(src)

            # 1. Reset shared timestamps and fetch current tip
            for nid in all_target_nodes:
                shared_timestamps[nid] = 0.0

            async with AsyncBitcoinRpc("127.0.0.1", cfg_src.rpc_port, cfg_src.rpc_user, cfg_src.rpc_pass, timeout_sec=3.0) as rpc:
                old_tip = await rpc.call("getbestblockhash")

            shared_tip.value = old_tip.encode("ascii")

            # 2. Reset worker events and arm all workers simultaneously
            for i in range(actual_workers):
                stop_events[i].clear()
                done_events[i].clear()
                arm_events[i].set()

            # 3. Mine block on source node
            t_mine_start = time.time()
            async with AsyncBitcoinRpc("127.0.0.1", cfg_src.rpc_port, cfg_src.rpc_user, cfg_src.rpc_pass, timeout_sec=5.0) as rpc:
                block_hashes = await rpc.call("generatetoaddress", 1, mining_address)
            new_hash = block_hashes[0]
            t_mined = time.time()
            mining_dur_ms = (t_mined - t_mine_start) * 1000.0

            if shared_timestamps[src] == 0.0:
                shared_timestamps[src] = t_mined

            # 4. Wait for all workers to finish or timeout
            deadline = time.time() + timeout_sec
            while not all(e.is_set() for e in done_events) and time.time() < deadline:
                await asyncio.sleep(0.01)

            # Signal stop to any lagging worker
            for i in range(actual_workers):
                stop_events[i].set()

            # Clear arm events so workers wait for next round
            for i in range(actual_workers):
                arm_events[i].clear()

            # 5. Extract arrival times from shared memory
            arrival_times: dict[int, float] = {}
            for nid in all_target_nodes:
                t_val = shared_timestamps[nid]
                if t_val > 0.0:
                    arrival_times[nid] = t_val

            total_dur_ms = (max(arrival_times.values()) - min(arrival_times.values())) * 1000.0 if arrival_times else 0.0

            # 6. Calculate edge delays for this round
            round_delays: dict[str, float] = {}
            for u, v in all_edges:
                if u in arrival_times and v in arrival_times:
                    delta_ms = abs(arrival_times[u] - arrival_times[v]) * 1000.0
                    if delta_ms > epsilon_ms:
                        edge_key = canonical_edge_str(u, v)
                        round_delays[edge_key] = delta_ms
                        if edge_key not in edge_observations:
                            edge_observations[edge_key] = []
                        edge_observations[edge_key].append(delta_ms)

            telemetry = {
                "round": round_idx,
                "source_node": src,
                "block_hash": new_hash,
                "mining_duration_ms": round(mining_dur_ms, 2),
                "nodes_reached": len(arrival_times),
                "total_propagation_duration_ms": round(total_dur_ms, 2),
                "observed_edges_count": len(round_delays),
            }
            round_telemetries.append(telemetry)

            log.info(
                "Round %3d/%d (MP-Pool) | Src %4d | Reached: %d/%d nodes in %5.1f ms | Valid Edges: %d/%d",
                round_idx,
                num_rounds,
                src,
                len(arrival_times),
                total_nodes,
                total_dur_ms,
                len(round_delays),
                total_edges,
            )

            await asyncio.sleep(0.05)

    try:
        asyncio.run(run_round_loop())
    finally:
        # Shutdown worker processes gracefully
        log.info("Shutting down %d worker processes...", actual_workers)
        shutdown_event.set()
        for e in arm_events:
            e.set()
        for p in workers:
            p.join(timeout=1.0)
            if p.is_alive():
                p.terminate()

    t_total_all = time.time() - t_start_all
    log.info("Completed %d Multi-Process live rounds in %.2f seconds.", num_rounds, t_total_all)

    # Compute d(u, v) = min_{r} Delta_r(u, v)
    edge_delays_min: dict[str, float] = {}
    for edge_key, obs_list in edge_observations.items():
        edge_delays_min[edge_key] = round(min(obs_list), 4)

    # Fallback calculation
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
        "concurrency_workers": actual_workers,
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
            "description": f"Empirical minimum edge delays d(u, v) = min_{{r}} |T_r(u) - T_r(v)| across {num_rounds} live RegTest rounds using {actual_workers} Multi-Process workers",
            "formula": f"Delta_r(u, v) = |T_r(u) - T_r(v)| > {epsilon_ms} ms; d(u, v) = min_r Delta_r(u, v)",
            "unit": "milliseconds",
            "source_nodes": source_nodes,
            "epsilon_ms": epsilon_ms,
            "concurrency_workers": actual_workers,
        },
        "statistics": stats,
        "rounds": round_telemetries,
        "edge_delays": edge_delays_min,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    # Update alias link_latencies.json
    alias_path = out_path.parent / "link_latencies.json"
    with open(alias_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    log.info("Saved %d edge delays to %s (and alias %s)", len(edge_delays_min), out_path, alias_path)
    log.info(
        "Final MP Delay Statistics: coverage=%.1f%%, min=%.2fms, mean=%.2fms, median=%.2fms, max=%.2fms",
        stats["coverage_percentage"],
        stats["min_delay_ms"],
        stats["mean_delay_ms"],
        stats["median_delay_ms"],
        stats["max_delay_ms"],
    )

    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure live block propagation delays on RegTest network using Multi-Process Concurrency"
    )
    parser.add_argument("--rounds", type=int, default=100, help="Number of propagation rounds (default: 100)")
    parser.add_argument("--workers", type=int, default=20, help="Number of concurrent worker processes (default: 20)")
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY_PATH, help="Path to groundtruth_topology.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_LIVE_DELAYS_OUT, help="Output JSON path")
    parser.add_argument("--epsilon-ms", type=float, default=0.05, help="Minimum non-zero delta filter threshold (default: 0.05 ms)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for source selection (default: 42)")

    args = parser.parse_args()

    measure_live_edge_delays_multiprocess(
        num_rounds=args.rounds,
        num_workers=args.workers,
        topology_path=args.topology,
        out_path=args.out,
        epsilon_ms=args.epsilon_ms,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
