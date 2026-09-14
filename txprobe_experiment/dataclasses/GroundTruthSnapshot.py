from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType

from .NodeIdentity import NodeIdentity

@dataclass(frozen=True)
class GroundTruthSnapshot:
    """The snapshot of the groundtruth"""

    nodes: tuple[NodeIdentity, ...]
    adj_list: Mapping[NodeIdentity, tuple[NodeIdentity, ...]]

    def eliminate_nodes_not_in_both_lists(
            self,
            peer_list_1: list[NodeIdentity],
            peer_list_2: list[NodeIdentity]
    ) -> GroundTruthSnapshot:
        valid_nodes_set: set[NodeIdentity] = set(peer_list_1) & set(peer_list_2)

        new_nodes: list[NodeIdentity] = [node for node in self.nodes if node in valid_nodes_set]
        new_nodes_set: set[NodeIdentity] = set(new_nodes)

        new_adj_list: dict[NodeIdentity, list[NodeIdentity]] = {node: [] for node in new_nodes_set}
        for node in new_nodes:
            original_peer_list: list[NodeIdentity] = self.adj_list[node]
            new_adj_list[node] = [peer for peer in original_peer_list if peer in new_nodes_set]
            
        return GroundTruthSnapshot(
            nodes = tuple(new_nodes),
            adj_list = MappingProxyType({
                node: tuple(peers)
                for node, peers in new_adj_list.items()
            })
        )