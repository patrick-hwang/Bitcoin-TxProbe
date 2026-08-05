"""Read the real experiment topology for Validation Test Mode Phase 1.

This module deliberately does not add, remove, or disconnect any peers. The
older random-topology experiment remains separate; Validation Test Mode needs
an observed ground truth that includes connectable external peers.
"""

from dataclasses import dataclass
import ipaddress
import json
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple, Union

from .cli import nodes_cli


TRACKED_NODE_IDS = (1, 2, 3, 4, 5)
EXCLUDED_NODE_IDS = frozenset((0, 6))
NodeIdentity = Union[int, str]


class GroundTruthError(RuntimeError):
    """The peer data cannot be mapped unambiguously to experiment nodes."""


@dataclass(frozen=True)
class GroundTruthSnapshot:
    """The observed Phase 1 topology.

    Integer identities represent configured experiment nodes. A string identity
    represents an external peer's normalized ``addr`` endpoint. ``gt_edges``
    intentionally contains both directed pairs for every observed connection.
    """

    nodes: Tuple[NodeIdentity, ...]
    peers: Mapping[int, Tuple[NodeIdentity, ...]]
    gt_edges: Tuple[Tuple[NodeIdentity, NodeIdentity], ...]

    def as_dict(self):
        return {
            "nodes": list(self.nodes),
            "peers": {str(node_id): list(peers) for node_id, peers in sorted(self.peers.items())},
            "gt_edges": [list(edge) for edge in self.gt_edges],
        }


def _endpoint(address: str) -> Tuple[str, Optional[int]]:
    """Return a normalized ``(host, port)`` pair for a Bitcoin peer address."""

    address = address.strip()
    if address.startswith("["):
        closing = address.find("]")
        if closing != -1:
            host = address[1:closing]
            rest = address[closing + 1:]
            if rest.startswith(":") and rest[1:].isdigit():
                return host.lower(), int(rest[1:])
            return host.lower(), None

    host, separator, port = address.rpartition(":")
    if separator and host and port.isdigit():
        return host.lower(), int(port)
    return address.lower(), None


def _normalized_endpoint(address: str) -> str:
    """Create the stable external-peer identity required by the specification."""

    host, port = _endpoint(address)
    if ":" in host:
        return f"[{host}]:{port}" if port is not None else f"[{host}]"
    return f"{host}:{port}" if port is not None else host


def _is_unconnectable_external_peer(address: str) -> bool:
    """Whether ``addr`` is localhost or IPv6, both excluded by Phase 1."""

    host, _ = _endpoint(address)
    if host == "127.0.0.1":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).version == 6
    except ValueError:
        return False


def _build_address_index(
    network_info_by_node: Mapping[int, Mapping], required_node_ids: Iterable[int]
):
    """Index exactly ``localaddresses[0]`` for every supplied node.

    Nodes tracked by Phase 1 (normally 1--5) must provide their first local
    address. Nodes 0 and 6 are excluded from Phase 1 and are indexed only when
    they provide that address; their lack of one must not prevent a snapshot.
    """

    endpoint_to_node: Dict[Tuple[str, Optional[int]], int] = {}
    host_to_nodes: Dict[str, Set[int]] = {}
    required = set(required_node_ids)

    for node_id in sorted(set(network_info_by_node) | required):
        network_info = network_info_by_node.get(node_id)
        is_required = node_id in required
        if not isinstance(network_info, Mapping):
            if is_required:
                raise GroundTruthError(f"Node {node_id}: getnetworkinfo response is unavailable.")
            continue

        local_addresses = network_info.get("localaddresses")
        if not isinstance(local_addresses, Sequence) or isinstance(local_addresses, (str, bytes)):
            if is_required:
                raise GroundTruthError(
                    f"Node {node_id}: getnetworkinfo.localaddresses[0] is unavailable."
                )
            continue
        if not local_addresses or not isinstance(local_addresses[0], Mapping):
            if is_required:
                raise GroundTruthError(
                    f"Node {node_id}: getnetworkinfo.localaddresses[0] is unavailable."
                )
            continue

        local_address = local_addresses[0]
        host = local_address.get("address")
        if not isinstance(host, str) or not host:
            if is_required:
                raise GroundTruthError(
                    f"Node {node_id}: getnetworkinfo.localaddresses[0].address is unavailable."
                )
            continue
        port = local_address.get("port")
        if not isinstance(port, int):
            port = None
        key = (host.lower(), port)
        previous = endpoint_to_node.get(key)
        if previous is not None and previous != node_id:
            raise GroundTruthError(
                f"Address {host}:{port} is advertised by nodes {previous} and {node_id}."
            )
        endpoint_to_node[key] = node_id
        host_to_nodes.setdefault(host.lower(), set()).add(node_id)

    return endpoint_to_node, host_to_nodes


