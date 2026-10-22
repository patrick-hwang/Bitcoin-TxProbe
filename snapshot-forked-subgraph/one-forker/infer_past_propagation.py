"""Past Block Propagation Inference Engine and Snapshot Evaluator.

Infers the prior propagation state of a target block at time (t - delta) from
a snapshot at time t using the backward network propagation constraint rule:
If a node u does not know the target block at time t, then at time (t - delta),
neither u nor any of its connected neighbors v in N(u) knew the target block.

Compares inferred past snapshots against ground truth snapshots and computes
confusion matrix (TP, FP, TN, FN) and evaluation metrics (Accuracy, Precision, Recall, F1).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import sys
from typing import Any, Sequence

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
for p in (CURRENT_DIR, TXPROBE_DIR, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from config import DEFAULT_INFERRED_TOPOLOGY_PATH, DEFAULT_RESULTS_DIR, DEFAULT_TOPOLOGY_PATH, load_topology
except ImportError:
    from .config import DEFAULT_INFERRED_TOPOLOGY_PATH, DEFAULT_RESULTS_DIR, DEFAULT_TOPOLOGY_PATH, load_topology

log = logging.getLogger("snapshot_fork.infer_past")


@dataclass(frozen=True)
class BlockPropagationSnapshot:
    """Discrete state snapshot representing target block propagation across the network at time t."""

    snapshot_index: int
    rel_time_ms: float
    timestamp: float
    target_block_hash: str
    known_nodes: list[int]
    unknown_nodes: list[int]
    total_nodes: int
    is_inferred: bool = False
    source_snapshot_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_index": self.snapshot_index,
            "rel_time_ms": round(self.rel_time_ms, 3),
            "timestamp": round(self.timestamp, 6),
            "target_block_hash": self.target_block_hash,
            "known_nodes": self.known_nodes,
            "unknown_nodes": self.unknown_nodes,
            "known_count": len(self.known_nodes),
            "unknown_count": len(self.unknown_nodes),
            "total_nodes": self.total_nodes,
            "is_inferred": self.is_inferred,
            "source_snapshot_index": self.source_snapshot_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlockPropagationSnapshot:
        return cls(
            snapshot_index=int(data["snapshot_index"]),
            rel_time_ms=float(data["rel_time_ms"]),
            timestamp=float(data["timestamp"]),
            target_block_hash=str(data["target_block_hash"]),
            known_nodes=list(data.get("known_nodes", [])),
            unknown_nodes=list(data.get("unknown_nodes", [])),
            total_nodes=int(data.get("total_nodes", len(data.get("known_nodes", [])) + len(data.get("unknown_nodes", [])))),
            is_inferred=bool(data.get("is_inferred", False)),
            source_snapshot_index=data.get("source_snapshot_index"),
        )


@dataclass(frozen=True)
class InferenceMetrics:
    """Evaluation metrics comparing an inferred past snapshot with ground truth."""

    snapshot_index: int
    source_snapshot_index: int
    timestamp: float
    rel_time_ms: float
    tp: int
    fp: int
    tn: int
    fn: int
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    total_nodes: int
    real_known_count: int
    inferred_known_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_index": self.snapshot_index,
            "source_snapshot_index": self.source_snapshot_index,
            "timestamp": round(self.timestamp, 6),
            "rel_time_ms": round(self.rel_time_ms, 3),
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "total_nodes": self.total_nodes,
            "real_known_count": self.real_known_count,
            "inferred_known_count": self.inferred_known_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InferenceMetrics:
        return cls(
            snapshot_index=int(data["snapshot_index"]),
            source_snapshot_index=int(data["source_snapshot_index"]),
            timestamp=float(data["timestamp"]),
            rel_time_ms=float(data["rel_time_ms"]),
            tp=int(data["tp"]),
            fp=int(data["fp"]),
            tn=int(data["tn"]),
            fn=int(data["fn"]),
            accuracy=float(data["accuracy"]),
            precision=float(data["precision"]),
            recall=float(data["recall"]),
            f1_score=float(data["f1_score"]),
            total_nodes=int(data.get("total_nodes", data["tp"] + data["fp"] + data["tn"] + data["fn"])),
            real_known_count=int(data.get("real_known_count", data["tp"] + data["fn"])),
            inferred_known_count=int(data.get("inferred_known_count", data["tp"] + data["fp"])),
        )


def get_propagation_snapshot_at(
    node_timings: dict[str | int, Any],
    target_block_hash: str,
    t: float,
    snapshot_index: int = 0,
    rel_origin_t: float | None = None,
    all_nodes: Sequence[int] | None = None,
) -> BlockPropagationSnapshot:
    """Construct a discrete BlockPropagationSnapshot for target block at continuous timestamp t.

    A node u is considered to 'know' target_block_hash at time t if and only if
    node_timings records that u received target_block_hash at or before t.
    """
    if all_nodes is None:
        all_nodes_list = sorted(int(k) for k in node_timings.keys())
    else:
        all_nodes_list = sorted(all_nodes)

    if rel_origin_t is None:
        rel_origin_t = t

    rel_time_ms = round((t - rel_origin_t) * 1000.0, 3)

    known_nodes: list[int] = []
    unknown_nodes: list[int] = []

    for nid in all_nodes_list:
        info = node_timings.get(nid) or node_timings.get(str(nid))
        rec_time: float | None = None
        if info is not None:
            if hasattr(info, "block_received_at"):
                rec_time = info.block_received_at.get(target_block_hash)
            elif isinstance(info, dict):
                rec_time = info.get("block_received_at", {}).get(target_block_hash)

        if rec_time is not None and rec_time <= t:
            known_nodes.append(nid)
        else:
            unknown_nodes.append(nid)

    return BlockPropagationSnapshot(
        snapshot_index=snapshot_index,
        rel_time_ms=rel_time_ms,
        timestamp=round(t, 6),
        target_block_hash=target_block_hash,
        known_nodes=known_nodes,
        unknown_nodes=unknown_nodes,
        total_nodes=len(all_nodes_list),
        is_inferred=False,
    )


def generate_block_propagation_snapshots(
    node_timings: dict[str | int, Any],
    target_block_hash: str,
    start_time: float,
    end_time: float,
    step_ms: float = 10.0,
    all_nodes: Sequence[int] | None = None,
) -> list[BlockPropagationSnapshot]:
    """Slice continuous block propagation timeline into discrete BlockPropagationSnapshots."""
    if end_time < start_time:
        raise ValueError(f"end_time ({end_time}) cannot be earlier than start_time ({start_time})")

    step_sec = step_ms / 1000.0
    snapshots: list[BlockPropagationSnapshot] = []

    idx = 0
    while True:
        curr_t = round(start_time + idx * step_sec, 6)
        if curr_t > end_time + 1e-6:
            break
        snap = get_propagation_snapshot_at(
            node_timings=node_timings,
            target_block_hash=target_block_hash,
            t=curr_t,
            snapshot_index=idx,
            rel_origin_t=start_time,
            all_nodes=all_nodes,
        )
        snapshots.append(snap)
        idx += 1

    return snapshots


def extract_known_nodes(
    snapshot: Any,
    target_block_hash: str,
    node_timings: dict[str | int, Any] | None = None,
    all_nodes: Sequence[int] | set[int] | None = None,
) -> set[int]:
    """Extract set of node IDs that know target_block_hash at snapshot time.

    Prefers exact block receipt timing from node_timings if available to prevent
    consensus reorg artifacts from masquerading as unknown nodes.
    """
    if isinstance(snapshot, BlockPropagationSnapshot):
        if snapshot.target_block_hash == target_block_hash:
            return set(snapshot.known_nodes)
        return set()

    snap_dict = snapshot if isinstance(snapshot, dict) else (snapshot.to_dict() if hasattr(snapshot, "to_dict") else {})

    # If snapshot directly has known_nodes
    if "known_nodes" in snap_dict and snap_dict.get("target_block_hash") == target_block_hash:
        return {int(n) for n in snap_dict["known_nodes"]}

    # If node_timings is available and snapshot provides timestamp, extract ground truth from timings
    if node_timings is not None and "timestamp" in snap_dict:
        t = float(snap_dict["timestamp"])
        nodes_universe = all_nodes if all_nodes is not None else [int(k) for k in node_timings.keys()]
        known: set[int] = set()
        for nid in nodes_universe:
            info = node_timings.get(nid) or node_timings.get(str(nid))
            if info is not None:
                rec_map = getattr(info, "block_received_at", None) or (info.get("block_received_at") if isinstance(info, dict) else None)
                if rec_map and target_block_hash in rec_map:
                    if rec_map[target_block_hash] <= t + 1e-6:
                        known.add(int(nid))
        return known

    # Fallback to subgraphs partition if present
    subgraphs = getattr(snapshot, "subgraphs", None) or snap_dict.get("subgraphs", {})
    if target_block_hash in subgraphs:
        return {int(n) for n in subgraphs[target_block_hash]}

    return set()


def infer_past_propagation(
    current_known_nodes: Sequence[int] | set[int],
    adjacency: dict[int, list[int]],
    all_nodes: Sequence[int] | set[int] | None = None,
) -> tuple[set[int], set[int]]:
    """Infer prior block propagation state at (t - delta) using the backward constraint rule.

    Principle:
    If a node u does not know the target block at time t (u in U_t),
    then at time (t - delta), neither u nor any connected neighbor v in N(u)
    knew the target block.

    Formally:
    U_inferred(t - delta) = U_t U { v in N(u) for u in U_t }
    K_inferred(t - delta) = V \\ U_inferred(t - delta) = { w in K_t | N[w] subseteq K_t }

    Returns:
        tuple[set[int], set[int]]: (inferred_known_nodes, inferred_unknown_nodes)
    """
    if all_nodes is None:
        nodes_universe: set[int] = {int(k) for k in adjacency.keys()} | {int(x) for x in current_known_nodes}
    else:
        nodes_universe = {int(x) for x in all_nodes}

    known_t = {int(x) for x in current_known_nodes} & nodes_universe
    unknown_t = nodes_universe - known_t

    # Standardize adjacency to integer keys and values
    adj_clean: dict[int, list[int]] = {}
    for k, vs in adjacency.items():
        adj_clean[int(k)] = [int(v) for v in vs]

    # Propagate unknown backwards: all unknown nodes and their connected neighbors are unknown
    inferred_unknown: set[int] = set(unknown_t)
    for u in unknown_t:
        for v in adj_clean.get(u, []):
            if v in nodes_universe:
                inferred_unknown.add(v)

    inferred_known = nodes_universe - inferred_unknown
    return inferred_known, inferred_unknown


def infer_past_block_propagation_snapshot(
    current_snapshot: Any,
    adjacency: dict[int, list[int]],
    target_block_hash: str,
    delta_ms: float = 10.0,
    all_nodes: Sequence[int] | set[int] | None = None,
    node_timings: dict[str | int, Any] | None = None,
) -> BlockPropagationSnapshot:
    """Infer past BlockPropagationSnapshot at (t - delta) from current snapshot at time t."""
    all_nodes_set = set(all_nodes) if all_nodes is not None else set(adjacency.keys())
    known_curr = extract_known_nodes(current_snapshot, target_block_hash, node_timings=node_timings, all_nodes=all_nodes_set)
    inferred_known, inferred_unknown = infer_past_propagation(known_curr, adjacency, all_nodes_set)

    curr_idx: int = getattr(
        current_snapshot,
        "snapshot_index",
        current_snapshot.get("snapshot_index", 0) if isinstance(current_snapshot, dict) else 0,
    )
    curr_t: float = getattr(
        current_snapshot,
        "timestamp",
        current_snapshot.get("timestamp", 0.0) if isinstance(current_snapshot, dict) else 0.0,
    )
    curr_rel_ms: float = getattr(
        current_snapshot,
        "rel_time_ms",
        current_snapshot.get("rel_time_ms", 0.0) if isinstance(current_snapshot, dict) else 0.0,
    )

    inferred_idx = max(0, curr_idx - 1)
    inferred_t = max(0.0, curr_t - (delta_ms / 1000.0))
    inferred_rel_ms = max(0.0, curr_rel_ms - delta_ms)

    return BlockPropagationSnapshot(
        snapshot_index=inferred_idx,
        rel_time_ms=round(inferred_rel_ms, 3),
        timestamp=round(inferred_t, 6),
        target_block_hash=target_block_hash,
        known_nodes=sorted(inferred_known),
        unknown_nodes=sorted(inferred_unknown),
        total_nodes=len(all_nodes_set),
        is_inferred=True,
        source_snapshot_index=curr_idx,
    )


def compute_metrics(
    y_true_known: Sequence[int] | set[int],
    y_pred_known: Sequence[int] | set[int],
    all_nodes: Sequence[int] | set[int],
) -> tuple[int, int, int, int, float, float, float, float]:
    """Compute binary classification metrics for block propagation state.

    Positive class: Node knows the target block (is infected/informed).
    Negative class: Node does not know the target block (is uninfected/uninformed).

    Returns:
        tuple[int, int, int, int, float, float, float, float]:
        (tp, fp, tn, fn, accuracy, precision, recall, f1_score)
    """
    nodes_universe = {int(x) for x in all_nodes}
    total = len(nodes_universe)
    if total == 0:
        return 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0

    y_true = {int(x) for x in y_true_known} & nodes_universe
    y_pred = {int(x) for x in y_pred_known} & nodes_universe

    tp = len(y_pred & y_true)
    fp = len(y_pred - y_true)
    fn = len(y_true - y_pred)
    tn = total - (tp + fp + fn)

    accuracy = (tp + tn) / total

    # Handle precision edge cases
    if (tp + fp) == 0:
        # No predicted positives
        precision = 1.0 if (tp + fn) == 0 else 0.0
    else:
        precision = tp / (tp + fp)

    # Handle recall edge cases
    if (tp + fn) == 0:
        # No actual positives
        recall = 1.0 if (tp + fp) == 0 else 0.0
    else:
        recall = tp / (tp + fn)

    # Handle F1 edge cases
    if (precision + recall) == 0.0:
        f1_score = 0.0
    else:
        f1_score = 2.0 * (precision * recall) / (precision + recall)

    return tp, fp, tn, fn, accuracy, precision, recall, f1_score


def evaluate_inference(
    inferred_snapshot: BlockPropagationSnapshot,
    ground_truth_snapshot: Any,
    all_nodes: Sequence[int] | set[int] | None = None,
    target_block_hash: str | None = None,
    node_timings: dict[str | int, Any] | None = None,
) -> InferenceMetrics:
    """Compare an inferred past snapshot against ground truth and compute metrics."""
    block_hash = target_block_hash or inferred_snapshot.target_block_hash
    if all_nodes is not None:
        all_nodes_set = set(all_nodes)
    else:
        all_nodes_set = set(inferred_snapshot.known_nodes) | set(inferred_snapshot.unknown_nodes)

    real_known = extract_known_nodes(
        ground_truth_snapshot,
        block_hash,
        node_timings=node_timings,
        all_nodes=all_nodes_set,
    )
    inferred_known = set(inferred_snapshot.known_nodes) & all_nodes_set

    tp, fp, tn, fn, acc, prec, rec, f1 = compute_metrics(real_known, inferred_known, all_nodes_set)
    return InferenceMetrics(
        snapshot_index=inferred_snapshot.snapshot_index,
        source_snapshot_index=inferred_snapshot.source_snapshot_index if inferred_snapshot.source_snapshot_index is not None else inferred_snapshot.snapshot_index + 1,
        timestamp=inferred_snapshot.timestamp,
        rel_time_ms=inferred_snapshot.rel_time_ms,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        accuracy=acc,
        precision=prec,
        recall=rec,
        f1_score=f1,
        total_nodes=len(all_nodes_set),
        real_known_count=len(real_known),
        inferred_known_count=len(inferred_known),
    )


def resolve_target_block(data: dict[str, Any], block_spec: str) -> tuple[str, str]:
    """Resolve block label (e.g. 'B1', 'B2', 'B3') or partial/full hex to (canonical_label, block_hash)."""
    fork_blocks: dict[str, str] = data.get("fork_blocks", {})
    spec_clean = block_spec.strip()
    spec_lower = spec_clean.lower()

    # 1. Exact label match (e.g. "B1")
    if spec_clean in fork_blocks:
        return spec_clean, fork_blocks[spec_clean]

    # 2. Case-insensitive label match (e.g. "b1" -> "B1")
    for label, h in fork_blocks.items():
        if spec_lower == label.lower():
            return label, h

    # 3. Exact full 64-char hex match
    for label, h in fork_blocks.items():
        if spec_lower == h.lower():
            return label, h

    # 4. Partial hex prefix match (min 4 hex chars)
    if len(spec_clean) >= 4:
        matches = [
            (label, h) for label, h in fork_blocks.items()
            if h.lower().startswith(spec_lower) or spec_lower in h.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            raise ValueError(f"Ambiguous block hex prefix '{block_spec}' matches multiple blocks: {[m[0] for m in matches]}")

    # 5. If block_spec is a 64-char hex not present in fork_blocks
    if len(spec_clean) == 64:
        return "CUSTOM", spec_clean

    raise ValueError(f"Could not resolve target block specifier: {block_spec}. Available blocks: {list(fork_blocks.keys())}")


def resolve_target_block_hash(data: dict[str, Any], block_spec: str) -> str:
    """Resolve block label (e.g. 'B1', 'B2', 'B3') or partial/full hex to block hash."""
    _, block_hash = resolve_target_block(data, block_spec)
    return block_hash


def infer_multistep_past_propagation(
    initial_snapshot: Any,
    adjacency: dict[int, list[int]],
    target_block_hash: str,
    num_steps: int = 1,
    delta_ms: float = 10.0,
    all_nodes: Sequence[int] | set[int] | None = None,
    node_timings: dict[str | int, Any] | None = None,
) -> list[BlockPropagationSnapshot]:
    """Recursively infer block propagation state backwards across multiple time steps without intermediate ground truth.

    Chains inferences:
    Step 1: t -> (t - delta) from initial snapshot.
    Step 2..m: (t - (k-1)*delta) -> (t - k*delta) taking the prior inferred snapshot as input.

    Returns:
        list[BlockPropagationSnapshot]: Inferred snapshots from step 1 to num_steps backwards.
    """
    if num_steps < 1:
        raise ValueError(f"num_steps must be >= 1, got {num_steps}")

    all_nodes_set = set(all_nodes) if all_nodes is not None else {int(k) for k in adjacency.keys()}
    results: list[BlockPropagationSnapshot] = []

    current_snap = initial_snapshot
    for step_i in range(1, num_steps + 1):
        # Only use node_timings for the very first step if initial_snapshot is not already inferred
        use_timings = node_timings if (step_i == 1 and not getattr(current_snap, "is_inferred", False)) else None

        inferred = infer_past_block_propagation_snapshot(
            current_snapshot=current_snap,
            adjacency=adjacency,
            target_block_hash=target_block_hash,
            delta_ms=delta_ms,
            all_nodes=all_nodes_set,
            node_timings=use_timings,
        )
        results.append(inferred)
        current_snap = inferred

    return results


def evaluate_snapshot_data(
    data: dict[str, Any],
    adjacency: dict[int, list[int]],
    target_block: str = "B1",
    step_index: int | None = None,
    use_timings_groundtruth: bool = True,
) -> dict[str, Any]:
    """Execute backward propagation inference across snapshots and compute evaluation metrics."""
    canonical_label, target_block_hash = resolve_target_block(data, target_block)
    delta_ms = float(data.get("snapshot_interval_ms", 10.0))
    snapshots = data.get("snapshots", [])
    node_timings = data.get("node_timings") if use_timings_groundtruth else None
    all_nodes = sorted(int(k) for k in adjacency.keys())

    evaluations: list[InferenceMetrics] = []
    inferred_snapshots: list[BlockPropagationSnapshot] = []

    if not snapshots:
        raise ValueError("No snapshots found in input data.")

    if step_index is not None:
        if step_index < 1 or step_index >= len(snapshots):
            raise IndexError(f"Step index {step_index} out of range [1, {len(snapshots) - 1}]")
        step_indices = [step_index]
    else:
        step_indices = list(range(1, len(snapshots)))

    for k in step_indices:
        curr_snap = snapshots[k]
        prev_snap_real = snapshots[k - 1]

        inferred_snap = infer_past_block_propagation_snapshot(
            current_snapshot=curr_snap,
            adjacency=adjacency,
            target_block_hash=target_block_hash,
            delta_ms=delta_ms,
            all_nodes=all_nodes,
            node_timings=node_timings,
        )
        inferred_snapshots.append(inferred_snap)

        metrics = evaluate_inference(
            inferred_snapshot=inferred_snap,
            ground_truth_snapshot=prev_snap_real,
            all_nodes=all_nodes,
            target_block_hash=target_block_hash,
            node_timings=node_timings,
        )
        evaluations.append(metrics)

    n = len(evaluations)
    mean_acc = sum(m.accuracy for m in evaluations) / n if n else 0.0
    mean_prec = sum(m.precision for m in evaluations) / n if n else 0.0
    mean_rec = sum(m.recall for m in evaluations) / n if n else 0.0
    mean_f1 = sum(m.f1_score for m in evaluations) / n if n else 0.0

    return {
        "target_block_label": canonical_label,
        "target_block_hash": target_block_hash,
        "delta_ms": delta_ms,
        "total_nodes": len(all_nodes),
        "total_steps_evaluated": len(evaluations),
        "mean_metrics": {
            "accuracy": round(mean_acc, 4),
            "precision": round(mean_prec, 4),
            "recall": round(mean_rec, 4),
            "f1_score": round(mean_f1, 4),
        },
        "step_metrics": [m.to_dict() for m in evaluations],
        "inferred_snapshots": [s.to_dict() for s in inferred_snapshots],
    }


def compare_topologies_evaluation(
    data: dict[str, Any],
    gt_adjacency: dict[int, list[int]],
    inferred_adjacency: dict[int, list[int]],
    target_block: str = "B1",
    step_index: int | None = None,
    use_timings_groundtruth: bool = True,
) -> dict[str, Any]:
    """Execute backward propagation inference across both Ground Truth and Inferred topologies and compare."""
    res_gt = evaluate_snapshot_data(
        data=data,
        adjacency=gt_adjacency,
        target_block=target_block,
        step_index=step_index,
        use_timings_groundtruth=use_timings_groundtruth,
    )
    res_inf = evaluate_snapshot_data(
        data=data,
        adjacency=inferred_adjacency,
        target_block=target_block,
        step_index=step_index,
        use_timings_groundtruth=use_timings_groundtruth,
    )

    mean_gt = res_gt["mean_metrics"]
    mean_inf = res_inf["mean_metrics"]

    diff_metrics = {
        k: round(mean_inf[k] - mean_gt[k], 4)
        for k in mean_gt
    }

    return {
        "target_block_label": res_gt["target_block_label"],
        "target_block_hash": res_gt["target_block_hash"],
        "delta_ms": res_gt["delta_ms"],
        "total_nodes": res_gt["total_nodes"],
        "total_steps_evaluated": res_gt["total_steps_evaluated"],
        "groundtruth_topology": res_gt,
        "inferred_topology": res_inf,
        "comparison": {
            "mean_gt_metrics": mean_gt,
            "mean_inferred_metrics": mean_inf,
            "metric_differences_inf_minus_gt": diff_metrics,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Infer past block propagation snapshot using backward constraint and evaluate against ground truth."
    )
    parser.add_argument(
        "-i",
        "--input-file",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "fork_subgraph_height_102.json",
        help="Path to snapshot JSON file",
    )
    parser.add_argument(
        "-t",
        "--topology",
        type=Path,
        default=DEFAULT_TOPOLOGY_PATH,
        help="Path to ground truth topology JSON (default: groundtruth_topology.json)",
    )
    parser.add_argument(
        "--inferred-topology",
        type=Path,
        default=DEFAULT_INFERRED_TOPOLOGY_PATH,
        help="Path to TxProbe inferred topology JSON (default: full_inferred_topology.json)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run side-by-side comparison between Ground Truth topology and TxProbe Inferred topology",
    )
    parser.add_argument(
        "-b",
        "--block",
        type=str,
        default="B1",
        help="Target block label (e.g. B1, B2, B3, 'all', or comma-separated list 'B1,B2,B3')",
    )
    parser.add_argument(
        "-s",
        "--step",
        type=int,
        default=None,
        help="Specific snapshot step index k to infer (k-1) from. If omitted, evaluates all steps.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Optional output path or directory to write evaluation results JSON",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print detailed metrics for each step",
    )

    args = parser.parse_args()

    if not args.input_file.exists():
        log.error("Input file not found: %s", args.input_file)
        sys.exit(1)

    if not args.topology.exists():
        log.error("Topology file not found: %s", args.topology)
        sys.exit(1)

    with open(args.input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Determine which blocks to evaluate
    fork_blocks = data.get("fork_blocks", {})
    if args.block.strip().lower() == "all":
        target_blocks = list(fork_blocks.keys()) if fork_blocks else ["B1", "B2", "B3"]
    elif "," in args.block:
        target_blocks = [b.strip() for b in args.block.split(",") if b.strip()]
    else:
        target_blocks = [args.block.strip()]

    if args.compare:
        if not args.inferred_topology.exists():
            log.error("Inferred topology file not found: %s", args.inferred_topology)
            sys.exit(1)

        gt_adjacency = load_topology(args.topology)
        inf_adjacency = load_topology(args.inferred_topology)

        all_comparisons: dict[str, dict[str, Any]] = {}
        for blk in target_blocks:
            comp = compare_topologies_evaluation(
                data=data,
                gt_adjacency=gt_adjacency,
                inferred_adjacency=inf_adjacency,
                target_block=blk,
                step_index=args.step,
            )
            label = comp["target_block_label"]
            all_comparisons[label] = comp
            mean_gt = comp["comparison"]["mean_gt_metrics"]
            mean_inf = comp["comparison"]["mean_inferred_metrics"]
            diffs = comp["comparison"]["metric_differences_inf_minus_gt"]

            print("\n" + "=" * 80)
            print(f"TOPOLOGY COMPARISON: Ground Truth vs. TxProbe Inferred ({label})")
            print("=" * 80)
            print(f"Target Block: {label} ({comp['target_block_hash'][:16]}...)")
            print(f"Total Nodes: {comp['total_nodes']} | Steps Evaluated: {comp['total_steps_evaluated']}")
            print("-" * 80)
            print(f"{'Metric':<14} | {'Ground Truth':<15} | {'TxProbe Inferred':<18} | {'Difference':<12}")
            print("-" * 80)
            for m_key in ["accuracy", "precision", "recall", "f1_score"]:
                v_gt = mean_gt[m_key]
                v_inf = mean_inf[m_key]
                v_diff = diffs[m_key]
                print(f"{m_key.capitalize():<14} | {v_gt:<15.4f} | {v_inf:<18.4f} | {v_diff:+12.4f}")
            print("=" * 80)

            if args.verbose or args.step is not None:
                print("\nTxProbe Inferred Step-by-step breakdown:")
                print(f"{'Step':>5} | {'RelTime(ms)':>11} | {'RealKnown':>9} | {'InfKnown':>8} | {'TP':>5} | {'FP':>5} | {'TN':>5} | {'FN':>5} | {'Acc':>6} | {'Prec':>6} | {'Rec':>6} | {'F1':>6}")
                print("-" * 105)
                for m in comp["inferred_topology"]["step_metrics"]:
                    print(
                        f"{m['snapshot_index']:5d} | {m['rel_time_ms']:11.1f} | {m['real_known_count']:9d} | "
                        f"{m['inferred_known_count']:8d} | {m['tp']:5d} | {m['fp']:5d} | {m['tn']:5d} | {m['fn']:5d} | "
                        f"{m['accuracy']:6.4f} | {m['precision']:6.4f} | {m['recall']:6.4f} | {m['f1_score']:6.4f}"
                    )

            if args.output:
                if len(target_blocks) == 1 and not (args.output.is_dir() or args.output.suffix == ""):
                    save_path = args.output
                else:
                    out_dir = args.output if (args.output.is_dir() or args.output.suffix == "") else args.output.parent
                    save_path = out_dir / f"eval_comparison_{label}.json"

                save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(comp, f, indent=2)
                print(f"\nSaved comparison evaluation results for {label} to: {save_path}")

    else:
        adjacency = load_topology(args.topology)
        all_results: dict[str, dict[str, Any]] = {}
        for blk in target_blocks:
            results = evaluate_snapshot_data(data, adjacency, target_block=blk, step_index=args.step)
            label = results["target_block_label"]
            all_results[label] = results

            print("\n" + "=" * 60)
            print("PAST BLOCK PROPAGATION INFERENCE EVALUATION")
            print("=" * 60)
            print(f"Target Block: {results['target_block_label']} ({results['target_block_hash'][:16]}...)")
            print(f"Total Nodes: {results['total_nodes']} | Steps Evaluated: {results['total_steps_evaluated']}")
            print("-" * 60)
            print("Mean Metrics across evaluated steps:")
            for k, v in results["mean_metrics"].items():
                print(f"  {k.capitalize():12s}: {v:.4f}")
            print("=" * 60)

            if args.verbose or args.step is not None:
                print("\nStep-by-step breakdown:")
                print(f"{'Step':>5} | {'RelTime(ms)':>11} | {'RealKnown':>9} | {'InfKnown':>8} | {'TP':>5} | {'FP':>5} | {'TN':>5} | {'FN':>5} | {'Acc':>6} | {'Prec':>6} | {'Rec':>6} | {'F1':>6}")
                print("-" * 105)
                for m in results["step_metrics"]:
                    print(
                        f"{m['snapshot_index']:5d} | {m['rel_time_ms']:11.1f} | {m['real_known_count']:9d} | "
                        f"{m['inferred_known_count']:8d} | {m['tp']:5d} | {m['fp']:5d} | {m['tn']:5d} | {m['fn']:5d} | "
                        f"{m['accuracy']:6.4f} | {m['precision']:6.4f} | {m['recall']:6.4f} | {m['f1_score']:6.4f}"
                    )

            if args.output:
                if len(target_blocks) == 1 and not (args.output.is_dir() or args.output.suffix == ""):
                    save_path = args.output
                else:
                    out_dir = args.output if (args.output.is_dir() or args.output.suffix == "") else args.output.parent
                    save_path = out_dir / f"eval_inference_{label}.json"

                save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2)
                print(f"\nSaved evaluation results for {label} to: {save_path}")


if __name__ == "__main__":
    main()
