"""Graph snapshot data model."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .node import NodeIdentity


@dataclass(frozen=True)
class GraphSnapshot:
    """Immutable snapshot of a network topology graph."""

    nodes: tuple[NodeIdentity, ...]
    adj_list: Mapping[NodeIdentity, tuple[NodeIdentity, ...]]

    @property
    def num_nodes(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self.nodes)

    @property
    def num_edges(self) -> int:
        """Return the number of undirected edges in the graph."""
        unique_edges: set[tuple[str, str]] = set()
        for u, neighbors in self.adj_list.items():
            for v in neighbors:
                edge = (u.addr, v.addr) if u.addr <= v.addr else (v.addr, u.addr)
                unique_edges.add(edge)
        return len(unique_edges)

    def prune_nodes(self, keep_nodes: Iterable[NodeIdentity]) -> GraphSnapshot:
        """Return a new GraphSnapshot keeping only specified nodes and their mutual edges."""
        keep_set = set(keep_nodes)
        new_nodes = tuple(n for n in self.nodes if n in keep_set)
        new_adj: dict[NodeIdentity, tuple[NodeIdentity, ...]] = {}
        for node in new_nodes:
            new_adj[node] = tuple(p for p in self.adj_list.get(node, ()) if p in keep_set)
        return GraphSnapshot(
            nodes=new_nodes,
            adj_list=MappingProxyType(new_adj),
        )

    def remove_nodes(self, remove_nodes: Iterable[NodeIdentity]) -> GraphSnapshot:
        """Return a new GraphSnapshot removing specified nodes and their incident edges."""
        rem_set = set(remove_nodes)
        return self.prune_nodes(n for n in self.nodes if n not in rem_set)

    def remove_edges(
        self,
        edges_to_remove: Iterable[tuple[NodeIdentity, NodeIdentity] | tuple[str, str]],
    ) -> GraphSnapshot:
        """Return a new GraphSnapshot removing specified undirected edges.

        Accepts edges as tuples of either NodeIdentity or address strings.
        Preserves all nodes and non-removed edges.
        """
        edge_set: set[tuple[str, str]] = set()
        for edge in edges_to_remove:
            u_addr = edge[0].addr if hasattr(edge[0], "addr") else str(edge[0])
            v_addr = edge[1].addr if hasattr(edge[1], "addr") else str(edge[1])
            edge_set.add((u_addr, v_addr) if u_addr <= v_addr else (v_addr, u_addr))

        new_adj: dict[NodeIdentity, tuple[NodeIdentity, ...]] = {}
        for node in self.nodes:
            current_peers = self.adj_list.get(node, ())
            filtered_peers: list[NodeIdentity] = []
            for peer in current_peers:
                canonical = (
                    (node.addr, peer.addr)
                    if node.addr <= peer.addr
                    else (peer.addr, node.addr)
                )
                if canonical not in edge_set:
                    filtered_peers.append(peer)
            new_adj[node] = tuple(filtered_peers)

        return GraphSnapshot(
            nodes=self.nodes,
            adj_list=MappingProxyType(new_adj),
        )

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "nodes": [n.addr for n in self.nodes],
            "adj_list": {
                node.addr: [peer.addr for peer in peers]
                for node, peers in self.adj_list.items()
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        """Write graph snapshot to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> GraphSnapshot:
        """Deserialize from a dict."""
        nodes = tuple(NodeIdentity(addr=a) for a in data["nodes"])
        adj_list: dict[NodeIdentity, tuple[NodeIdentity, ...]] = {}
        for addr_str, peer_strs in data["adj_list"].items():
            node = NodeIdentity(addr=addr_str)
            adj_list[node] = tuple(NodeIdentity(addr=p) for p in peer_strs)
        return cls(
            nodes=nodes,
            adj_list=MappingProxyType(adj_list),
        )

    @classmethod
    def from_json(cls, text: str) -> GraphSnapshot:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> GraphSnapshot:
        """Load a GraphSnapshot from a JSON file."""
        path = Path(path)
        return cls.from_json(path.read_text(encoding="utf-8"))