def _resolve_experiment_node(
    peer: Mapping,
    endpoint_to_node: Mapping[Tuple[str, Optional[int]], int],
    host_to_nodes: Mapping[str, Set[int]],
) -> Optional[int]:
    """Return a configured node ID only when the peer is known unambiguously."""

    address = peer.get("addr", "")
    if not address:
        return None
    host, port = _endpoint(address)
    node_id = endpoint_to_node.get((host, port))
    if node_id is not None:
        return node_id

    candidates = host_to_nodes.get(host, set())
    return next(iter(candidates)) if len(candidates) == 1 else None


def _identity_sort_key(identity: NodeIdentity):
    return (0, identity) if isinstance(identity, int) else (1, identity)


def collect_phase1_groundtruth(
    network_info_by_node: Mapping[int, Mapping],
    peer_info_by_node: Mapping[int, Sequence[Mapping]],
    tracked_node_ids: Iterable[int] = TRACKED_NODE_IDS,
    excluded_node_ids: Iterable[int] = EXCLUDED_NODE_IDS,
) -> GroundTruthSnapshot:
    """Build Phase 1 ground truth from captured RPC responses.

    Configured nodes 0 and 6 are discarded. Other configured nodes retain
    their integer ID. Every remaining, connectable peer is represented by its
    normalized ``addr`` endpoint and becomes an external vertex.
    """

    tracked = tuple(sorted(set(tracked_node_ids)))
    excluded = set(excluded_node_ids)
    endpoint_to_node, host_to_nodes = _build_address_index(network_info_by_node, tracked)

    missing = [node_id for node_id in tracked if node_id not in peer_info_by_node]
    if missing:
        raise GroundTruthError(f"Missing getpeerinfo response for nodes {missing}.")

    peers = {}
    external_nodes = set()
    edges = set()
    for node_id in tracked:
        resolved_peers = set()
        for peer in peer_info_by_node[node_id]:
            address = peer.get("addr", "")
            if not address:
                continue

            experiment_node_id = _resolve_experiment_node(
                peer, endpoint_to_node, host_to_nodes
            )
            if experiment_node_id is not None:
                if experiment_node_id in excluded or experiment_node_id == node_id:
                    continue
                peer_identity: NodeIdentity = experiment_node_id
            else:
                if _is_unconnectable_external_peer(address):
                    continue
                peer_identity = _normalized_endpoint(address)
                external_nodes.add(peer_identity)

            resolved_peers.add(peer_identity)
            edges.add((node_id, peer_identity))
            edges.add((peer_identity, node_id))
        peers[node_id] = tuple(sorted(resolved_peers, key=_identity_sort_key))

    nodes = tuple(tracked) + tuple(sorted(external_nodes))
    return GroundTruthSnapshot(
        nodes=nodes,
        peers=peers,
        gt_edges=tuple(sorted(edges, key=lambda edge: (_identity_sort_key(edge[0]), _identity_sort_key(edge[1])))),
    )


def _node_cli_json(node_id: int, *args):
    """Run RPC and report an immediate, node-specific retrieval failure."""

    cli = nodes_cli[node_id]
    if node_id in EXCLUDED_NODE_IDS:
        result = cli.wsl_cli(*args, ignore=True)
    else:
        result = cli.win_cli(*args, ignore=True)

    command = " ".join(args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).replace("\x00", "").strip()
        detail = detail or f"exit status {result.returncode}"
        raise GroundTruthError(f"Node {node_id}: cannot retrieve {command}: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise GroundTruthError(
            f"Node {node_id}: cannot parse {command} response as JSON."
        ) from error


def retrieve_phase1_groundtruth() -> GroundTruthSnapshot:
    """Collect live RPC data and return the Phase 1 ground-truth snapshot."""

    network_info_by_node = {
        node_id: _node_cli_json(node_id, "getnetworkinfo")
        for node_id in TRACKED_NODE_IDS
    }
    for node_id in EXCLUDED_NODE_IDS:
        try:
            network_info_by_node[node_id] = _node_cli_json(node_id, "getnetworkinfo")
        except GroundTruthError:
            # Nodes 0 and 6 are not part of S_groundtruth_before. Their primary
            # address is useful for recognizing them, but is not mandatory.
            continue
    peer_info_by_node = {
        node_id: _node_cli_json(node_id, "getpeerinfo")
        for node_id in TRACKED_NODE_IDS
    }
    return collect_phase1_groundtruth(network_info_by_node, peer_info_by_node)
