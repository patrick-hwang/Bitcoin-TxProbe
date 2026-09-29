"""Step 2: INVBLOCK Pre-filtering for TxProbe.

Identifies and eliminates:
1. Non-responsive / non-relaying nodes that fail to send GETDATA to Probe 0
   (e.g., nodes in Initial Block Download (IBD), blocksonly mode, crawler spiders,
   unresponsive nodes, or high-latency timeouts).
2. Malfunctioning nodes that violate the INVBLOCK mechanism by sending duplicate
   GETDATA requests to Probe 1 for a transaction already blocked / in-flight
   from Probe 0.

Surviving nodes are guaranteed to be active full-relay nodes complying with
Bitcoin Core's inventory deduplication and responsive to TxProbe queries.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Callable

from .models.graph import GraphSnapshot
from .models.node import NodeIdentity
from .models.transaction import TxMessage
from .rpc.client import AsyncBitcoinRpc

log = logging.getLogger(__name__)

# Regular expressions matching GETDATA and blocked notifications in custom bitcoind logs
RE_BLOCKED_NOTFOUND = re.compile(
    r"BLOCKED_NOTFOUND peer=(\d+)\s+addr=(\S+)\s+type=\S+\s+hash=([0-9a-fA-F]{64})"
)
RE_RECEIVED_GETDATA = re.compile(
    r"received getdata for:\s+\S+\s+([0-9a-fA-F]{64})\s+peer=(\d+)"
)


@dataclass(frozen=True)
class InvblockStats:
    """Statistics for the INVBLOCK pre-filtering process."""

    total_initial_nodes: int
    probe_0_active_peers: int
    probe_1_active_peers: int
    mutually_connected_count: int
    probe_0_responsive_count: int
    probe_0_nonresponsive_count: int
    probe_1_violating_count: int
    eliminated_count: int
    remaining_qualified_count: int
    remaining_edges_count: int


@dataclass(frozen=True)
class InvblockResult:
    """Result of Step 2 INVBLOCK pre-filtering."""

    snapshot: GraphSnapshot
    eliminated_nonresponsive: tuple[NodeIdentity, ...]
    eliminated_violating: tuple[NodeIdentity, ...]
    stats: InvblockStats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "snapshot": self.snapshot.to_dict(),
            "eliminated_nonresponsive": [n.addr for n in self.eliminated_nonresponsive],
            "eliminated_violating": [n.addr for n in self.eliminated_violating],
            "stats": {
                "total_initial_nodes": self.stats.total_initial_nodes,
                "probe_0_active_peers": self.stats.probe_0_active_peers,
                "probe_1_active_peers": self.stats.probe_1_active_peers,
                "mutually_connected_count": self.stats.mutually_connected_count,
                "probe_0_responsive_count": self.stats.probe_0_responsive_count,
                "probe_0_nonresponsive_count": self.stats.probe_0_nonresponsive_count,
                "probe_1_violating_count": self.stats.probe_1_violating_count,
                "eliminated_count": self.stats.eliminated_count,
                "remaining_qualified_count": self.stats.remaining_qualified_count,
                "remaining_edges_count": self.stats.remaining_edges_count,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        """Save results to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvblockResult:
        """Deserialize from a dict."""
        snapshot = GraphSnapshot.from_dict(data["snapshot"])
        elim_nonresponsive = tuple(
            NodeIdentity(addr=a) for a in data.get("eliminated_nonresponsive", [])
        )
        elim_violating = tuple(
            NodeIdentity(addr=a) for a in data.get("eliminated_violating", [])
        )
        raw_stats = data["stats"]
        stats = InvblockStats(
            total_initial_nodes=raw_stats["total_initial_nodes"],
            probe_0_active_peers=raw_stats["probe_0_active_peers"],
            probe_1_active_peers=raw_stats["probe_1_active_peers"],
            mutually_connected_count=raw_stats.get("mutually_connected_count", 0),
            probe_0_responsive_count=raw_stats["probe_0_responsive_count"],
            probe_0_nonresponsive_count=raw_stats["probe_0_nonresponsive_count"],
            probe_1_violating_count=raw_stats["probe_1_violating_count"],
            eliminated_count=raw_stats["eliminated_count"],
            remaining_qualified_count=raw_stats["remaining_qualified_count"],
            remaining_edges_count=raw_stats["remaining_edges_count"],
        )
        return cls(
            snapshot=snapshot,
            eliminated_nonresponsive=elim_nonresponsive,
            eliminated_violating=elim_violating,
            stats=stats,
        )

    @classmethod
    def from_json(cls, text: str) -> InvblockResult:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> InvblockResult:
        """Load an InvblockResult from a JSON file."""
        p = Path(path)
        return cls.from_json(p.read_text(encoding="utf-8"))


