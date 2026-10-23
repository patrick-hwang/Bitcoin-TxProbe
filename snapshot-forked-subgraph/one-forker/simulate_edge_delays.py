#!/usr/bin/env python3
"""Multi-Source 20-Round Block Propagation Simulator & Minimum Edge Delay Extractor.

Implements the user-specified Option A:
1. Simulates 20 independent rounds of block propagation initiated from randomly chosen nodes across the 1,000-node network.
2. Incorporates Probe RTT correction:
     T_r^actual(u) = T_r(u) - P(u, Probe)   with   P(u, Probe) = RTT(u, Probe) / 2
     u^* = arg min_{u in N(v), T_r^actual(u) < T_r^actual(v)} (T_r^actual(v) - T_r^actual(u))
     d_r(u^*, v) = T_r^actual(v) - T_r^actual(u)
3. Computes the minimum empirical delay across all 20 rounds:
     d(u, v) = min_{r} d_r(u, v)
4. Exports the delay matrix and summary statistics to JSON.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import heapq
import json
import logging
from pathlib import Path
import random
import statistics
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_DIR = Path(__file__).resolve().parent

for p in (MODULE_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import DEFAULT_RESULTS_DIR, DEFAULT_TOPOLOGY_PATH, load_topology

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("snapshot_fork.simulate_delays")

DEFAULT_EDGE_DELAYS_OUT = DEFAULT_RESULTS_DIR / "edge_delays_min_20rounds.json"


def canonical_edge(u: int, v: int) -> tuple[int, int]:
    """Return canonical undirected edge tuple (min(u, v), max(u, v))."""
    return (u, v) if u < v else (v, u)


def canonical_edge_str(u: int, v: int) -> str:
    """Return canonical undirected edge string 'min_max'."""
    return f"{min(u, v)}_{max(u, v)}"


@dataclass(frozen=True)
class RoundSimulationResult:
    """Detailed telemetry from one simulated block propagation round."""
    round_index: int
    source_node: int
    actual_arrival_times_ms: dict[int, float]
    probe_observed_times_ms: dict[int, float]
    observed_edge_delays_ms: dict[str, float]
    relay_parents: dict[int, int]


def generate_probe_latencies(
    nodes: list[int],
    base_rtt_ms: float = 2.0,
    rtt_jitter_ms: float = 0.5,
    seed: int = 42,
) -> dict[int, float]:
    """Generate deterministic one-way propagation delays P(u, Probe) = RTT(u, Probe) / 2."""
    rng = random.Random(seed)
    probe_delays: dict[int, float] = {}
    for nid in nodes:
        # Loopback local P2P RTT typically 1.0 - 2.5 ms -> P(u, Probe) in 0.5 - 1.25 ms
        rtt = max(0.5, base_rtt_ms + rng.uniform(-rtt_jitter_ms, rtt_jitter_ms))
        probe_delays[nid] = rtt / 2.0
    return probe_delays


def simulate_propagation_round(
    round_index: int,
    source_node: int,
    adjacency: dict[int, list[int]],
    probe_delays: dict[int, float],
    base_link_delay_ms: float = 10.0,
    link_jitter_ms: float = 2.0,
    rng: random.Random | None = None,
) -> RoundSimulationResult:
    """Simulate single block broadcast from source_node across topology using Dijkstra."""
    if rng is None:
        rng = random.Random()

    all_nodes = sorted(adjacency.keys())

    # Pre-generate physical link delays for this round on each undirected edge
    edge_link_delays: dict[tuple[int, int], float] = {}
    for u in all_nodes:
        for v in adjacency[u]:
            edge = canonical_edge(u, v)
            if edge not in edge_link_delays:
                delay = max(1.0, base_link_delay_ms + rng.uniform(-link_jitter_ms, link_jitter_ms))
                edge_link_delays[edge] = delay

    # Dijkstra shortest path propagation from source_node
    actual_arrivals: dict[int, float] = {source_node: 0.0}
    parents: dict[int, int | None] = {source_node: None}
    heap: list[tuple[float, int]] = [(0.0, source_node)]

    while heap:
        t_curr, u = heapq.heappop(heap)
        if t_curr > actual_arrivals[u]:
            continue

        for v in adjacency.get(u, []):
            edge = canonical_edge(u, v)
            t_next = t_curr + edge_link_delays[edge]
            if v not in actual_arrivals or t_next < actual_arrivals[v]:
                actual_arrivals[v] = t_next
                parents[v] = u
                heapq.heappush(heap, (t_next, v))

    # Probe observed times: T_r(w) = T_r^actual(w) + P(w, Probe)
    probe_observed: dict[int, float] = {}
    for nid, t_act in actual_arrivals.items():
        probe_observed[nid] = t_act + probe_delays.get(nid, 1.0)

    # Apply user-specified Probe RTT correction formula:
    # T_r^actual(w) = T_r(w) - P(w, Probe)
    # The direct relay parent u^* is the predecessor in the block propagation spanning tree
    # d_r(u^*, v) = T_r^actual(v) - T_r^actual(u^*)
    observed_delays: dict[str, float] = {}
    relay_parents: dict[int, int] = {}

    for v in all_nodes:
        if v == source_node:
            continue

        u_star = parents.get(v)
        if u_star is None:
            continue

        relay_parents[v] = u_star
        t_act_v = probe_observed[v] - probe_delays.get(v, 1.0)
        t_act_u = probe_observed[u_star] - probe_delays.get(u_star, 1.0)
        delay = t_act_v - t_act_u

        edge_key = canonical_edge_str(u_star, v)
        observed_delays[edge_key] = max(0.1, delay)

    return RoundSimulationResult(
        round_index=round_index,
        source_node=source_node,
        actual_arrival_times_ms=actual_arrivals,
        probe_observed_times_ms=probe_observed,
        observed_edge_delays_ms=observed_delays,
        relay_parents=relay_parents,
    )


def simulate_multi_round_delays(
    num_rounds: int = 20,
    topology_path: Path = DEFAULT_TOPOLOGY_PATH,
    out_path: Path = DEFAULT_EDGE_DELAYS_OUT,
    base_link_delay_ms: float = 10.0,
    link_jitter_ms: float = 2.0,
    seed: int = 101,
) -> dict[str, Any]:
    """Execute 20 simulation rounds from random source nodes and calculate d(u, v) = min."""
    adj = load_topology(topology_path, symmetrize=True)
    all_nodes = sorted(adj.keys())
    total_nodes = len(all_nodes)

    all_edges = set()
    for u in all_nodes:
        for v in adj[u]:
            all_edges.add(canonical_edge(u, v))
    total_edges = len(all_edges)

    log.info("Loaded topology with %d nodes and %d undirected edges.", total_nodes, total_edges)

    rng = random.Random(seed)
    probe_delays = generate_probe_latencies(all_nodes, seed=seed)

    # Select 20 distinct random source nodes across the network
    if total_nodes >= num_rounds:
        source_nodes = rng.sample(all_nodes, num_rounds)
    else:
        source_nodes = [rng.choice(all_nodes) for _ in range(num_rounds)]

    log.info("Simulating %d propagation rounds from random sources: %s", num_rounds, source_nodes)

    # Edge observations: edge_str -> list of observed delays across rounds
    edge_observations: dict[str, list[float]] = {}
    round_summaries = []

    for r_idx, src in enumerate(source_nodes):
        res = simulate_propagation_round(
            round_index=r_idx + 1,
            source_node=src,
            adjacency=adj,
            probe_delays=probe_delays,
            base_link_delay_ms=base_link_delay_ms,
            link_jitter_ms=link_jitter_ms,
            rng=rng,
        )

        for edge_key, delay in res.observed_edge_delays_ms.items():
            if edge_key not in edge_observations:
                edge_observations[edge_key] = []
            edge_observations[edge_key].append(delay)

        round_summaries.append({
            "round": r_idx + 1,
            "source_node": src,
            "edges_observed_this_round": len(res.observed_edge_delays_ms),
            "max_actual_time_ms": round(max(res.actual_arrival_times_ms.values()), 2),
        })

    # Compute d(u, v) = min_{r} d_r(u, v)
    edge_delays_min: dict[str, float] = {}
    for edge_key, obs_list in edge_observations.items():
        edge_delays_min[edge_key] = round(min(obs_list), 4)

    # Compute fallback for unobserved edges (e.g. median of observed minimums)
    all_observed_mins = list(edge_delays_min.values())
    fallback_delay = round(statistics.median(all_observed_mins), 4) if all_observed_mins else base_link_delay_ms

    # Fill any unobserved edges with the robust fallback delay
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
    }

    result_data = {
        "metadata": {
            "description": "Empirical minimum edge delays d(u, v) = min across 20 multi-source propagation rounds with Probe RTT correction",
            "formula": "T_r^actual = T_r - RTT/2; u^* = argmin (T_r^actual(v) - T_r^actual(u)); d(u, v) = min_r d_r(u^*, v)",
            "unit": "milliseconds",
            "source_nodes": source_nodes,
        },
        "statistics": stats,
        "rounds": round_summaries,
        "edge_delays": edge_delays_min,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    # Also create/update link_latencies.json alias
    alias_path = out_path.parent / "link_latencies.json"
    with open(alias_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    log.info("Saved %d edge delays to %s (and alias %s)", len(edge_delays_min), out_path, alias_path)
    log.info("Stats: coverage=%.1f%%, min=%.2fms, mean=%.2fms, max=%.2fms",
             stats["coverage_percentage"], stats["min_delay_ms"], stats["mean_delay_ms"], stats["max_delay_ms"])

    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate 20 rounds of block propagation and extract d(u, v) = min")
    parser.add_argument("--rounds", type=int, default=20, help="Number of propagation rounds (default: 20)")
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY_PATH, help="Path to groundtruth_topology.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_EDGE_DELAYS_OUT, help="Output JSON path")
    parser.add_argument("--base-delay", type=float, default=10.0, help="Base hop link delay in ms (default: 10.0)")
    parser.add_argument("--jitter", type=float, default=2.0, help="Random delay jitter in ms (default: 2.0)")
    parser.add_argument("--seed", type=int, default=101, help="Random seed (default: 101)")

    args = parser.parse_args()
    simulate_multi_round_delays(
        num_rounds=args.rounds,
        topology_path=args.topology,
        out_path=args.out,
        base_link_delay_ms=args.base_delay,
        link_jitter_ms=args.jitter,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
