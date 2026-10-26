#!/usr/bin/env python3
"""Master Orchestrator for Real-Time Blockchain Fork Injection & Subgraph Snapshotting.

Deploys the live fork experiment across 1,000 RegTest nodes using a high-performance
Multi-Process Concurrency Pool:
1. Spawns 20 worker processes running persistent HTTP Keep-Alive sessions (<2ms polling cycle).
2. Submits Block B1 and monitors the exact arrival timestamp on all 1,000 nodes concurrently.
3. Submits Block B2 (side-branch) and Block B3 (reorganization trigger).
4. Monitors real-time reorg arrival across all 1,000 nodes concurrently.
5. Calibrates arrival timestamps using P2P minping RTT compensation from Probe 0:
     T_calib(u) = T_obs(u) - RTT(u, Probe) / 2
6. Emits granular 5ms sliced snapshots of network subgraphs until convergence,
   eliminating synthetic BFS approximations and stagnant duplicates.

Usage:
    python run_experiment.py --step-ms 5.0 --workers 20 --out results/fork_subgraph_live_run_realtime_5ms.json
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
import resource
import statistics
import sys
import time
from typing import Any

# Increase file descriptor limit for concurrent HTTP RPC polling
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, 65535), hard))

import aiohttp

# Add project root and module to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
MODULE_DIR = Path(__file__).resolve().parent

for p in (TXPROBE_DIR, MODULE_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import (
    DEFAULT_FUNDING_TARGET_SATS,
    DEFAULT_RESULTS_DIR,
    DEFAULT_TOPOLOGY_PATH,
    ExperimentConfig,
    check_network_peered,
    connect_network_topology,
    get_node_config,
    load_topology,
    parse_node_id,
    wait_for_topology_ready,
)
from block_builder import ForkPackage, build_fork_package
from funding import ParentUtxo, fund_forker_node
from forker import ForkerExecutionTimings, submit_block_to_node
from prober import SubgraphTracker, create_subgraph_tracker_from_config
from txprobe.rpc.client import AsyncBitcoinRpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("snapshot_fork.orchestrator")

DEFAULT_REALTIME_SNAPSHOT_OUT = DEFAULT_RESULTS_DIR / "fork_subgraph_live_run_realtime_5ms.json"


async def fetch_probe_rtt_map(probe_id: int = 0) -> dict[int, float]:
    """Fetch minping (RTT in ms) for all connected peers from Probe node."""
    cfg = get_node_config(probe_id)
    rtt_map: dict[int, float] = {probe_id: 0.0}
    try:
        async with AsyncBitcoinRpc("127.0.0.1", cfg.rpc_port, cfg.rpc_user, cfg.rpc_pass, timeout_sec=5.0) as rpc:
            peers = await rpc.call("getpeerinfo")
            for p in peers:
                addr = p.get("addr", "")
                nid = parse_node_id(addr)
                minping_s = p.get("minping")
                if minping_s is not None and minping_s > 0:
                    rtt_map[nid] = float(minping_s) * 1000.0
                elif "pingtime" in p and p["pingtime"] > 0:
                    rtt_map[nid] = float(p["pingtime"]) * 1000.0
    except Exception as e:
        log.warning("Failed to fetch getpeerinfo from Probe %d: %s", probe_id, e)
    return rtt_map


def block_monitor_worker_main(
    worker_id: int,
    node_ids: list[int],
    shared_timestamps: mp.Array,
    shared_target_hash: mp.Array,
    arm_event: mp.Event,
    stop_event: mp.Event,
    done_event: mp.Event,
    shutdown_event: mp.Event,
) -> None:
    """Worker process body: concurrently polls dedicated node partition for target block arrival."""
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
                while not arm_event.is_set() and not shutdown_event.is_set():
                    await asyncio.sleep(0.001)

                if shutdown_event.is_set():
                    break

                target_hash = shared_target_hash.value.decode("ascii")
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
                                    if tip == target_hash:
                                        shared_timestamps[nid] = time.time()
                                        pending.remove(nid)
                                        return
                        except Exception:
                            pass
                        await asyncio.sleep(0.002)

                await asyncio.gather(*[poll_single_node(nid) for nid in list(node_ids)])
                done_event.set()

                while arm_event.is_set() and not shutdown_event.is_set():
                    await asyncio.sleep(0.001)

    asyncio.run(worker_loop())


class MultiProcessBlockMonitor:
    """Manages pool of worker processes to observe block arrival times across all nodes in real time."""

    def __init__(self, node_ids: list[int], num_workers: int = 20) -> None:
        self.node_ids = sorted(node_ids)
        self.total_nodes = len(self.node_ids)
        self.actual_workers = min(num_workers, self.total_nodes, os.cpu_count() or 4)

        chunk_size = math.ceil(self.total_nodes / self.actual_workers)
        self.node_chunks: list[list[int]] = []
        for i in range(self.actual_workers):
            chunk = self.node_ids[i * chunk_size : (i + 1) * chunk_size]
            if chunk:
                self.node_chunks.append(chunk)
        self.actual_workers = len(self.node_chunks)

        self.shared_timestamps = mp.Array("d", 1002)
        self.shared_target_hash = mp.Array("c", 65)
        self.arm_events = [mp.Event() for _ in range(self.actual_workers)]
        self.stop_events = [mp.Event() for _ in range(self.actual_workers)]
        self.done_events = [mp.Event() for _ in range(self.actual_workers)]
        self.shutdown_event = mp.Event()

        self.workers: list[mp.Process] = []

    def start(self) -> None:
        for i in range(self.actual_workers):
            p = mp.Process(
                target=block_monitor_worker_main,
                args=(
                    i,
                    self.node_chunks[i],
                    self.shared_timestamps,
                    self.shared_target_hash,
                    self.arm_events[i],
                    self.stop_events[i],
                    self.done_events[i],
                    self.shutdown_event,
                ),
                daemon=True,
            )
            p.start()
            self.workers.append(p)
        time.sleep(0.3)
        log.info("Initialized %d worker processes monitoring %d nodes.", self.actual_workers, self.total_nodes)

    def arm(self, target_hash: str) -> None:
        for nid in self.node_ids:
            self.shared_timestamps[nid] = 0.0
        self.shared_target_hash.value = target_hash.encode("ascii")
        for i in range(self.actual_workers):
            self.stop_events[i].clear()
            self.done_events[i].clear()
            self.arm_events[i].set()

    async def wait_for_completion(self, timeout_sec: float = 10.0) -> dict[int, float]:
        deadline = time.time() + timeout_sec
        while not all(e.is_set() for e in self.done_events) and time.time() < deadline:
            await asyncio.sleep(0.005)

        for i in range(self.actual_workers):
            self.stop_events[i].set()
            self.arm_events[i].clear()

        arrivals: dict[int, float] = {}
        for nid in self.node_ids:
            t = self.shared_timestamps[nid]
            if t > 0.0:
                arrivals[nid] = t
        return arrivals

    def close(self) -> None:
        self.shutdown_event.set()
        for e in self.arm_events:
            e.set()
        for p in self.workers:
            p.join(timeout=1.0)
            if p.is_alive():
                p.terminate()


async def run_live_experiment(
    config: ExperimentConfig,
    step_ms: float = 5.0,
    out_path: Path | None = None,
    num_workers: int = 20,
    use_rtt: bool = True,
    probe_id: int = 0,
) -> Path:
    """Execute the full live experiment on the running 1,000-node RegTest network using real-time MP monitoring."""
    log.info("Starting live fork propagation experiment with Multi-Process Real-Time Monitoring...")

    # 0. Check and ensure P2P topology is connected
    log.info("Step 0: Checking network P2P peering status...")
    is_peered = await check_network_peered(probe_id=probe_id)
    if not is_peered:
        log.info("Connecting 1,000 target nodes and Probes from %s...", config.topology_path)
        await connect_network_topology(config.topology_path, tuple(config.probe_ids))
        log.info("Dispatched connection requests. Waiting for peer handshakes to establish...")
        await wait_for_topology_ready(min_probe_peers=50, timeout_sec=30.0)

    # 1. Fund Node 2 (Forker)
    log.info("Step 1: Verifying UTXO funding on Node %d...", config.forker_id)
    tx0 = await fund_forker_node(
        forker_id=config.forker_id,
        target_amount_sats=config.funding_target_sats,
    )

    # 2. Build offline ForkPackage
    log.info("Step 2: Building offline conflicting transactions and blocks B1, B2, B3...")
    fork_pkg = await build_fork_package(
        forker_id=config.forker_id,
        tx0=tx0,
        config=config,
    )
    height = fork_pkg.parent_height + 1

    # 3. Initialize SubgraphTracker
    log.info("Step 3: Initializing SubgraphTracker for height %d...", height)
    tracker = create_subgraph_tracker_from_config(
        height=height,
        parent_hash=fork_pkg.parent_hash,
        b1_hash=fork_pkg.b1.block_hash,
        b2_hash=fork_pkg.b2.block_hash,
        b3_hash=fork_pkg.b3.block_hash,
        config=config,
    )

    # Fetch RTT map from Probe 0 for latency compensation
    rtt_map: dict[int, float] = {}
    if use_rtt:
        log.info("Fetching P2P minping RTT from Probe %d...", probe_id)
        rtt_map = await fetch_probe_rtt_map(probe_id=probe_id)
        valid_rtts = [v for k, v in rtt_map.items() if k != probe_id]
        if valid_rtts:
            log.info(
                "RTT compensation active (%d nodes): min=%.3fms, median=%.3fms, max=%.3fms",
                len(rtt_map),
                min(valid_rtts),
                statistics.median(valid_rtts),
                max(valid_rtts),
            )

    # 4. Launch Multi-Process Monitor
    monitor = MultiProcessBlockMonitor(tracker.target_node_ids, num_workers=num_workers)
    monitor.start()

    try:
        # ─────────────────────────────────────────────────────────────
        # Phase 1: Publish B1 & Real-time Concurrent Monitoring
        # ─────────────────────────────────────────────────────────────
        log.info("=== Phase 1: Publishing Block B1 to Node %d & Monitoring Live Arrival ===", config.forker_id)
        monitor.arm(fork_pkg.b1.block_hash)
        await asyncio.sleep(0.005)  # Allow workers to enter loop

        t_pub_b1 = time.time()
        res_b1 = await submit_block_to_node(config.forker_id, fork_pkg.b1.block_hex)
        log.info("Submitted B1 (%s): %s", fork_pkg.b1.block_hash[:16], res_b1 if res_b1 else "Accepted as Active Tip")
        tracker.record_event(config.forker_id, fork_pkg.b1.block_hash, timestamp=t_pub_b1, message_type="submitblock")

        b1_arrivals = await monitor.wait_for_completion(timeout_sec=config.propagation_timeout_sec)
        t_conv_b1 = max(b1_arrivals.values()) if b1_arrivals else time.time()
        b1_dur_ms = (t_conv_b1 - t_pub_b1) * 1000.0
        log.info("B1 propagation reached %d/%d nodes in %.2f ms", len(b1_arrivals), len(tracker.target_node_ids), b1_dur_ms)

        # Record calibrated B1 events
        for nid, t_obs in b1_arrivals.items():
            if nid == config.forker_id:
                continue
            rtt_ms = rtt_map.get(nid, 0.32) if (use_rtt and rtt_map) else 0.0
            t_calib = t_obs - (rtt_ms / 2000.0)
            tracker.record_event(nid, fork_pkg.b1.block_hash, timestamp=t_calib, probe_id=probe_id)

        # Small inter-phase stabilization pause
        await asyncio.sleep(0.05)

        # ─────────────────────────────────────────────────────────────
        # Phase 2: Publish B2 (Side-Branch) + B3 (Reorganization Trigger)
        # ─────────────────────────────────────────────────────────────
        log.info("=== Phase 2: Publishing Branch B2 + B3 (Reorg Trigger) & Monitoring Live Arrival ===")
        t_pub_b2 = time.time()
        res_b2 = await submit_block_to_node(config.forker_id, fork_pkg.b2.block_hex)
        log.info("Submitted B2 (%s): %s (side branch)", fork_pkg.b2.block_hash[:16], res_b2)
        tracker.record_event(config.forker_id, fork_pkg.b2.block_hash, timestamp=t_pub_b2, message_type="submitblock")

        monitor.arm(fork_pkg.b3.block_hash)
        await asyncio.sleep(0.005)

        t_pub_b3 = time.time()
        res_b3 = await submit_block_to_node(config.forker_id, fork_pkg.b3.block_hex)
        log.info("Submitted B3 (%s): %s (reorg trigger)", fork_pkg.b3.block_hash[:16], res_b3 if res_b3 else "Accepted as Active Tip")
        tracker.record_event(config.forker_id, fork_pkg.b3.block_hash, timestamp=t_pub_b3, message_type="submitblock")

        b3_arrivals = await monitor.wait_for_completion(timeout_sec=config.propagation_timeout_sec)
        t_conv_reorg = max(b3_arrivals.values()) if b3_arrivals else time.time()
        reorg_dur_ms = (t_conv_reorg - t_pub_b3) * 1000.0
        log.info("Reorganization to B3 reached %d/%d nodes in %.2f ms", len(b3_arrivals), len(tracker.target_node_ids), reorg_dur_ms)

        # Record calibrated B3 events
        for nid, t_obs in b3_arrivals.items():
            if nid == config.forker_id:
                continue
            rtt_ms = rtt_map.get(nid, 0.32) if (use_rtt and rtt_map) else 0.0
            t_calib = t_obs - (rtt_ms / 2000.0)
            tracker.record_event(nid, fork_pkg.b3.block_hash, timestamp=t_calib, probe_id=probe_id)

    finally:
        log.info("Shutting down Multi-Process Block Monitor...")
        monitor.close()

    timings = ForkerExecutionTimings(
        b1_published_at=t_pub_b1,
        b1_converged_at=t_conv_b1,
        b1_propagation_duration_ms=b1_dur_ms,
        b2_published_at=t_pub_b2,
        b3_published_at=t_pub_b3,
        reorg_converged_at=t_conv_reorg,
        reorg_propagation_duration_ms=reorg_dur_ms,
    )

    # 5. Generate sliced snapshots and export
    if out_path is None:
        out_path = DEFAULT_REALTIME_SNAPSHOT_OUT

    valid_rtts = [v for k, v in rtt_map.items() if k != probe_id] if rtt_map else []
    meta = {
        "mode": "live_realtime_multiprocess",
        "timings": timings.to_dict(),
        "conflicts": fork_pkg.conflicts.to_dict(),
        "blocks": {
            "B1": fork_pkg.b1.to_dict(),
            "B2": fork_pkg.b2.to_dict(),
            "B3": fork_pkg.b3.to_dict(),
        },
        "rtt_compensation_enabled": bool(use_rtt and rtt_map),
        "probe_id": probe_id,
        "concurrency_workers": monitor.actual_workers,
        "rtt_statistics_ms": {
            "nodes_count": len(valid_rtts),
            "min_ms": round(min(valid_rtts), 4) if valid_rtts else 0.0,
            "median_ms": round(statistics.median(valid_rtts), 4) if valid_rtts else 0.0,
            "mean_ms": round(statistics.mean(valid_rtts), 4) if valid_rtts else 0.0,
            "max_ms": round(max(valid_rtts), 4) if valid_rtts else 0.0,
        } if valid_rtts else None,
    }

    start_t = timings.b1_published_at
    step_sec = step_ms / 1000.0
    end_t = timings.reorg_converged_at + step_sec
    snapshots = tracker.generate_sliced_snapshots(
        start_time=start_t,
        end_time=end_t,
        step_ms=step_ms,
        stop_on_convergence_hash=fork_pkg.b3.block_hash,
    )

    tracker.export_to_json(out_path, fork_metadata=meta, snapshots=snapshots, step_ms=step_ms)
    log.info("Live real-time experiment complete! Output saved to: %s (%d dynamic snapshots)", out_path, len(snapshots))
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Blockchain Fork Injection and Subgraph Snapshotting on Live RegTest Network (Real-time MP)")
    parser.add_argument("--funding-sats", type=int, default=DEFAULT_FUNDING_TARGET_SATS, help="Target UTXO sats (default: 100,000)")
    parser.add_argument("--step-ms", type=float, default=5.0, help="Snapshot time slice in milliseconds (default: 5.0)")
    parser.add_argument("--timeout", type=float, default=15.0, help="Convergence timeout in seconds (default: 15.0)")
    parser.add_argument("--workers", type=int, default=20, help="Number of concurrent worker processes (default: 20)")
    parser.add_argument("--probe-id", type=int, default=0, help="Probe node ID for RTT minping querying (default: 0)")
    parser.add_argument("--no-rtt", dest="use_rtt", action="store_false", help="Disable RTT latency compensation")
    parser.add_argument("--out", type=Path, default=DEFAULT_REALTIME_SNAPSHOT_OUT, help="Output JSON path")
    parser.set_defaults(use_rtt=True)

    args = parser.parse_args()

    config = ExperimentConfig(
        funding_target_sats=args.funding_sats,
        propagation_timeout_sec=args.timeout,
        snapshot_interval_ms=args.step_ms,
    )

    asyncio.run(run_live_experiment(
        config=config,
        step_ms=args.step_ms,
        out_path=args.out,
        num_workers=args.workers,
        use_rtt=args.use_rtt,
        probe_id=args.probe_id,
    ))


if __name__ == "__main__":
    main()
