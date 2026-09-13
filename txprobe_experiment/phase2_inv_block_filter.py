"""Validation Test Mode Phase 2: INVBLOCK filter.

Establishes the persistent node 0 / node 6 filter links to every node in
S_groundtruth_before, announces a single probe transaction twice (node 0 then
node 6), and reports which targets could not be INVBLOCKed.
"""

import json
import re
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

from .address import (
    endpoint_tuple_to_str,
    endpoint_str_to_tuple,
)
from .classes.BitcoinCli.BitcoinCli import BitcoinCli, nodes_cli
from .groundtruth import (
    EXCLUDED_CONNECTION_TYPES,
    GroundTruthSnapshot,
    NodeIdentity,
    TRACKED_NODE_IDS,
    _identity_sort_key,
)


GETDATA_PATTERN = re.compile(r"received getdata for: \S+ ([0-9a-f]{64}) peer=(\d+)")


class Phase2Error(RuntimeError):
    """Phase 2 cannot proceed as the specification requires."""


@dataclass(frozen=True)
class Phase2Result:
    """Everything Phase 2 measured or established for the later phases."""

    target_addrs: Mapping[NodeIdentity, str]
    node0_peer_ids: Mapping[NodeIdentity, int]
    node6_peer_ids: Mapping[NodeIdentity, int]
    itx_hex: str
    itx_txid: str
    itx_wtxid: str
    no_invblock_nodes: Tuple[NodeIdentity, ...]
    snapshot: GroundTruthSnapshot

    def as_dict(self):
        return {
            "target_addrs": {str(k): v for k, v in self.target_addrs.items()},
            "node0_peer_ids": {str(k): v for k, v in self.node0_peer_ids.items()},
            "node6_peer_ids": {str(k): v for k, v in self.node6_peer_ids.items()},
            "itx_hex": self.itx_hex,
            "itx_txid": self.itx_txid,
            "itx_wtxid": self.itx_wtxid,
            "no_invblock_nodes": list(self.no_invblock_nodes),
            "snapshot": self.snapshot.as_dict(),
        }


def build_target_addresses(
    snapshot: GroundTruthSnapshot,
    network_info_by_node: Mapping[int, Mapping],
) -> Dict[NodeIdentity, str]:
    """Map every S_groundtruth_before identity to the exact Phase 1 ``addr``.

    Configured nodes advertise ``getnetworkinfo.localaddresses[0]``; external
    peers already carry their normalized ``host:port`` endpoint as identity.
    """

    target_addrs: Dict[NodeIdentity, str] = {}
    for identity in snapshot.nodes:
        if isinstance(identity, int):
            network_info = network_info_by_node.get(identity)
            if not isinstance(network_info, Mapping):
                raise Phase2Error(f"Node {identity}: getnetworkinfo response is unavailable.")
            local_addresses = network_info.get("localaddresses")
            if not isinstance(local_addresses, Sequence) or isinstance(local_addresses, (str, bytes)):
                raise Phase2Error(f"Node {identity}: getnetworkinfo.localaddresses is unavailable.")
            if not local_addresses or not isinstance(local_addresses[0], Mapping):
                raise Phase2Error(f"Node {identity}: getnetworkinfo.localaddresses[0] is unavailable.")
            host = local_addresses[0].get("address")
            port = local_addresses[0].get("port")
            if not isinstance(host, str) or not host:
                raise Phase2Error(f"Node {identity}: getnetworkinfo.localaddresses[0].address is unavailable.")
            if not isinstance(port, int):
                port = None
            target_addrs[identity] = endpoint_tuple_to_str((host.lower(), port))
        else:
            target_addrs[identity] = identity
    return target_addrs


def plan_cleanup(
    target_addrs: Mapping[NodeIdentity, str],
    added_addrs: Iterable[str],
    active_peer_addrs: Iterable[str],
):
    """Compute the cleanup actions for one instrumentation node.

    Returns ``(to_remove, to_disconnect, to_add)``:
    - ``addednode ... remove`` for every addnode entry not a target,
    - ``disconnectnode`` for every active peer not a target,
    - ``addnode ... add`` for every target missing from the addnode list.
    """

    target_set = set(target_addrs.values())
    to_remove = sorted(addr for addr in added_addrs if addr not in target_set)
    to_disconnect = sorted(addr for addr in active_peer_addrs if addr not in target_set)
    to_add = sorted(
        addr for addr in target_addrs.values() if addr not in set(added_addrs)
    )
    return to_remove, to_disconnect, to_add


