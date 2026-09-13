from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from .NodeIdentity import NodeIdentity

@dataclass(frozen=True)
class GroundTruthSnapshot:
    """The snapshot of the groundtruth
    """

    nodes: tuple[NodeIdentity, ...]
    adj_list: Mapping[NodeIdentity, tuple[NodeIdentity, ...]]

    # def remove_nodes(
    #     self,
    #     removing_nodes: Iterable[NodeIdentity],
    # ):
    #     set_removing_nodes = set(removing_nodes)
    #     nodes = tuple(sorted((identity for identity in self.nodes if identity not in set_removing_nodes), key=_identity_sort_key))
    #     peers = {key: value for key, value in self.peers.items() if key in nodes}
    #     for node_id, peers_of_node in peers:
    #         peers_of_node = tuple(sorted((identity for identity in peers_of_node if identity in nodes)))
    #         peers[node_id] = peers_of_node
    #     gt_edges = tuple(sorted((pair for 
    #         pair in self.gt_edges
    #         if pair[0] in nodes and pair[1] in nodes), 
    #         key=lambda edge: (_identity_sort_key(edge[0]), _identity_sort_key(edge[1]))))
    #     return GroundTruthSnapshot(
    #         nodes = nodes, peers = peers,
    #         gt_edges = gt_edges
    #     )

    # def as_dict(self):
    #     return {
    #         "nodes": list(self.nodes),
    #         "peers": {str(node_id): list(peers) for node_id, peers in sorted(self.peers.items())},
    #         "gt_edges": [list(edge) for edge in self.gt_edges],
    #     }