def craft_dummy_test_transaction(nonce_seed: str | None = None) -> TxMessage:
    """Craft a syntactically valid raw Bitcoin transaction.

    Constructs a 1-input, 1-output transaction that requires no wallet balance
    or on-chain UTXOs. It generates a unique txid and wtxid based on current
    timestamp and an optional seed.

    Args:
        nonce_seed: Optional string seed to randomize the transaction hash.

    Returns:
        TxMessage with raw hex, txid, and wtxid.
    """
    ts_bytes = int(time.time() * 1000).to_bytes(8, "little")
    seed_bytes = (nonce_seed or "txprobe_invblock").encode("utf-8")
    fake_prevout = hashlib.sha256(b"prevout_" + ts_bytes + seed_bytes).digest()

    raw = (
        b"\x01\x00\x00\x00"  # Version 1 (4 bytes)
        b"\x01"              # 1 Input
        + fake_prevout       # Prev txid (32 bytes)
        + b"\x00\x00\x00\x00"# Prev vout 0 (4 bytes)
        + b"\x00"            # ScriptSig length 0
        + b"\xff\xff\xff\xff"# Sequence (4 bytes)
        + b"\x01"            # 1 Output
        + b"\xe8\x03\x00\x00\x00\x00\x00\x00"  # 1000 sats (8 bytes)
        + b"\x16\x00\x14" + (b"\x12" * 20)      # P2WPKH scriptPubKey (22 bytes)
        + b"\x00\x00\x00\x00"# Locktime 0 (4 bytes)
    )

    # Double SHA256 reversed for txid / wtxid (legacy serialization)
    dhash = hashlib.sha256(hashlib.sha256(raw).digest()).digest()
    txid = dhash[::-1].hex()
    return TxMessage(hexstr=raw.hex(), txid=txid, wtxid=txid)


async def craft_test_transaction(
    rpc: AsyncBitcoinRpc | None = None,
    nonce_seed: str | None = None,
) -> TxMessage:
    """Create a test transaction for INVBLOCK testing.

    Attempts to use bitcoind's createrawtransaction and decoderawtransaction
    via RPC if available; falls back to pure-Python crafting if RPC is None
    or fails.

    Args:
        rpc: Optional AsyncBitcoinRpc instance.
        nonce_seed: Optional seed string.

    Returns:
        TxMessage containing the test transaction.
    """
    if rpc is not None:
        try:
            ts_str = f"{int(time.time())}"
            fake_txid = hashlib.sha256((ts_str + (nonce_seed or "")).encode()).hexdigest()
            inputs = [{"txid": fake_txid, "vout": 0}]
            outputs = [{"tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx": 0.0001}]
            raw_hex = await rpc.createrawtransaction(inputs, outputs)
            decoded = await rpc.decoderawtransaction(raw_hex)
            txid = decoded["txid"]
            wtxid = decoded.get("hash", txid)
            return TxMessage(hexstr=raw_hex, txid=txid, wtxid=wtxid)
        except Exception as e:
            log.warning("RPC createrawtransaction failed, falling back to pure-Python: %s", e)

    return craft_dummy_test_transaction(nonce_seed=nonce_seed)