def cleanup_and_connect(node_cli: BitcoinCli, target_addrs: Mapping[NodeIdentity, str], debug: bool = False):
    """Bring an instrumentation node to a clean, persistent link state."""

    added_addrs = [item.get("addednode") for item in node_cli.cli_json("getaddednodeinfo")]
    active_peer_addrs = [peer.get("addr", "") for peer in node_cli.cli_json("getpeerinfo")]

    to_remove, to_disconnect, to_add = plan_cleanup(target_addrs, added_addrs, active_peer_addrs)

    if debug:
        print(f"Node {node_cli.id}: removing {to_remove}, disconnecting {to_disconnect}, adding {to_add}", file=sys.stderr)

    for addr in to_remove:
        node_cli.cli_raw("addnode", addr, "remove", ignore=True)

    node_cli.delete_peers(to_disconnect, True, debug)
    node_cli.add_peers(to_add, True, debug)

    if debug:
        print(f'Cleanup_and_connect done.')


def _match_connected(
    target_by_endpoint: Mapping[Tuple[str, Optional[int]], NodeIdentity],
    peers: Sequence[Mapping],
) -> Dict[NodeIdentity, int]:
    """Return ``{identity: peer_id}`` for qualifying full-relay peer entries."""

    connected: Dict[NodeIdentity, int] = {}
    for peer in peers:
        if peer.get("connection_type") in EXCLUDED_CONNECTION_TYPES:
            continue
        addr = peer.get("addr", "")
        identity = target_by_endpoint.get(endpoint_str_to_tuple(addr))
        if identity is not None and identity not in connected:
            connected[identity] = peer["id"]
    return connected


def poll_full_relay_links(
    node_cli: BitcoinCli,
    target_addrs: Mapping[NodeIdentity, str],
    timeout: int = 30,
    hard_timeout: int = 240,
    interval: int = 2,
    debug: bool = False,
) -> Dict[NodeIdentity, int]:
    """Wait until the node has a qualifying full-relay link to every target.

    On each polling timeout, print ``timeout`` and reset the elapsed counter,
    continuing indefinitely (per the specification).
    """

    target_by_endpoint = {endpoint_str_to_tuple(addr): identity for identity, addr in target_addrs.items()}
    elapsed = 0
    hard_elapsed = 0
    while hard_elapsed < hard_timeout:
        while elapsed < timeout:
            peers = node_cli.cli_json("getpeerinfo")
            connected = _match_connected(target_by_endpoint, peers)
            if len(connected) == len(target_addrs):
                return connected
            time.sleep(interval)
            elapsed += interval
            hard_elapsed += interval
        print(f"Phase 2 polling: Node {node_cli.id} waits to connect to target nodes timeout.\n"
              f"Currently connected to {len(connected)} out of {len(target_addrs)}", file=sys.stderr)
        elapsed = 0
        if hard_elapsed >= hard_timeout:
            print(f"Phase 2 polling: Hard timeout limit reached, skip the cannot connecting nodes,"
                f"Those nodes are considered transient.")
            c = input("Halt (h)?").lower()
            if c == 'h':
                return connected
            else:
                hard_elapsed = 0

def create_itx() -> Tuple[str, str, str]:
    """Node 0 creates one signed probe transaction ``itx`` (not broadcast)."""

    nodes_cli[0].ensure_wallet("mywallet")
    txid, vout, amount_btc = nodes_cli[0].get_utxo()
    final_addr = nodes_cli[0].get_own_address("mywallet")
    amount_sats = int(amount_btc * Decimal(100_000_000))
    out_btc = (amount_sats - 1000) / 1e8

    unsigned_hex = nodes_cli[0].cli_raw(
        "createrawtransaction",
        json.dumps([{"txid": txid, "vout": vout}]),
        json.dumps({final_addr: out_btc}),
    )
    signed = nodes_cli[0].cli_json("signrawtransactionwithwallet", unsigned_hex)
    if not signed.get("complete"):
        raise Phase2Error("Failed to sign the Phase 2 probe transaction itx.")
    decoded = nodes_cli[0].cli_json("decoderawtransaction", signed["hex"])
    txid_new = decoded["txid"]
    wtxid = decoded.get("hash", txid_new)
    return signed["hex"], txid_new, wtxid


