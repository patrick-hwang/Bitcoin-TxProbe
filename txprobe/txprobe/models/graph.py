"""Graph snapshot data model."""

from __future__ import annotations

import json
from collections.abc import Mapping
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