def parse_getdata_peers_from_log(
    log_path: str | Path,
    target_hashes: set[str] | list[str],
    peer_id_to_addr: Mapping[int, str] | None = None,
) -> set[str]:
    """Parse a bitcoind custom txprobe log file to find peers requesting target transactions.

    Finds all peer addresses that triggered:
    1. `BLOCKED_NOTFOUND peer=<id> addr=<addr> type=<type> hash=<hash>`
    2. `received getdata for: <type> <hash> peer=<id>`

    Args:
        log_path: Path to the log file (e.g. `txprobe_0.log`).
        target_hashes: Set or list of txid / wtxid hex strings (case-insensitive).
        peer_id_to_addr: Optional mapping of numeric peer ID to "host:port".

    Returns:
        Set of matching peer address strings ("host:port").
    """
    path = Path(log_path)
    if not path.is_file():
        log.warning("Log file %s does not exist or is not a file", log_path)
        return set()

    target_hashes_lower = {h.lower() for h in target_hashes}
    found_addrs: set[str] = set()

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                # Check BLOCKED_NOTFOUND
                m_blocked = RE_BLOCKED_NOTFOUND.search(line)
                if m_blocked:
                    peer_id = int(m_blocked.group(1))
                    addr = m_blocked.group(2)
                    hash_str = m_blocked.group(3).lower()
                    if hash_str in target_hashes_lower:
                        found_addrs.add(addr)
                        continue

                # Check received getdata
                m_getdata = RE_RECEIVED_GETDATA.search(line)
                if m_getdata:
                    hash_str = m_getdata.group(1).lower()
                    peer_id = int(m_getdata.group(2))
                    if hash_str in target_hashes_lower:
                        if peer_id_to_addr and peer_id in peer_id_to_addr:
                            found_addrs.add(peer_id_to_addr[peer_id])
    except Exception as e:
        log.error("Error reading log file %s: %s", log_path, e)

    return found_addrs


def clear_log_file(log_path: str | Path) -> None:
    """Truncate the log file to empty if it exists."""
    path = Path(log_path)
    try:
        if path.is_file():
            path.write_text("", encoding="utf-8")
            log.debug("Cleared log file: %s", log_path)
    except Exception as e:
        log.warning("Could not clear log file %s: %s", log_path, e)


async def disconnect_peers_parallel(
    rpc: AsyncBitcoinRpc,
    addrs: Iterable[str],
    concurrency: int = 16,
) -> None:
    """Disconnect and remove nodes in parallel on a probe node."""
    sem = asyncio.Semaphore(concurrency)

    async def _disconnect_one(addr: str) -> None:
        async with sem:
            try:
                await rpc.disconnectnode(addr)
            except Exception as e:
                log.debug("disconnectnode %s failed: %s", addr, e)
            try:
                await rpc.addnode(addr, "remove")
            except Exception as e:
                log.debug("addnode remove %s failed: %s", addr, e)

    await asyncio.gather(*[_disconnect_one(a) for a in addrs], return_exceptions=True)


