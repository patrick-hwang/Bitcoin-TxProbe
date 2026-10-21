"""Role 1: The Forker Actuator.

Coordinates the phased release of the blockchain fork:
1. Submits Block B1 to Node 2 and monitors propagation until 100% convergence.
2. Submits branch B2 + B3 to trigger network-wide reorganization.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import sys
import time
from typing import Any

# Add project root and module to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
for p in (TXPROBE_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from txprobe.rpc.client import AsyncBitcoinRpc, RpcError

try:
    from .block_builder import ForkPackage
    from .config import ExperimentConfig, compute_bfs_distances, get_node_config, load_topology
    from .funding import make_rpc_client
    from .prober import SubgraphTracker
except ImportError:
    from block_builder import ForkPackage
    from config import ExperimentConfig, compute_bfs_distances, get_node_config, load_topology
    from funding import make_rpc_client
    from prober import SubgraphTracker

log = logging.getLogger("snapshot_fork.forker")


@dataclass(frozen=True)
class ForkerExecutionTimings:
    """Detailed timing records of the fork publication and propagation phases."""
    b1_published_at: float
    b1_converged_at: float
    b1_propagation_duration_ms: float
    b2_published_at: float
    b3_published_at: float
    reorg_converged_at: float
    reorg_propagation_duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "b1_published_at": self.b1_published_at,
            "b1_converged_at": self.b1_converged_at,
            "b1_propagation_duration_ms": round(self.b1_propagation_duration_ms, 2),
            "b2_published_at": self.b2_published_at,
            "b3_published_at": self.b3_published_at,
            "reorg_converged_at": self.reorg_converged_at,
            "reorg_propagation_duration_ms": round(self.reorg_propagation_duration_ms, 2),
        }


async def submit_block_to_node(node_id: int, block_hex: str) -> str | None:
    """Submit a raw block hex to a node via submitblock RPC."""
    async with make_rpc_client(node_id) as rpc:
        try:
            res = await rpc.call("submitblock", block_hex)
            # submitblock returns None on success, or a string reason (e.g. "duplicate", "inconclusive")
            return res
        except RpcError as e:
            log.warning("RPC error submitting block to Node %d: %s", node_id, e)
            return str(e)


async def check_nodes_best_block(node_ids: list[int], target_hash: str) -> tuple[int, int]:
    """Check how many of the given nodes have target_hash as their best block tip.

    Returns:
        tuple[int, int]: (converged_count, total_queried)
    """
    async def _check_one(nid: int) -> bool:
        try:
            async with make_rpc_client(nid, timeout_sec=2.0) as rpc:
                tip = await rpc.call("getbestblockhash")
                return tip == target_hash
        except Exception:
            return False

    results = await asyncio.gather(*[_check_one(nid) for nid in node_ids])
    converged = sum(1 for r in results if r)
    return converged, len(node_ids)


async def wait_for_convergence_barrier(
    target_block_hash: str,
    peripheral_node_ids: list[int],
    tracker: SubgraphTracker | None = None,
    poll_interval_sec: float = 0.05,
    timeout_sec: float = 10.0,
) -> float:
    """Monitor network until peripheral nodes adopt target_block_hash or timeout expires.

    Because peripheral nodes are at maximum hop distance (Hop 5), when peripheral nodes
    adopt target_block_hash, all intermediate nodes have already absorbed the block.

    Returns:
        float: timestamp of full convergence.
    """
    t0 = time.monotonic()
    log.info("Monitoring propagation of %s across %d peripheral nodes (timeout=%.1fs)...",
             target_block_hash[:16], len(peripheral_node_ids), timeout_sec)

    while (time.monotonic() - t0) < timeout_sec:
        converged, total = await check_nodes_best_block(peripheral_node_ids, target_block_hash)
        if converged == total and total > 0:
            conv_t = time.time()
            log.info("100%% convergence reached! All %d peripheral nodes adopted %s in %.3fs",
                     total, target_block_hash[:16], time.monotonic() - t0)
            return conv_t

        await asyncio.sleep(poll_interval_sec)

    log.warning("Timeout waiting for convergence of %s after %.1fs", target_block_hash[:16], timeout_sec)
    return time.time()


async def execute_forker_sequence(
    fork_pkg: ForkPackage,
    config: ExperimentConfig | None = None,
    tracker: SubgraphTracker | None = None,
    peripheral_nodes: list[int] | None = None,
) -> ForkerExecutionTimings:
    """Execute Role 1 forker sequence:

    Phase 1: Submit Block B1 to Node 2.
    Phase 2: Wait for B1 propagation across peripheral nodes.
    Phase 3: Submit Block B2 (side-branch), then Block B3 (reorg trigger).
    Phase 4: Wait for B3 reorganization convergence.
    """
    if config is None:
        config = ExperimentConfig()

    forker_id = config.forker_id
    if peripheral_nodes is None:
        adj = load_topology(config.topology_path)
        distances = compute_bfs_distances(adj, forker_id)
        max_dist = max(distances.values())
        peripheral_nodes = [nid for nid, d in distances.items() if d == max_dist]
        log.info("Identified %d peripheral nodes at max distance %d hops from Forker.",
                 len(peripheral_nodes), max_dist)

    # ─────────────────────────────────────────────────────────────
    # Phase 1: Publish B1
    # ─────────────────────────────────────────────────────────────
    log.info("=== Phase 1: Publishing Block B1 to Node %d ===", forker_id)
    t_pub_b1 = time.time()
    res_b1 = await submit_block_to_node(forker_id, fork_pkg.b1.block_hex)
    log.info("Submitted B1 (%s): %s", fork_pkg.b1.block_hash, res_b1 if res_b1 else "Accepted as Active Tip")
    if tracker:
        tracker.record_event(forker_id, fork_pkg.b1.block_hash, timestamp=t_pub_b1, message_type="submitblock")

    # ─────────────────────────────────────────────────────────────
    # Phase 2: Wait for B1 Propagation Convergence
    # ─────────────────────────────────────────────────────────────
    log.info("=== Phase 2: Waiting for B1 Propagation Convergence ===")
    t_conv_b1 = await wait_for_convergence_barrier(
        target_block_hash=fork_pkg.b1.block_hash,
        peripheral_node_ids=peripheral_nodes,
        tracker=tracker,
        timeout_sec=config.propagation_timeout_sec,
    )
    b1_duration_ms = (t_conv_b1 - t_pub_b1) * 1000.0
    log.info("B1 propagation completed in %.2f ms", b1_duration_ms)

    # ─────────────────────────────────────────────────────────────
    # Phase 3: Publish B2 + B3 (Chain Reorganization)
    # ─────────────────────────────────────────────────────────────
    log.info("=== Phase 3: Publishing Branch B2 + B3 ===")
    t_pub_b2 = time.time()
    res_b2 = await submit_block_to_node(forker_id, fork_pkg.b2.block_hex)
    log.info("Submitted B2 (%s): %s (accepted as side branch)", fork_pkg.b2.block_hash, res_b2)
    if tracker:
        tracker.record_event(forker_id, fork_pkg.b2.block_hash, timestamp=t_pub_b2, message_type="submitblock")

    t_pub_b3 = time.time()
    res_b3 = await submit_block_to_node(forker_id, fork_pkg.b3.block_hex)
    log.info("Submitted B3 (%s): %s (reorg trigger)", fork_pkg.b3.block_hash, res_b3 if res_b3 else "Accepted as Active Tip")
    if tracker:
        tracker.record_event(forker_id, fork_pkg.b3.block_hash, timestamp=t_pub_b3, message_type="submitblock")

    # ─────────────────────────────────────────────────────────────
    # Phase 4: Wait for Reorganization Convergence (B3)
    # ─────────────────────────────────────────────────────────────
    log.info("=== Phase 4: Waiting for Reorganization Convergence (B3) ===")
    t_conv_reorg = await wait_for_convergence_barrier(
        target_block_hash=fork_pkg.b3.block_hash,
        peripheral_node_ids=peripheral_nodes,
        tracker=tracker,
        timeout_sec=config.propagation_timeout_sec,
    )
    reorg_duration_ms = (t_conv_reorg - t_pub_b3) * 1000.0
    log.info("Reorganization to B3 completed in %.2f ms", reorg_duration_ms)

    return ForkerExecutionTimings(
        b1_published_at=t_pub_b1,
        b1_converged_at=t_conv_b1,
        b1_propagation_duration_ms=b1_duration_ms,
        b2_published_at=t_pub_b2,
        b3_published_at=t_pub_b3,
        reorg_converged_at=t_conv_reorg,
        reorg_propagation_duration_ms=reorg_duration_ms,
    )
