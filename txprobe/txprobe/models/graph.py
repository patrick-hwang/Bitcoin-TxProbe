"""Graph snapshot data model."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .node import NodeIdentity


@dataclass(frozen=True)
class GraphSnapshot:
    """Immutable snapshot of a network topology graph."""

    nodes: tuple[NodeIdentity, ...]
    adj_list: Mapping[NodeIdentity, tuple[NodeIdentity, ...]]

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