async def run_invblock_prefilter(
    graph: GraphSnapshot,
    probe_0: AsyncBitcoinRpc,
    probe_1: AsyncBitcoinRpc,
    probe_0_log_path: str | Path,
    probe_1_log_path: str | Path,
    wait_time_sec: float = 5.0,
    test_tx: TxMessage | None = None,
    clear_logs: bool = True,
    progress_callback: Callable[[str, float], None] | None = None,
) -> InvblockResult:
    """Execute Step 2 INVBLOCK Pre-filtering across Probe 0 and Probe 1.

    Args:
        graph: Current GraphSnapshot (from Step 1 Groundtruth Capture).
        probe_0: AsyncBitcoinRpc client for Probe 0.
        probe_1: AsyncBitcoinRpc client for Probe 1.
        probe_0_log_path: Path to Probe 0's custom log file.
        probe_1_log_path: Path to Probe 1's custom log file.
        wait_time_sec: Seconds to wait after sending INVs for peers to respond.
        test_tx: Optional pre-crafted TxMessage; if None, crafts a fresh one.
        clear_logs: Whether to truncate probe log files before starting test.
        progress_callback: Optional callback(stage_name, progress_ratio).

    Returns:
        InvblockResult with pruned GraphSnapshot and detailed statistics.
    """
    initial_node_count = graph.num_nodes
    log.info("Starting Step 2 INVBLOCK Pre-filtering for %d nodes", initial_node_count)

    # 0. Truncate historical log files if requested
    if clear_logs:
        clear_log_file(probe_0_log_path)
        clear_log_file(probe_1_log_path)

    if progress_callback:
        progress_callback("Crafting test transaction", 0.05)

    # 1. Craft test transaction
    if test_tx is None:
        test_tx = await craft_test_transaction(probe_0)
    target_hashes = {test_tx.txid.lower(), test_tx.wtxid.lower()}
    log.info("Crafted test txid=%s wtxid=%s", test_tx.txid, test_tx.wtxid)

    # 2. Query peer info from Probe 0 and Probe 1 in parallel
    if progress_callback:
        progress_callback("Querying probe peer information", 0.10)
    p0_info, p1_info = await asyncio.gather(
        probe_0.getpeerinfo(),
        probe_1.getpeerinfo(),
    )

    # Build addr <-> peer_id mappings for eligible full-relay peers
    p0_addr_to_id: dict[str, int] = {}
    p0_id_to_addr: dict[int, str] = {}
    for p in p0_info:
        addr = p.get("addr", "")
        pid = p.get("id")
        conn_type = p.get("connection_type", "")
        if addr and pid is not None and not addr.startswith("127.0.0.1") and conn_type != "block-relay-only":
            p0_addr_to_id[addr] = pid
            p0_id_to_addr[pid] = addr

    p1_addr_to_id: dict[str, int] = {}
    p1_id_to_addr: dict[int, str] = {}
    for p in p1_info:
        addr = p.get("addr", "")
        pid = p.get("id")
        conn_type = p.get("connection_type", "")
        if addr and pid is not None and not addr.startswith("127.0.0.1") and conn_type != "block-relay-only":
            p1_addr_to_id[addr] = pid
            p1_id_to_addr[pid] = addr

    # Find mutual target nodes that exist in both probe peer lists and graph snapshot
    graph_addrs = {n.addr for n in graph.nodes}
    mutually_connected_nodes = [
        n for n in graph.nodes
        if n.addr in p0_addr_to_id and n.addr in p1_addr_to_id
    ]
    mutually_connected_count = len(mutually_connected_nodes)
    log.info(
        "Probe 0 active peers: %d, Probe 1 active peers: %d, Mutually connected target nodes: %d",
        len(p0_addr_to_id),
        len(p1_addr_to_id),
        mutually_connected_count,
    )

    # 3. Probe 0 sends INVBLOCK test
    if progress_callback:
        progress_callback("Probe 0 sending INVBLOCK test", 0.20)
    p0_target_ids = [p0_addr_to_id[n.addr] for n in mutually_connected_nodes]
    if p0_target_ids:
        await probe_0.sendinv_orphan([test_tx.hexstr], p0_target_ids)

    # 4. Wait for Probe 0 GETDATA responses
    if progress_callback:
        progress_callback("Waiting for Probe 0 GETDATA responses", 0.35)
    await asyncio.sleep(wait_time_sec)

    # 5. Parse Probe 0 log: identify responsive nodes (Filter 1)
    if progress_callback:
        progress_callback("Analyzing Probe 0 responsiveness", 0.50)
    p0_getdata_addrs = parse_getdata_peers_from_log(
        probe_0_log_path, target_hashes, p0_id_to_addr
    )

    p0_responsive_nodes: list[NodeIdentity] = []
    p0_nonresponsive_nodes: list[NodeIdentity] = []
    for n in mutually_connected_nodes:
        if n.addr in p0_getdata_addrs:
            p0_responsive_nodes.append(n)
        else:
            p0_nonresponsive_nodes.append(n)

    log.info(
        "Filter 1 Results (Probe 0): %d responsive, %d non-responsive (IBD/blocksonly/timeout)",
        len(p0_responsive_nodes),
        len(p0_nonresponsive_nodes),
    )

    # 6. Probe 1 sends INVBLOCK test to responsive peers
    if progress_callback:
        progress_callback("Probe 1 sending INVBLOCK test", 0.60)
    p1_target_ids = [p1_addr_to_id[n.addr] for n in p0_responsive_nodes]
    if p1_target_ids:
        await probe_1.sendinv_orphan([test_tx.hexstr], p1_target_ids)

    # 7. Wait for Probe 1 responses
    if progress_callback:
        progress_callback("Waiting for Probe 1 GETDATA responses", 0.75)
    await asyncio.sleep(wait_time_sec)

    # 8. Parse Probe 1 log: identify violating nodes (Filter 2)
    if progress_callback:
        progress_callback("Analyzing Probe 1 INVBLOCK compliance", 0.85)
    p1_getdata_addrs = parse_getdata_peers_from_log(
        probe_1_log_path, target_hashes, p1_id_to_addr
    )

    p1_violating_nodes: list[NodeIdentity] = []
    qualified_nodes: list[NodeIdentity] = []
    for n in p0_responsive_nodes:
        if n.addr in p1_getdata_addrs:
            p1_violating_nodes.append(n)
        else:
            qualified_nodes.append(n)

    log.info(
        "Filter 2 Results (Probe 1): %d compliant, %d violating (duplicate GETDATA sent)",
        len(qualified_nodes),
        len(p1_violating_nodes),
    )

    # Also determine any graph nodes that dropped prior to or during the test
    dropped_nodes = [
        n for n in graph.nodes
        if n.addr not in p0_addr_to_id or n.addr not in p1_addr_to_id
    ]

    all_eliminated_nodes_set = (
        {n.addr for n in p0_nonresponsive_nodes}
        | {n.addr for n in p1_violating_nodes}
        | {n.addr for n in dropped_nodes}
    )

    # 9. Disconnect all eliminated peers in parallel from both Probe 0 and Probe 1
    if progress_callback:
        progress_callback("Disconnecting eliminated peers from probes", 0.90)
    await asyncio.gather(
        disconnect_peers_parallel(probe_0, all_eliminated_nodes_set),
        disconnect_peers_parallel(probe_1, all_eliminated_nodes_set),
    )

    # 10. Clear tracked probe transaction memory on both probes
    if progress_callback:
        progress_callback("Clearing probe transaction state", 0.95)
    await asyncio.gather(
        probe_0.clearinv_probe(),
        probe_1.clearinv_probe(),
    )

    # 11. Prune graph snapshot
    final_snapshot = graph.prune_nodes(qualified_nodes)
    if progress_callback:
        progress_callback("Completed INVBLOCK pre-filtering", 1.0)

    stats = InvblockStats(
        total_initial_nodes=initial_node_count,
        probe_0_active_peers=len(p0_addr_to_id),
        probe_1_active_peers=len(p1_addr_to_id),
        mutually_connected_count=mutually_connected_count,
        probe_0_responsive_count=len(p0_responsive_nodes),
        probe_0_nonresponsive_count=len(p0_nonresponsive_nodes),
        probe_1_violating_count=len(p1_violating_nodes),
        eliminated_count=len(all_eliminated_nodes_set),
        remaining_qualified_count=final_snapshot.num_nodes,
        remaining_edges_count=final_snapshot.num_edges,
    )

    log.info(
        "INVBLOCK Filter finished: %d -> %d nodes (%d eliminated: %d non-responsive, %d violating, %d dropped), %d edges remaining",
        initial_node_count,
        final_snapshot.num_nodes,
        len(all_eliminated_nodes_set),
        len(p0_nonresponsive_nodes),
        len(p1_violating_nodes),
        len(dropped_nodes),
        final_snapshot.num_edges,
    )

    return InvblockResult(
        snapshot=final_snapshot,
        eliminated_nonresponsive=tuple(p0_nonresponsive_nodes),
        eliminated_violating=tuple(p1_violating_nodes),
        stats=stats,
    )