def announce_inv(node_cli: BitcoinCli, tx_hex: str, peer_ids: Iterable[int], debug: bool = False):
    """Send an ``INV`` announcement for one transaction to the given peers."""

    if debug:
        print(f"Node {node_cli.id}: announcing INV to peers {list(peer_ids)}", file=sys.stderr)
    node_cli.cli_json("sendinv_orphan", json.dumps([tx_hex]), json.dumps(list(peer_ids)))

def collect_no_invblock_peers(
    log_path: str,
    probe_hashes: Iterable[str],
    peer_id_to_identity: Mapping[int, NodeIdentity],
) -> Tuple[NodeIdentity, ...]:
    """Read a node's txprobe log and return the targets that sent getdata."""

    probe_set = set(probe_hashes)
    failures = set()
    try:
        with open(log_path) as log_file:
            for line in log_file:
                match = GETDATA_PATTERN.search(line)
                if not match:
                    continue
                log_hash = match.group(1)
                log_peer = int(match.group(2))
                if log_hash in probe_set and log_peer in peer_id_to_identity:
                    failures.add(peer_id_to_identity[log_peer])
    except FileNotFoundError:
        pass
    return tuple(sorted(failures, key=_identity_sort_key))


def no_invblock_filter(
    snapshot: GroundTruthSnapshot,
    network_info_by_node: Optional[Mapping[int, Mapping]] = None,
    debug: bool = False,
    inv_delay: float = 30,
    settle_delay: float = 15,
    poll_timeout: int = 30,
    poll_interval: int = 2,
    node0_log: str = "txprobe_0.log",
    node6_log: str = "txprobe_6.log",
) -> Phase2Result:
    """Execute the full Phase 2 workflow and return its measurements."""

    if network_info_by_node is None:
        network_info_by_node = {
            node_id: nodes_cli[node_id].cli_json("getnetworkinfo")
            for node_id in TRACKED_NODE_IDS
        }
    target_addrs = build_target_addresses(snapshot, network_info_by_node)

    for node_cli in (nodes_cli[0], nodes_cli[6]):
        cleanup_and_connect(node_cli, target_addrs, debug)

    node0_peer_ids = poll_full_relay_links(nodes_cli[0], target_addrs, poll_timeout, poll_interval, debug)
    node6_peer_ids = poll_full_relay_links(nodes_cli[6], target_addrs, poll_timeout, poll_interval, debug)

    itx_hex, itx_txid, itx_wtxid = create_itx()

    announce_inv(nodes_cli[0], itx_hex, node0_peer_ids.values(), debug)
    time.sleep(inv_delay)
    announce_inv(nodes_cli[6], itx_hex, node6_peer_ids.values(), debug)
    time.sleep(settle_delay)

    peer6_to_identity = {peer_id: identity for identity, peer_id in node6_peer_ids.items()}
    no_invblock = collect_no_invblock_peers(node6_log, {itx_txid, itx_wtxid}, peer6_to_identity)

    addr_no_invblock_nodes = [nodes_cli[identity].get_localaddress() if isinstance(identity, int) else identity for identity in no_invblock]
    nodes_cli[0].delete_peers(addr_no_invblock_nodes, wait = True, debug = debug)
    nodes_cli[6].delete_peers(addr_no_invblock_nodes, wait = True, debug = debug)

    cannot_connect_node6 = [identity for identity, addr in target_addrs.items() if identity not in node6_peer_ids]
    addr_cannot_connect_node6 = [nodes_cli[identity].get_localaddress() if isinstance(identity, int) else identity for identity in cannot_connect_node6]
    nodes_cli[0].delete_peers(addr_cannot_connect_node6, wait = True, debug = debug)

    snapshot = snapshot.remove_nodes(list(no_invblock))
    snapshot = snapshot.remove_nodes(cannot_connect_node6)

    result = Phase2Result(
        target_addrs=target_addrs,
        node0_peer_ids=node0_peer_ids,
        node6_peer_ids=node6_peer_ids,
        itx_hex=itx_hex,
        itx_txid=itx_txid,
        itx_wtxid=itx_wtxid,
        no_invblock_nodes=no_invblock,
        snapshot=snapshot
    )

    if debug:
        print(result.__str__())

    return result