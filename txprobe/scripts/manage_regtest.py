#!/usr/bin/env python3
"""RegTest Network Manager for Bitcoin TxProbe Experiments.

Provides automated provisioning, startup, topology construction, funding,
and teardown for multi-node RegTest environments (e.g. 100 target nodes + 2 probe nodes).

Usage:
    # 1. Initialize data directories and generate config/regtest.yaml:
    python scripts/manage_regtest.py init --num-nodes 100

    # 2. Start all nodes:
    python scripts/manage_regtest.py start

    # 3. Build target graph topology and connect probes:
    python scripts/manage_regtest.py build-topology --degree 8

    # 4. Mine 101 blocks on Probe 0 to provide UTXO funding:
    python scripts/manage_regtest.py fund-probes

    # 5. Check network status:
    python scripts/manage_regtest.py status

    # 6. Stop all regtest nodes:
    python scripts/manage_regtest.py stop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

import yaml

# Allow running directly from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from txprobe.rpc.client import AsyncBitcoinRpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("txprobe.regtest")

DEFAULT_BASE_DIR = Path("/mnt/ssd/hdhphat-mindfullab/regtest-node-data")
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "regtest.yaml"
BITCOIND_CUSTOM = Path("/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/build/bin/bitcoind")
BITCOIND_OFFICIAL = Path("/mnt/ssd/hdhphat-mindfullab/bitcoin-31.1/bin/bitcoind")

BASE_P2P_PORT = 18444
BASE_RPC_PORT = 19444


def get_ports(node_id: int, base_p2p: int = BASE_P2P_PORT, base_rpc: int = BASE_RPC_PORT) -> tuple[int, int]:
    """Return (p2p_port, rpc_port) for a given node ID."""
    return base_p2p + node_id, base_rpc + node_id


def init_network(
    num_target_nodes: int = 100,
    base_dir: Path = DEFAULT_BASE_DIR,
    config_path: Path = DEFAULT_CONFIG_PATH,
    base_p2p_port: int = BASE_P2P_PORT,
    base_rpc_port: int = BASE_RPC_PORT,
) -> None:
    """Create data directories, configuration files, and YAML experiment config."""
    total_nodes = num_target_nodes + 2  # 2 probes (0, 1) + target nodes (2..num_target_nodes+1)
    log.info("Initializing RegTest network with %d total nodes (2 probes + %d targets)...", total_nodes, num_target_nodes)
    base_dir.mkdir(parents=True, exist_ok=True)

    yaml_nodes = []

    for i in range(total_nodes):
        node_dir = base_dir / f"bitcoin-{i}"
        node_dir.mkdir(parents=True, exist_ok=True)

        p2p_port, rpc_port = get_ports(i, base_p2p_port, base_rpc_port)
        rpc_user = f"regtestuser{i}"
        rpc_pass = f"regtestpassword{i}"
        role = "probe" if i < 2 else "groundtruth"

        # Generate bitcoin.conf
        conf_lines = [
            f"datadir={node_dir}",
            "chain=regtest",
            "server=1",
            "listen=1",
            "",
            "[regtest]",
            "discover=0",
            f"bind=127.0.0.1:{p2p_port}",
            f"port={p2p_port}",
            f"rpcport={rpc_port}",
            f"rpcuser={rpc_user}",
            f"rpcpassword={rpc_pass}",
            "rpcallowip=127.0.0.1",
            "fallbackfee=0.0001",
            "txindex=1",
            f"maxconnections={1250 if i < 2 else 250}",
        ]

        if i < 2:
            log_file = node_dir / f"txprobe_{i}.log"
            conf_lines.append(f"txprobelogfile={log_file}")

        conf_file = node_dir / "bitcoin.conf"
        conf_file.write_text("\n".join(conf_lines) + "\n", encoding="utf-8")

        node_dict: dict[str, Any] = {
            "id": i,
            "role": role,
            "rpcport": rpc_port,
            "rpcuser": rpc_user,
            "rpcpassword": rpc_pass,
            "p2pport": p2p_port,
        }
        if i == 0:
            node_dict["wallet"] = "mywallet"
            node_dict["txprobe_log_file"] = str(node_dir / "txprobe_0.log")
        elif i == 1:
            node_dict["txprobe_log_file"] = str(node_dir / "txprobe_1.log")

        yaml_nodes.append(node_dict)

    # Generate config/regtest.yaml
    yaml_config = {
        "network": "regtest",
        "default_port": base_p2p_port,
        "allow_localhost": True,
        "results_dir": "results-regtest",
        "nodes": yaml_nodes,
        "discovery": {
            "target_count": 0,
            "crawling_time_sec": 60.0,
            "poll_interval_sec": 3.0,
            "retry_interval_sec": 15.0,
            "clearnet_onetry_concurrency": 50,
            "tor_onetry_concurrency": 0,
            "max_addrman_age_days": 0.0,
        },
        "reachability": {
            "tor_proxy_host": "127.0.0.1",
            "tor_proxy_port": 9050,
            "clearnet_timeout_sec": 5.0,
            "tor_timeout_sec": 10.0,
            "clearnet_concurrency": 50,
            "tor_concurrency": 0,
        },
        "dns_seeds": [],
        "invblock": {
            "wait_time_sec": 3.0,
        },
        "tx_crafting": {
            "utxo_target_sats": 2000,
            "parent_fee_sats": 500,
            "marker_fee_sats": 500,
            "split_fee_rate_sat_vb": 2,
            "max_outputs_per_split_tx": 500,
            "max_source_size": 75,
            "poll_interval_sec": 3.0,
            "block_propagation_wait_sec": 3.0,
        },
        "txprobe_execution": {
            "invblock_wait_sec": 4.0,
            "flood_wait_sec": 0.5,
            "parent_wait_sec": 2.0,
            "marker_propagation_wait_sec": 7.5,
            "getdata_wait_sec": 6.0,
            "cleanup_wait_sec": 1.0,
        },
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_config, f, sort_keys=False, indent=2)

    log.info("Initialized %d node directories in %s", total_nodes, base_dir)
    log.info("Saved YAML configuration to %s", config_path)


def start_nodes(base_dir: Path = DEFAULT_BASE_DIR, start_id: int = 0, end_id: int | None = None) -> None:
    """Launch bitcoind instances in background."""
    node_dirs = sorted(base_dir.glob("bitcoin-*"), key=lambda p: int(p.name.split("-")[1]))
    if not node_dirs:
        log.error("No node directories found in %s. Run init first.", base_dir)
        sys.exit(1)

    if end_id is None:
        target_dirs = [d for d in node_dirs if int(d.name.split("-")[1]) >= start_id]
    else:
        target_dirs = [d for d in node_dirs if start_id <= int(d.name.split("-")[1]) <= end_id]

    log.info("Starting %d nodes from %s...", len(target_dirs), base_dir)

    for node_dir in target_dirs:
        node_id = int(node_dir.name.split("-")[1])
        conf_file = node_dir / "bitcoin.conf"
        binary = BITCOIND_CUSTOM if node_id < 2 else (BITCOIND_OFFICIAL if BITCOIND_OFFICIAL.exists() else BITCOIND_CUSTOM)

        extra_args = []
        if node_id < 2:
            extra_args.append(f"-txprobelogfile={node_dir / f'txprobe_{node_id}.log'}")

        cmd = [
            str(binary),
            f"-datadir={node_dir}",
            f"-conf={conf_file}",
            "-daemon",
            "-rpcthreads=16",
            "-rpcworkqueue=64",
            "-dbcache=20",
            "-maxmempool=20",
            *extra_args,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    log.info("Launched %d nodes. Waiting for RPC ready...", len(target_dirs))
    asyncio.run(wait_for_rpc_ready(target_dirs))


async def wait_for_rpc_ready(target_dirs: list[Path], timeout_sec: float = 60.0) -> None:
    """Wait until all started nodes respond to RPC."""
    t0 = time.monotonic()
    pending = list(target_dirs)

    async def _check_one(d: Path) -> Path | None:
        nid = int(d.name.split("-")[1])
        _, rpc = get_ports(nid)
        try:
            async with AsyncBitcoinRpc("127.0.0.1", rpc, f"regtestuser{nid}", f"regtestpassword{nid}", timeout_sec=0.5) as client:
                await client.getnetworkinfo()
                return d
        except Exception:
            return None

    while pending and (time.monotonic() - t0) < timeout_sec:
        results = await asyncio.gather(*[_check_one(d) for d in pending])
        ready = [d for d in results if d is not None]
        for d in ready:
            pending.remove(d)
        if pending:
            await asyncio.sleep(0.5)

    if pending:
        log.warning("Timeout waiting for %d nodes to become RPC-ready: %s", len(pending), [d.name for d in pending])
    else:
        log.info("All nodes are online and RPC-responsive!")


def stop_nodes(base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """Stop all running regtest nodes in base_dir."""
    node_dirs = sorted(base_dir.glob("bitcoin-*"), key=lambda p: int(p.name.split("-")[1]))
    if not node_dirs:
        log.info("No nodes found in %s.", base_dir)
        return

    log.info("Stopping %d regtest nodes...", len(node_dirs))

    async def _stop_node(d: Path) -> None:
        nid = int(d.name.split("-")[1])
        _, rpc = get_ports(nid)
        try:
            async with AsyncBitcoinRpc("127.0.0.1", rpc, f"regtestuser{nid}", f"regtestpassword{nid}", timeout_sec=2.0) as client:
                await client.call("stop")
        except Exception:
            pass

    async def _stop_all() -> None:
        await asyncio.gather(*[_stop_node(d) for d in node_dirs])

    asyncio.run(_stop_all())
    log.info("Stop signals sent. Waiting for shutdown...")
    time.sleep(2)


def build_topology(
    num_target_nodes: int = 100,
    degree: int = 8,
    base_dir: Path = DEFAULT_BASE_DIR,
    graph_out: Path | None = None,
) -> None:
    """Construct an undirected k-regular / random connected graph on target nodes (2..N+1) and connect probes."""
    total_targets = num_target_nodes
    target_ids = list(range(2, 2 + total_targets))

    log.info("Generating connected random graph with target degree ~%d for %d nodes...", degree, total_targets)

    # Build connected graph: create spanning tree first, then add edges up to degree
    adj: dict[int, set[int]] = {i: set() for i in target_ids}

    # 1. Spanning tree to ensure full network connectivity
    shuffled = list(target_ids)
    random.shuffle(shuffled)
    connected_nodes = [shuffled[0]]
    for node in shuffled[1:]:
        parent = random.choice(connected_nodes)
        adj[node].add(parent)
        adj[parent].add(node)
        connected_nodes.append(node)

    # 2. Add random edges until each node has approximately degree edges
    all_pairs = [(u, v) for i, u in enumerate(target_ids) for v in target_ids[i + 1:]]
    random.shuffle(all_pairs)

    for u, v in all_pairs:
        if v not in adj[u] and len(adj[u]) < degree and len(adj[v]) < degree:
            adj[u].add(v)
            adj[v].add(u)

    total_edges = sum(len(neighbors) for neighbors in adj.values()) // 2
    log.info("Generated graph topology with %d target nodes and %d undirected edges.", len(target_ids), total_edges)

    if graph_out is None:
        graph_out = base_dir / "groundtruth_topology.json"
    graph_data = {
        "num_nodes": len(target_ids),
        "num_edges": total_edges,
        "adjacency": {str(u): sorted(list(neighbors)) for u, neighbors in sorted(adj.items())},
    }
    graph_out.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")
    log.info("Saved ground truth topology graph to %s", graph_out)

    # 3. Connect nodes via RPC addnode
    async def _connect_graph() -> None:
        log.info("Connecting inter-target node edges via RPC addnode...")
        tasks = []
        for u, neighbors in adj.items():
            _, rpc_u = get_ports(u)
            user_u = f"regtestuser{u}"
            pass_u = f"regtestpassword{u}"

            async def _connect_one_node(node_id: int, rpc_port: int, user: str, passwd: str, peers: set[int]) -> None:
                async with AsyncBitcoinRpc("127.0.0.1", rpc_port, user, passwd) as client:
                    for v in peers:
                        p2p_v, _ = get_ports(v)
                        try:
                            await client.addnode(f"127.0.0.1:{p2p_v}", "add")
                        except Exception as e:
                            log.warning("Failed addnode %d -> %d: %s", node_id, v, e)

            tasks.append(_connect_one_node(u, rpc_u, user_u, pass_u, neighbors))
        await asyncio.gather(*tasks)

        # 4. Connect Probe 0 and Probe 1 to ALL target nodes
        log.info("Connecting Probe 0 and Probe 1 to all %d target nodes...", len(target_ids))
        for probe_id in (0, 1):
            _, rpc_p = get_ports(probe_id)
            user_p = f"regtestuser{probe_id}"
            pass_p = f"regtestpassword{probe_id}"
            async with AsyncBitcoinRpc("127.0.0.1", rpc_p, user_p, pass_p) as probe_rpc:
                for target_id in target_ids:
                    p2p_t, _ = get_ports(target_id)
                    try:
                        await probe_rpc.addnode(f"127.0.0.1:{p2p_t}", "add")
                    except Exception as e:
                        log.warning("Probe %d addnode to %d failed: %s", probe_id, target_id, e)

    asyncio.run(_connect_graph())
    log.info("Topology construction completed successfully! Waiting 5s for P2P connections to establish...")
    time.sleep(5)


def fund_probes(num_blocks: int = 250) -> None:
    """Mine blocks on Probe 0 to provide spendable UTXO funding for TxProbe (coinbase maturity requires >= 100 blocks)."""
    _, rpc_0 = get_ports(0)
    user_0 = "regtestuser0"
    pass_0 = "regtestpassword0"

    async def _fund() -> None:
        log.info("Funding Probe 0 via local block generation (%d blocks)...", num_blocks)
        async with AsyncBitcoinRpc("127.0.0.1", rpc_0, user_0, pass_0) as client:
            # Create wallet if missing
            wallets = await client.listwallets()
            if "mywallet" not in wallets:
                try:
                    await client.createwallet("mywallet")
                except Exception:
                    pass

        # Use wallet RPC
        async with AsyncBitcoinRpc("127.0.0.1", rpc_0, user_0, pass_0, wallet="mywallet") as w_client:
            mining_addr = await w_client.getnewaddress("mining")
            log.info("Mining %d blocks to address: %s", num_blocks, mining_addr)
            blocks = await w_client.generatetoaddress(num_blocks, mining_addr)
            mature_count = max(0, len(blocks) - 100)
            log.info("Mined %d blocks! Probe 0 now has %d mature block reward UTXOs.", len(blocks), mature_count)
            bal = await w_client.getbalance()
            log.info("Probe 0 wallet balance: %s BTC", bal)

    asyncio.run(_fund())
    log.info("Waiting 3s for block propagation across all connected nodes...")
    time.sleep(3)


def check_status(base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """Check running status, block height, and peer counts across all nodes."""
    node_dirs = sorted(base_dir.glob("bitcoin-*"), key=lambda p: int(p.name.split("-")[1]))
    if not node_dirs:
        log.info("No nodes found in %s.", base_dir)
        return

    async def _check_all() -> None:
        online = 0
        total = len(node_dirs)

        async def _check_one(d: Path) -> dict[str, Any]:
            nid = int(d.name.split("-")[1])
            p2p, rpc = get_ports(nid)
            user = f"regtestuser{nid}"
            passwd = f"regtestpassword{nid}"
            try:
                async with AsyncBitcoinRpc("127.0.0.1", rpc, user, passwd, timeout_sec=2.0) as client:
                    b_count = await client.getblockcount()
                    peers = await client.getpeerinfo()
                    return {"id": nid, "status": "ONLINE", "blocks": b_count, "peers": len(peers)}
            except Exception:
                return {"id": nid, "status": "OFFLINE", "blocks": 0, "peers": 0}

        results = await asyncio.gather(*[_check_one(d) for d in node_dirs])
        online_count = sum(1 for r in results if r["status"] == "ONLINE")

        print("\n" + "=" * 65)
        print(f"       RegTest Cluster Status: {online_count}/{total} nodes ONLINE")
        print("=" * 65)
        for r in results[:10]:
            print(f" Node {r['id']:3d} | Status: {r['status']:7s} | Blocks: {r['blocks']:4d} | Peers: {r['peers']:3d}")
        if len(results) > 10:
            print(f" ... ({len(results) - 10} more nodes) ...")
            last = results[-1]
            print(f" Node {last['id']:3d} | Status: {last['status']:7s} | Blocks: {last['blocks']:4d} | Peers: {last['peers']:3d}")
        print("=" * 65 + "\n")

    asyncio.run(_check_all())


def main() -> None:
    parser = argparse.ArgumentParser(description="RegTest Network Manager for TxProbe")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_p = subparsers.add_parser("init", help="Initialize node directories and configuration")
    init_p.add_argument("--num-nodes", type=int, default=100, help="Number of target groundtruth nodes (default: 100)")
    init_p.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR, help="Base directory for nodes")
    init_p.add_argument("--config-out", type=Path, default=DEFAULT_CONFIG_PATH, help="Path for output YAML config")

    start_p = subparsers.add_parser("start", help="Start all bitcoind instances")
    start_p.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR, help="Base directory for nodes")
    start_p.add_argument("--start-id", type=int, default=0, help="First node ID to start")
    start_p.add_argument("--end-id", type=int, default=None, help="Last node ID to start")

    stop_p = subparsers.add_parser("stop", help="Stop all bitcoind instances")
    stop_p.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR, help="Base directory for nodes")

    topo_p = subparsers.add_parser("build-topology", help="Connect target nodes and probes into a graph")
    topo_p.add_argument("--num-nodes", type=int, default=100, help="Number of target groundtruth nodes")
    topo_p.add_argument("--degree", type=int, default=8, help="Target average degree (default: 8)")
    topo_p.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR, help="Base directory for nodes")

    fund_p = subparsers.add_parser("fund-probes", help="Mine blocks on Probe 0 to create spendable UTXOs")
    fund_p.add_argument("--blocks", type=int, default=250, help="Number of blocks to mine (default: 250, maturity requires >100)")
    subparsers.add_parser("status", help="Display cluster health and peer counts")

    args = parser.parse_args()

    if args.command == "init":
        init_network(
            num_target_nodes=args.num_nodes,
            base_dir=args.base_dir,
            config_path=args.config_out,
        )
    elif args.command == "start":
        start_nodes(base_dir=args.base_dir, start_id=args.start_id, end_id=args.end_id)
    elif args.command == "stop":
        stop_nodes(base_dir=args.base_dir)
    elif args.command == "build-topology":
        build_topology(num_target_nodes=args.num_nodes, degree=args.degree, base_dir=args.base_dir)
    elif args.command == "fund-probes":
        fund_probes(num_blocks=args.blocks)
    elif args.command == "status":
        check_status(base_dir=getattr(args, "base_dir", DEFAULT_BASE_DIR))


if __name__ == "__main__":
    main()
