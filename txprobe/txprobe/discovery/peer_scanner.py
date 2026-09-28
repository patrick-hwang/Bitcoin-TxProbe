"""Phase 2 — Batch connection attempts, mutual peer polling, and selection."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..models.node import CandidateNode, CandidatePriority, NodeIdentity
from ..rpc.client import AsyncBitcoinRpc
from .harvester import HarvestResult, _SKIP_CONN_TYPES

log = logging.getLogger(__name__)


@dataclass
class ScanStats:
    """Statistics from the Phase 2 peer scanning and selection process."""
    candidates_input: int = 0
    onetry_sent_probes: dict[int, int] = field(default_factory=dict)
    connected_probes: dict[int, int] = field(default_factory=dict)
    mutual_connected: int = 0
    selected_count: int = 0
    excess_disconnected_probes: dict[int, int] = field(default_factory=dict)
    early_exit: bool = False
    polls_count: int = 0
    elapsed_sec: float = 0.0
    timestamp: str = ""


@dataclass
class ScanResult:
    """Output of Phase 2 batch connection and peer selection."""
    selected_nodes: list[CandidateNode]
    probe_ids: tuple[int, int] = (0, 1)
    stats: ScanStats = field(default_factory=ScanStats)

    def selected_identities(self) -> list[NodeIdentity]:
        """Return the ordered list of selected NodeIdentity instances."""
        return [c.identity for c in self.selected_nodes]

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "timestamp": self.stats.timestamp,
            "elapsed_sec": round(self.stats.elapsed_sec, 2),
            "probe_ids": list(self.probe_ids),
            "stats": {
                "candidates_input": self.stats.candidates_input,
                "onetry_sent_probes": {
                    str(k): v for k, v in sorted(self.stats.onetry_sent_probes.items())
                },
                "connected_probes": {
                    str(k): v for k, v in sorted(self.stats.connected_probes.items())
                },
                "mutual_connected": self.stats.mutual_connected,
                "selected_count": self.stats.selected_count,
                "excess_disconnected_probes": {
                    str(k): v
                    for k, v in sorted(self.stats.excess_disconnected_probes.items())
                },
                "early_exit": self.stats.early_exit,
                "polls_count": self.stats.polls_count,
            },
            "selected_nodes": [
                {
                    "addr": c.identity.addr,
                    "priority": int(c.priority),
                    "network": c.network,
                    "source_node_id": c.source_node_id,
                    "last_seen": c.last_seen,
                }
                for c in self.selected_nodes
            ],
        }

    def save(self, path: Path) -> None:
        """Write scan result to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> ScanResult:
        """Deserialize a ScanResult from a JSON dict."""
        raw_stats = data.get("stats", {})
        stats = ScanStats(
            candidates_input=int(raw_stats.get("candidates_input", 0)),
            onetry_sent_probes={
                int(k): int(v)
                for k, v in raw_stats.get("onetry_sent_probes", {}).items()
            },
            connected_probes={
                int(k): int(v)
                for k, v in raw_stats.get("connected_probes", {}).items()
            },
            mutual_connected=int(raw_stats.get("mutual_connected", 0)),
            selected_count=int(raw_stats.get("selected_count", 0)),
            excess_disconnected_probes={
                int(k): int(v)
                for k, v in raw_stats.get("excess_disconnected_probes", {}).items()
            },
            early_exit=bool(raw_stats.get("early_exit", False)),
            polls_count=int(raw_stats.get("polls_count", 0)),
            elapsed_sec=float(data.get("elapsed_sec", 0.0)),
            timestamp=str(data.get("timestamp", "")),
        )

        raw_probe_ids = data.get("probe_ids", [0, 1])
        probe_ids = (int(raw_probe_ids[0]), int(raw_probe_ids[1]))

        selected_nodes = [
            CandidateNode(
                identity=NodeIdentity(addr=c["addr"]),
                priority=CandidatePriority(int(c["priority"])),
                network=str(c["network"]),
                source_node_id=int(c["source_node_id"]),
                last_seen=int(c.get("last_seen", 0)),
            )
            for c in data.get("selected_nodes", [])
        ]

        return cls(
            selected_nodes=selected_nodes,
            probe_ids=probe_ids,
            stats=stats,
        )

    @classmethod
    def load(cls, path: str | Path) -> ScanResult:
        """Load a ScanResult from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


async def scan_and_select_peers(
    config: Config,
    harvest: HarvestResult,
    *,
    disconnect_chunk_size: int = 50,
) -> ScanResult:
    """Main Phase 2 entry point — connect probes to candidates and select mutual peers.

    Steps:
        2.1  Order candidates by (priority, is_onion) and filter out already-connected
             peers per probe node.
        2.2  Concurrently dispatch ``addnode(addr, "onetry")`` on both probe nodes
             using a bounded worker pool while polling ``getpeerinfo()`` every
             ``poll_interval_sec`` up to ``crawling_time_sec``. Exit early as soon
             as ``|P_a ∩ P_b ∩ Candidates| >= target_count``.
        2.3  Select up to ``target_count`` mutual peers in priority order and
             disconnect excess peers on both probe nodes via ``disconnectnode``.

    Args:
        config: Experiment configuration.
        harvest: Phase 1 harvest result.
        disconnect_chunk_size: Batch size for ``disconnectnode`` RPC calls.

    Returns:
        ScanResult with the selected mutual peers and statistics.

    Raises:
        ValueError: If fewer than 2 probe nodes are configured in *config*.
    """
    probes = config.probe_nodes
    if len(probes) < 2:
        raise ValueError(
            f"At least 2 probe nodes are required, found {len(probes)}"
        )

    probe_a, probe_b = probes[0], probes[1]
    t0 = time.monotonic()

    target_count = config.discovery.target_count
    crawling_time_sec = config.discovery.crawling_time_sec
    poll_interval_sec = config.discovery.poll_interval_sec
    concurrency = config.discovery.onetry_concurrency

    # Ensure candidates are sorted by priority for final selection
    prioritized_candidates = sorted(harvest.candidates, key=lambda c: c.priority)
    candidate_set: set[NodeIdentity] = {c.identity for c in prioritized_candidates}

    # Order for connection dispatch: within each priority tier, try clearnet before onion
    dispatch_order = _order_candidates_for_dispatch(prioritized_candidates)

    already_a = harvest.already_connected_probes.get(probe_a.id, set())
    already_b = harvest.already_connected_probes.get(probe_b.id, set())

    addrs_to_try_a = [
        c.identity.addr for c in dispatch_order if c.identity not in already_a
    ]
    addrs_to_try_b = [
        c.identity.addr for c in dispatch_order if c.identity not in already_b
    ]

    stats = ScanStats(
        candidates_input=len(prioritized_candidates),
        onetry_sent_probes={probe_a.id: 0, probe_b.id: 0},
        connected_probes={probe_a.id: 0, probe_b.id: 0},
        excess_disconnected_probes={probe_a.id: 0, probe_b.id: 0},
    )

    log.info(
        "Step 2.1: Starting connection scan on Probe %d (%d to try) and Probe %d (%d to try), target=%d, timeout=%.0fs",
        probe_a.id,
        len(addrs_to_try_a),
        probe_b.id,
        len(addrs_to_try_b),
        target_count,
        crawling_time_sec,
    )

    stop_event = asyncio.Event()
    peers_a: set[NodeIdentity] = set()
    peers_b: set[NodeIdentity] = set()
    mutual: set[NodeIdentity] = set()

    async with (
        AsyncBitcoinRpc(probe_a.rpchost, probe_a.rpcport, probe_a.rpcuser, probe_a.rpcpassword) as rpc_a,
        AsyncBitcoinRpc(probe_b.rpchost, probe_b.rpcport, probe_b.rpcuser, probe_b.rpcpassword) as rpc_b,
    ):
        # ── Step 2.2: Concurrent onetry workers + polling loop ──
        worker_a = asyncio.create_task(
            _dispatch_onetry_worker(
                rpc_a,
                addrs_to_try_a,
                concurrency,
                stop_event,
                stats.onetry_sent_probes,
                probe_a.id,
            )
        )
        worker_b = asyncio.create_task(
            _dispatch_onetry_worker(
                rpc_b,
                addrs_to_try_b,
                concurrency,
                stop_event,
                stats.onetry_sent_probes,
                probe_b.id,
            )
        )

        grace_waited = False
        try:
            while True:
                peers_a, peers_b = await asyncio.gather(
                    _fetch_valid_probe_peers(rpc_a, probe_a.id),
                    _fetch_valid_probe_peers(rpc_b, probe_b.id),
                )
                mutual = peers_a & peers_b & candidate_set
                stats.polls_count += 1

                elapsed = time.monotonic() - t0
                log.info(
                    "  [Poll #%d | %.1fs] Probe %d: %d peers | Probe %d: %d peers | Mutual candidates: %d / %d",
                    stats.polls_count,
                    elapsed,
                    probe_a.id,
                    len(peers_a),
                    probe_b.id,
                    len(peers_b),
                    len(mutual),
                    target_count,
                )

                # Early exit when target_count is reached
                if len(mutual) >= target_count:
                    stats.early_exit = True
                    stop_event.set()
                    log.info(
                        "  Target reached (%d >= %d) after %.1fs! Stopping scan early.",
                        len(mutual),
                        target_count,
                        elapsed,
                    )
                    break

                # Timeout check
                if elapsed >= crawling_time_sec:
                    stop_event.set()
                    log.warning(
                        "  Crawling timeout (%.1fs) reached with %d / %d mutual peers.",
                        crawling_time_sec,
                        len(mutual),
                        target_count,
                    )
                    break

                # If both workers have finished sending all onetry calls, wait one
                # final grace interval for in-flight handshakes, poll once more, and exit.
                if worker_a.done() and worker_b.done():
                    if grace_waited:
                        log.info(
                            "  All connection attempts completed (%d mutual peers found).",
                            len(mutual),
                        )
                        break
                    grace_waited = True

                remaining = max(0.0, crawling_time_sec - elapsed)
                sleep_dur = min(poll_interval_sec, remaining)
                if sleep_dur > 0:
                    await asyncio.sleep(sleep_dur)
        finally:
            stop_event.set()
            for w in (worker_a, worker_b):
                if not w.done():
                    w.cancel()
            await asyncio.gather(worker_a, worker_b, return_exceptions=True)

        stats.connected_probes[probe_a.id] = len(peers_a)
        stats.connected_probes[probe_b.id] = len(peers_b)
        stats.mutual_connected = len(mutual)

        # ── Step 2.3: Select top target_count nodes in priority order & disconnect excess ──
        selected_nodes = [
            c for c in prioritized_candidates if c.identity in mutual
        ][:target_count]
        selected_set = {c.identity for c in selected_nodes}
        stats.selected_count = len(selected_nodes)

        log.info(
            "Step 2.3: Selected %d mutual peers. Disconnecting excess peers on Probe %d and Probe %d...",
            len(selected_nodes),
            probe_a.id,
            probe_b.id,
        )

        disc_a, disc_b = await asyncio.gather(
            _disconnect_excess_peers(rpc_a, selected_set, peers_a, disconnect_chunk_size),
            _disconnect_excess_peers(rpc_b, selected_set, peers_b, disconnect_chunk_size),
        )
        stats.excess_disconnected_probes[probe_a.id] = disc_a
        stats.excess_disconnected_probes[probe_b.id] = disc_b

    stats.elapsed_sec = time.monotonic() - t0
    stats.timestamp = datetime.now(timezone.utc).isoformat()
    log.info(
        "Phase 2 complete: %d selected peers (disconnected %d on Probe %d, %d on Probe %d) in %.1fs",
        stats.selected_count,
        disc_a,
        probe_a.id,
        disc_b,
        probe_b.id,
        stats.elapsed_sec,
    )

    return ScanResult(
        selected_nodes=selected_nodes,
        probe_ids=(probe_a.id, probe_b.id),
        stats=stats,
    )


# ── Internal helpers ──


def _order_candidates_for_dispatch(
    candidates: list[CandidateNode],
) -> list[CandidateNode]:
    """Order candidates by (priority, is_onion) so clearnet connects before Tor within each tier."""
    return sorted(
        candidates,
        key=lambda c: (int(c.priority), 1 if c.network == "onion" else 0),
    )


def _extract_valid_probe_peers(peers_raw: list[dict]) -> set[NodeIdentity]:
    """Extract valid full-relay connected peers from getpeerinfo() output.

    Excludes:
        - Localhost connections (127.0.0.1*)
        - Ephemeral connections (feeler, addr-fetch)
        - Block-relay-only connections (do not relay transactions)
        - Connections that have not completed the P2P version handshake (version <= 0)
    """
    valid: set[NodeIdentity] = set()
    for peer in peers_raw:
        addr: str = peer.get("addr", "")
        if not addr or addr.startswith("127.0.0.1"):
            continue

        conn_type: str = peer.get("connection_type", "")
        if conn_type in _SKIP_CONN_TYPES or conn_type == "block-relay-only":
            continue

        version = int(peer.get("version", 70016))
        if version <= 0:
            continue

        valid.add(NodeIdentity(addr=addr))
    return valid


async def _fetch_valid_probe_peers(
    rpc: AsyncBitcoinRpc, probe_id: int
) -> set[NodeIdentity]:
    """Call getpeerinfo() on a probe node and return valid peer identities."""
    try:
        peers_raw = await rpc.getpeerinfo()
        return _extract_valid_probe_peers(peers_raw)
    except Exception as e:
        log.warning("getpeerinfo failed on probe %d: %s", probe_id, e)
        return set()


async def _dispatch_onetry_worker(
    rpc: AsyncBitcoinRpc,
    addrs: list[str],
    concurrency: int,
    stop_event: asyncio.Event,
    counters: dict[int, int],
    probe_id: int,
) -> None:
    """Concurrently dispatch ``addnode(addr, "onetry")`` calls using a semaphore."""
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _try_one(addr: str) -> None:
        if stop_event.is_set():
            return
        async with sem:
            if stop_event.is_set():
                return
            try:
                counters[probe_id] = counters.get(probe_id, 0) + 1
                await rpc.addnode(addr, "onetry")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.debug("addnode onetry failed on probe %d for %s: %s", probe_id, addr, e)

    tasks = [asyncio.create_task(_try_one(addr)) for addr in addrs]
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _disconnect_excess_peers(
    rpc: AsyncBitcoinRpc,
    selected_identities: set[NodeIdentity],
    current_peers: set[NodeIdentity],
    chunk_size: int = 50,
) -> int:
    """Disconnect peers in *current_peers* that are not in *selected_identities*."""
    excess_addrs = sorted(
        p.addr for p in current_peers if p not in selected_identities
    )
    if not excess_addrs:
        return 0

    step = max(1, chunk_size)
    for i in range(0, len(excess_addrs), step):
        chunk = excess_addrs[i : i + step]
        calls = [("disconnectnode", addr) for addr in chunk]
        try:
            await rpc.call_batch(calls, raise_on_error=False)
        except Exception as e:
            log.warning("Batch disconnectnode failed: %s", e)

    return len(excess_addrs)
