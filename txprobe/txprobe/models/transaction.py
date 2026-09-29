"""Transaction message and round crafting data models."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .graph import GraphSnapshot
from .node import NodeIdentity


@dataclass(frozen=True)
class TxMessage:
    """A signed transaction not yet broadcast."""

    hexstr: str
    txid: str
    wtxid: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "hexstr": self.hexstr,
            "txid": self.txid,
            "wtxid": self.wtxid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxMessage:
        """Deserialize from a dictionary."""
        return cls(
            hexstr=str(data["hexstr"]),
            txid=str(data["txid"]),
            wtxid=str(data["wtxid"]),
        )


@dataclass(frozen=True)
class UtxoInfo:
    """Spendable UTXO metadata."""

    txid: str
    vout: int
    amount_sats: int
    confirmations: int = 1
    script_pub_key: str = ""

    @property
    def outpoint(self) -> tuple[str, int]:
        """Return (txid, vout) tuple."""
        return (self.txid, self.vout)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "txid": self.txid,
            "vout": self.vout,
            "amount_sats": self.amount_sats,
            "confirmations": self.confirmations,
            "script_pub_key": self.script_pub_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UtxoInfo:
        """Deserialize from a dictionary."""
        return cls(
            txid=str(data["txid"]),
            vout=int(data["vout"]),
            amount_sats=int(data["amount_sats"]),
            confirmations=int(data.get("confirmations", 1)),
            script_pub_key=str(data.get("script_pub_key", "")),
        )


@dataclass(frozen=True)
class MatrixRound:
    """Node partition for a single TxProbe matrix round."""

    round_index: int
    source_nodes: tuple[NodeIdentity, ...]
    sink_nodes: tuple[NodeIdentity, ...]

    @property
    def num_sources(self) -> int:
        """Number of nodes in the source set."""
        return len(self.source_nodes)

    @property
    def num_sinks(self) -> int:
        """Number of nodes in the sink set."""
        return len(self.sink_nodes)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "round_index": self.round_index,
            "source_nodes": [n.addr for n in self.source_nodes],
            "sink_nodes": [n.addr for n in self.sink_nodes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatrixRound:
        """Deserialize from a dictionary."""
        return cls(
            round_index=int(data["round_index"]),
            source_nodes=tuple(NodeIdentity(addr=a) for a in data["source_nodes"]),
            sink_nodes=tuple(NodeIdentity(addr=a) for a in data["sink_nodes"]),
        )


@dataclass(frozen=True)
class TxProbeRoundTxs:
    """Pre-crafted transactions and node partition for one TxProbe round."""

    round_index: int
    source_nodes: tuple[NodeIdentity, ...]
    sink_nodes: tuple[NodeIdentity, ...]
    utxo: UtxoInfo
    parent_txs: tuple[TxMessage, ...]
    flood_tx: TxMessage
    marker_txs: tuple[TxMessage, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "round_index": self.round_index,
            "source_nodes": [n.addr for n in self.source_nodes],
            "sink_nodes": [n.addr for n in self.sink_nodes],
            "utxo": self.utxo.to_dict(),
            "parent_txs": [tx.to_dict() for tx in self.parent_txs],
            "flood_tx": self.flood_tx.to_dict(),
            "marker_txs": [tx.to_dict() for tx in self.marker_txs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxProbeRoundTxs:
        """Deserialize from a dictionary."""
        return cls(
            round_index=int(data["round_index"]),
            source_nodes=tuple(NodeIdentity(addr=a) for a in data["source_nodes"]),
            sink_nodes=tuple(NodeIdentity(addr=a) for a in data["sink_nodes"]),
            utxo=UtxoInfo.from_dict(data["utxo"]),
            parent_txs=tuple(TxMessage.from_dict(t) for t in data["parent_txs"]),
            flood_tx=TxMessage.from_dict(data["flood_tx"]),
            marker_txs=tuple(TxMessage.from_dict(t) for t in data["marker_txs"]),
        )


@dataclass(frozen=True)
class TxCraftingStats:
    """Summary statistics for Step 3 transaction crafting."""

    total_nodes: int
    matrix_width: int
    matrix_height: int
    total_rounds: int
    total_parent_txs: int
    total_flood_txs: int
    total_marker_txs: int
    split_txids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "total_nodes": self.total_nodes,
            "matrix_width": self.matrix_width,
            "matrix_height": self.matrix_height,
            "total_rounds": self.total_rounds,
            "total_parent_txs": self.total_parent_txs,
            "total_flood_txs": self.total_flood_txs,
            "total_marker_txs": self.total_marker_txs,
            "split_txids": list(self.split_txids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxCraftingStats:
        """Deserialize from a dictionary."""
        return cls(
            total_nodes=int(data["total_nodes"]),
            matrix_width=int(data["matrix_width"]),
            matrix_height=int(data["matrix_height"]),
            total_rounds=int(data["total_rounds"]),
            total_parent_txs=int(data["total_parent_txs"]),
            total_flood_txs=int(data["total_flood_txs"]),
            total_marker_txs=int(data["total_marker_txs"]),
            split_txids=tuple(str(t) for t in data.get("split_txids", [])),
        )


@dataclass(frozen=True)
class TxProbeCraftingResult:
    """Complete Step 3 output containing the snapshot, pre-crafted rounds, and stats."""

    snapshot: GraphSnapshot
    rounds: tuple[TxProbeRoundTxs, ...]
    stats: TxCraftingStats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "snapshot": self.snapshot.to_dict(),
            "rounds": [r.to_dict() for r in self.rounds],
            "stats": self.stats.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        """Save to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TxProbeCraftingResult:
        """Deserialize from a dictionary."""
        return cls(
            snapshot=GraphSnapshot.from_dict(data["snapshot"]),
            rounds=tuple(TxProbeRoundTxs.from_dict(r) for r in data["rounds"]),
            stats=TxCraftingStats.from_dict(data["stats"]),
        )

    @classmethod
    def from_json(cls, text: str) -> TxProbeCraftingResult:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> TxProbeCraftingResult:
        """Load from a JSON file."""
        p = Path(path)
        return cls.from_json(p.read_text(encoding="utf-8"))

