from collections import defaultdict
from types import MappingProxyType

from ..dataclasses.GraphSnapshot import GraphSnapshot
from ..dataclasses.NodeIdentity import NodeIdentity
from ..objects.node_indices import groundtruth_nodes
from ..objects.node_instances import nodes_cli

def step_5_filter_malfunction_nodes(
        old_groundtruth: GraphSnapshot
) -> GraphSnapshot:
    try:
        result = filter_transitory_edges(old_groundtruth)
        result = filter_disconnecting_nodes(result)
        return result
    except Exception as e:
        print(f"Step 5: Encounter an exception {e}")
        raise

def filter_transitory_edges(old_graph: GraphSnapshot) -> GraphSnapshot:
    try:
        new_nodes: set[NodeIdentity] = set()
        new_adj_list: dict[NodeIdentity, set[NodeIdentity]] = defaultdict(set)
        for id in groundtruth_nodes:
            node_identity = nodes_cli[id].get_identity()
            if node_identity in old_graph.nodes:
                peers = nodes_cli[id].get_peer_list()
                peers_in_adj_list = old_graph.adj_list[node_identity]
                new_peers = set(peers) & set(peers_in_adj_list)

                new_adj_list[node_identity].update(new_peers)
                for peer in new_peers:
                    new_adj_list.setdefault(peer, set()).add(node_identity)
                
                new_nodes.add(node_identity)
                new_nodes.update(new_peers)
        return GraphSnapshot(
            nodes = tuple(new_nodes),
            adj_list = MappingProxyType({
                node: tuple(peers)
                for node, peers in new_adj_list.items()
            })
        )
    except Exception as e:
        print(f"Filter transitory edges: Encounter an error {e}")
        raise

def filter_disconnecting_nodes(old_graph: GraphSnapshot) -> GraphSnapshot:
    try:
        probing_nodes: list[NodeIdentity] = nodes_cli[0].get_peer_list()
        new_nodes: set[NodeIdentity] = {node for node in old_graph.nodes if node in probing_nodes}
        new_adj_list: dict[NodeIdentity, set[NodeIdentity]] = defaultdict(set)
        for node in new_nodes:
            old_peers = old_graph.adj_list.get(node, tuple())
            new_peers = {peer for peer in old_peers if peer in new_nodes}
            new_adj_list[node].update(new_peers)
            for peer in new_peers:
                new_adj_list[peer].add(node)
        return GraphSnapshot(
            nodes = tuple(new_nodes),
            adj_list = MappingProxyType({
                node: tuple(peer_list)
                for node, peer_list in new_adj_list.items()
            })
        )
    except Exception as e:
        print(f"Filter disconnecting nodes: encounter an error {e}")
        raise