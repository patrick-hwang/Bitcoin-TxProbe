"""Metric calculation and network topology evaluation engine for TxProbe."""

from __future__ import annotations

import json
import math
from collections import deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import statistics

from .models.graph import GraphSnapshot
from .models.node import NodeIdentity
from .reconciliation import canonical_edge


@dataclass(frozen=True)
class ConfusionMatrix:
    """Confusion matrix for edge inference."""

    tp: int
    fp: int
    tn: int
    fn: int

    def to_dict(self) -> dict[str, int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
        }


@dataclass(frozen=True)
class ValidationMetrics:
    """Binary classification metrics evaluated against groundtruth."""

    confusion_matrix: ConfusionMatrix
    precision: float
    recall: float
    accuracy: float
    specificity: float
    f1_score: float
    fpr: float
    fnr: float
    gt_edges_count: int
    inferred_edges_count: int
    total_candidate_pairs: int
    tp_edges: tuple[tuple[str, str], ...]
    fp_edges: tuple[tuple[str, str], ...]
    fn_edges: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict:
        return {
            "confusion_matrix": self.confusion_matrix.to_dict(),
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "accuracy": round(self.accuracy, 6),
            "specificity": round(self.specificity, 6),
            "f1_score": round(self.f1_score, 6),
            "fpr": round(self.fpr, 6),
            "fnr": round(self.fnr, 6),
            "gt_edges_count": self.gt_edges_count,
            "inferred_edges_count": self.inferred_edges_count,
            "total_candidate_pairs": self.total_candidate_pairs,
            "tp_edges": [list(e) for e in self.tp_edges],
            "fp_edges": [list(e) for e in self.fp_edges],
            "fn_edges": [list(e) for e in self.fn_edges],
        }


@dataclass(frozen=True)
class DegreeStats:
    """Node degree statistics across the network."""

    min_degree: int
    max_degree: int
    mean_degree: float
    median_degree: float
    std_degree: float
    degree_histogram: dict[str, int]
    top_hubs: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict:
        return {
            "min_degree": self.min_degree,
            "max_degree": self.max_degree,
            "mean_degree": round(self.mean_degree, 4),
            "median_degree": round(self.median_degree, 4),
            "std_degree": round(self.std_degree, 4),
            "degree_histogram": self.degree_histogram,
            "top_hubs": [{"addr": addr, "degree": deg} for addr, deg in self.top_hubs],
        }


@dataclass(frozen=True)
class ComponentStats:
    """Connected component decomposition metrics."""

    num_components: int
    giant_component_size: int
    giant_component_fraction: float
    isolated_nodes_count: int

    def to_dict(self) -> dict:
        return {
            "num_components": self.num_components,
            "giant_component_size": self.giant_component_size,
            "giant_component_fraction": round(self.giant_component_fraction, 6),
            "isolated_nodes_count": self.isolated_nodes_count,
        }


@dataclass(frozen=True)
class PathStats:
    """Shortest path metrics on the Giant Connected Component."""

    average_path_length: float
    diameter: int
    radius: int

    def to_dict(self) -> dict:
        return {
            "average_path_length": round(self.average_path_length, 4),
            "diameter": self.diameter,
            "radius": self.radius,
        }


@dataclass(frozen=True)
class GlobalTopologyMetrics:
    """Comprehensive graph-theoretic metrics for the full inferred topology."""

    num_nodes: int
    num_edges: int
    density: float
    degree_stats: DegreeStats
    average_clustering_coefficient: float
    er_clustering_comparison: float
    component_stats: ComponentStats
    path_stats: PathStats | None

    def to_dict(self) -> dict:
        return {
            "num_nodes": self.num_nodes,
            "num_edges": self.num_edges,
            "density": round(self.density, 6),
            "degree_stats": self.degree_stats.to_dict(),
            "average_clustering_coefficient": round(self.average_clustering_coefficient, 6),
            "er_clustering_comparison": round(self.er_clustering_comparison, 6),
            "component_stats": self.component_stats.to_dict(),
            "path_stats": self.path_stats.to_dict() if self.path_stats else None,
        }


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregated evaluation report containing validation and full topology metrics."""

    validation: ValidationMetrics | None
    global_topology: GlobalTopologyMetrics
    timestamp: str
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "validation": self.validation.to_dict() if self.validation else None,
            "global_topology": self.global_topology.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> EvaluationReport:
        val_data = data.get("validation")
        validation = None
        if val_data:
            cm = ConfusionMatrix(**val_data["confusion_matrix"])
            validation = ValidationMetrics(
                confusion_matrix=cm,
                precision=float(val_data["precision"]),
                recall=float(val_data["recall"]),
                accuracy=float(val_data["accuracy"]),
                specificity=float(val_data["specificity"]),
                f1_score=float(val_data["f1_score"]),
                fpr=float(val_data["fpr"]),
                fnr=float(val_data["fnr"]),
                gt_edges_count=int(val_data["gt_edges_count"]),
                inferred_edges_count=int(val_data["inferred_edges_count"]),
                total_candidate_pairs=int(val_data["total_candidate_pairs"]),
                tp_edges=tuple(tuple(e) for e in val_data.get("tp_edges", ())),
                fp_edges=tuple(tuple(e) for e in val_data.get("fp_edges", ())),
                fn_edges=tuple(tuple(e) for e in val_data.get("fn_edges", ())),
            )

        gt_data = data["global_topology"]
        deg_data = gt_data["degree_stats"]
        degree_stats = DegreeStats(
            min_degree=int(deg_data["min_degree"]),
            max_degree=int(deg_data["max_degree"]),
            mean_degree=float(deg_data["mean_degree"]),
            median_degree=float(deg_data["median_degree"]),
            std_degree=float(deg_data["std_degree"]),
            degree_histogram=deg_data["degree_histogram"],
            top_hubs=tuple(
                (hub["addr"], int(hub["degree"])) for hub in deg_data["top_hubs"]
            ),
        )

        comp_data = gt_data["component_stats"]
        component_stats = ComponentStats(
            num_components=int(comp_data["num_components"]),
            giant_component_size=int(comp_data["giant_component_size"]),
            giant_component_fraction=float(comp_data["giant_component_fraction"]),
            isolated_nodes_count=int(comp_data["isolated_nodes_count"]),
        )

        path_data = gt_data.get("path_stats")
        path_stats = (
            PathStats(
                average_path_length=float(path_data["average_path_length"]),
                diameter=int(path_data["diameter"]),
                radius=int(path_data["radius"]),
            )
            if path_data
            else None
        )

        global_topology = GlobalTopologyMetrics(
            num_nodes=int(gt_data["num_nodes"]),
            num_edges=int(gt_data["num_edges"]),
            density=float(gt_data["density"]),
            degree_stats=degree_stats,
            average_clustering_coefficient=float(gt_data["average_clustering_coefficient"]),
            er_clustering_comparison=float(gt_data["er_clustering_comparison"]),
            component_stats=component_stats,
            path_stats=path_stats,
        )

        return cls(
            validation=validation,
            global_topology=global_topology,
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


def _extract_canonical_edges(
    graph: GraphSnapshot,
    allowed_nodes: set[str] | None = None,
    incident_to_nodes: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Extract set of unique canonical (lexicographically ordered) edges from graph."""
    unique_edges: set[tuple[str, str]] = set()
    for u, neighbors in graph.adj_list.items():
        if allowed_nodes is not None and u.addr not in allowed_nodes:
            continue
        for v in neighbors:
            if allowed_nodes is not None and v.addr not in allowed_nodes:
                continue
            if incident_to_nodes is not None:
                if u.addr not in incident_to_nodes and v.addr not in incident_to_nodes:
                    continue
            unique_edges.add(canonical_edge(u.addr, v.addr))
    return unique_edges


def compute_groundtruth_metrics(
    gt_graph: GraphSnapshot,
    inferred_graph: GraphSnapshot,
    groundtruth_nodes: set[str] | None = None,
) -> ValidationMetrics:
    """Compute binary classification validation metrics between groundtruth and inferred graphs."""
    gt_nodes = {n.addr for n in gt_graph.nodes}
    inf_nodes = {n.addr for n in inferred_graph.nodes}
    eval_nodes = gt_nodes.intersection(inf_nodes)

    gt_nodes_eval: set[str] | None = None
    if groundtruth_nodes is not None:
        matched = eval_nodes.intersection(groundtruth_nodes)
        if matched:
            gt_nodes_eval = matched

    if gt_nodes_eval is not None:
        g = len(gt_nodes_eval)
        n = len(eval_nodes)
        total_pairs = g * (n - g) + g * (g - 1) // 2
        gt_edges = _extract_canonical_edges(
            gt_graph, allowed_nodes=eval_nodes, incident_to_nodes=gt_nodes_eval
        )
        inf_edges = _extract_canonical_edges(
            inferred_graph, allowed_nodes=eval_nodes, incident_to_nodes=gt_nodes_eval
        )
    else:
        n = len(eval_nodes)
        total_pairs = n * (n - 1) // 2
        gt_edges = _extract_canonical_edges(gt_graph, allowed_nodes=eval_nodes)
        inf_edges = _extract_canonical_edges(inferred_graph, allowed_nodes=eval_nodes)

    tp_edges = gt_edges.intersection(inf_edges)
    fp_edges = inf_edges.difference(gt_edges)
    fn_edges = gt_edges.difference(inf_edges)

    tp = len(tp_edges)
    fp = len(fp_edges)
    fn = len(fn_edges)
    tn = max(0, total_pairs - (tp + fp + fn))

    precision = (tp / (tp + fp)) if (tp + fp) > 0 else (1.0 if len(gt_edges) == 0 else 0.0)
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0
    accuracy = ((tp + tn) / total_pairs) if total_pairs > 0 else 1.0
    specificity = (tn / (tn + fp)) if (tn + fp) > 0 else 1.0
    f1_score = (
        (2.0 * precision * recall / (precision + recall))
        if (precision + recall) > 0.0
        else 0.0
    )
    fpr = (fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    fnr = (fn / (tp + fn)) if (tp + fn) > 0 else 0.0

    return ValidationMetrics(
        confusion_matrix=ConfusionMatrix(tp=tp, fp=fp, tn=tn, fn=fn),
        precision=precision,
        recall=recall,
        accuracy=accuracy,
        specificity=specificity,
        f1_score=f1_score,
        fpr=fpr,
        fnr=fnr,
        gt_edges_count=len(gt_edges),
        inferred_edges_count=len(inf_edges),
        total_candidate_pairs=total_pairs,
        tp_edges=tuple(sorted(tp_edges)),
        fp_edges=tuple(sorted(fp_edges)),
        fn_edges=tuple(sorted(fn_edges)),
    )


def compute_degree_stats(graph: GraphSnapshot, top_k: int = 10) -> DegreeStats:
    """Compute degree summary statistics, histogram distribution, and hub detection."""
    degrees_by_node: dict[str, int] = {}
    for node in graph.nodes:
        degrees_by_node[node.addr] = len(graph.adj_list.get(node, ()))

    if not degrees_by_node:
        return DegreeStats(
            min_degree=0,
            max_degree=0,
            mean_degree=0.0,
            median_degree=0.0,
            std_degree=0.0,
            degree_histogram={},
            top_hubs=(),
        )

    degrees = list(degrees_by_node.values())
    min_deg = min(degrees)
    max_deg = max(degrees)
    mean_deg = statistics.mean(degrees)
    median_deg = statistics.median(degrees)
    std_deg = statistics.pstdev(degrees) if len(degrees) > 0 else 0.0

    histogram_buckets: dict[str, int] = {
        "0": 0,
        "1-2": 0,
        "3-5": 0,
        "6-8": 0,
        "9-12": 0,
        "13-20": 0,
        "21-50": 0,
        "51-100": 0,
        "101+": 0,
    }

    for d in degrees:
        if d == 0:
            histogram_buckets["0"] += 1
        elif 1 <= d <= 2:
            histogram_buckets["1-2"] += 1
        elif 3 <= d <= 5:
            histogram_buckets["3-5"] += 1
        elif 6 <= d <= 8:
            histogram_buckets["6-8"] += 1
        elif 9 <= d <= 12:
            histogram_buckets["9-12"] += 1
        elif 13 <= d <= 20:
            histogram_buckets["13-20"] += 1
        elif 21 <= d <= 50:
            histogram_buckets["21-50"] += 1
        elif 51 <= d <= 100:
            histogram_buckets["51-100"] += 1
        else:
            histogram_buckets["101+"] += 1

    sorted_hubs = sorted(
        degrees_by_node.items(), key=lambda item: (-item[1], item[0])
    )[:top_k]

    return DegreeStats(
        min_degree=min_deg,
        max_degree=max_deg,
        mean_degree=mean_deg,
        median_degree=median_deg,
        std_degree=std_deg,
        degree_histogram=histogram_buckets,
        top_hubs=tuple(sorted_hubs),
    )


def compute_clustering_coefficient(graph: GraphSnapshot) -> float:
    """Compute network average clustering coefficient C_avg."""
    if graph.num_nodes == 0:
        return 0.0

    # Build neighbor address sets for fast intersection
    neighbor_sets: dict[str, set[str]] = {
        node.addr: {p.addr for p in graph.adj_list.get(node, ())}
        for node in graph.nodes
    }

    total_c = 0.0
    for node in graph.nodes:
        nbrs = neighbor_sets[node.addr]
        k = len(nbrs)
        if k < 2:
            continue

        mutual_edges_count = 0
        for u in nbrs:
            mutual_edges_count += len(nbrs.intersection(neighbor_sets.get(u, ())))

        e_v = mutual_edges_count // 2
        total_c += (2.0 * e_v) / (k * (k - 1))

    return total_c / graph.num_nodes


def compute_connected_components(
    graph: GraphSnapshot,
) -> tuple[list[set[str]], ComponentStats]:
    """Identify connected components via BFS decomposition and summarize component metrics."""
    visited: set[str] = set()
    components: list[set[str]] = []

    adj: dict[str, list[str]] = {
        node.addr: [p.addr for p in graph.adj_list.get(node, ())]
        for node in graph.nodes
    }

    for node in graph.nodes:
        addr = node.addr
        if addr not in visited:
            comp: set[str] = set()
            queue = deque([addr])
            visited.add(addr)

            while queue:
                curr = queue.popleft()
                comp.add(curr)
                for neighbor in adj.get(curr, ()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            components.append(comp)

    components.sort(key=lambda c: len(c), reverse=True)

    giant_size = len(components[0]) if components else 0
    num_nodes = graph.num_nodes
    giant_fraction = (giant_size / num_nodes) if num_nodes > 0 else 0.0

    isolated_count = sum(
        1 for c in components if len(c) == 1 and len(adj.get(next(iter(c)), ())) == 0
    )

    stats = ComponentStats(
        num_components=len(components),
        giant_component_size=giant_size,
        giant_component_fraction=giant_fraction,
        isolated_nodes_count=isolated_count,
    )

    return components, stats


def compute_path_metrics(
    graph: GraphSnapshot, giant_nodes: set[str] | None = None
) -> PathStats:
    """Compute average shortest path length, diameter, and radius on the Giant Connected Component."""
    if giant_nodes is None:
        components, _ = compute_connected_components(graph)
        giant_nodes = components[0] if components else set()

    n = len(giant_nodes)
    if n <= 1:
        return PathStats(average_path_length=0.0, diameter=0, radius=0)

    adj: dict[str, list[str]] = {
        node.addr: [p.addr for p in graph.adj_list.get(node, ()) if p.addr in giant_nodes]
        for node in graph.nodes
        if node.addr in giant_nodes
    }

    total_path_length = 0
    max_eccentricity = 0
    min_eccentricity = math.inf

    sorted_giant = sorted(giant_nodes)

    for src in sorted_giant:
        distances: dict[str, int] = {src: 0}
        queue = deque([src])

        while queue:
            curr = queue.popleft()
            d = distances[curr]
            for nxt in adj.get(curr, ()):
                if nxt not in distances:
                    distances[nxt] = d + 1
                    queue.append(nxt)

        eccentricity = max(distances.values()) if distances else 0
        if eccentricity > max_eccentricity:
            max_eccentricity = eccentricity
        if eccentricity < min_eccentricity:
            min_eccentricity = eccentricity

        for dst, dist in distances.items():
            if src < dst:
                total_path_length += dist

    total_pairs = n * (n - 1) // 2
    avg_path = (total_path_length / total_pairs) if total_pairs > 0 else 0.0
    diameter = int(max_eccentricity)
    radius = int(min_eccentricity) if min_eccentricity != math.inf else 0

    return PathStats(
        average_path_length=avg_path,
        diameter=diameter,
        radius=radius,
    )


def compute_global_topology_metrics(
    graph: GraphSnapshot, compute_paths: bool = True
) -> GlobalTopologyMetrics:
    """Compute all graph-theoretic metrics for the full inferred network topology."""
    n = graph.num_nodes
    e = graph.num_edges
    total_possible_edges = n * (n - 1) // 2
    density = (e / total_possible_edges) if total_possible_edges > 0 else 0.0

    degree_stats = compute_degree_stats(graph)
    avg_clustering = compute_clustering_coefficient(graph)
    er_clustering = density  # In Erdős-Rényi random graph, C_ER ≈ p = density

    components, component_stats = compute_connected_components(graph)

    path_stats: PathStats | None = None
    if compute_paths and component_stats.giant_component_size > 1:
        path_stats = compute_path_metrics(graph, giant_nodes=components[0])

    return GlobalTopologyMetrics(
        num_nodes=n,
        num_edges=e,
        density=density,
        degree_stats=degree_stats,
        average_clustering_coefficient=avg_clustering,
        er_clustering_comparison=er_clustering,
        component_stats=component_stats,
        path_stats=path_stats,
    )


def evaluate_reconciled_results(
    data: dict, compute_paths: bool = True
) -> EvaluationReport:
    """Generate complete EvaluationReport from Step 5 reconciled_topology.json or result dict."""
    full_inferred_dict = data.get("full_inferred_topology")
    if not full_inferred_dict:
        raise ValueError("Missing 'full_inferred_topology' in evaluation input data")

    full_graph = GraphSnapshot.from_dict(full_inferred_dict)
    global_metrics = compute_global_topology_metrics(
        full_graph, compute_paths=compute_paths
    )

    validation_metrics: ValidationMetrics | None = None
    gt_dict = data.get("reconciled_groundtruth")
    eval_dict = data.get("evaluation_inferred_topology")

    if gt_dict and eval_dict:
        gt_graph = GraphSnapshot.from_dict(gt_dict)
        eval_graph = GraphSnapshot.from_dict(eval_dict)
        gt_nodes_raw = data.get("groundtruth_identities", [])
        gt_nodes_set: set[str] | None = None
        if gt_nodes_raw:
            gt_nodes_set = {str(a) for a in gt_nodes_raw}
        validation_metrics = compute_groundtruth_metrics(
            gt_graph, eval_graph, groundtruth_nodes=gt_nodes_set
        )

    stats_meta = data.get("stats", {})
    return EvaluationReport(
        validation=validation_metrics,
        global_topology=global_metrics,
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={
            "step": "step_6_evaluation",
            "source_nodes_count": len(full_graph.nodes),
            "reconciliation_stats": stats_meta,
        },
    )


def generate_markdown_report(report: EvaluationReport) -> str:
    """Render comprehensive executive Markdown report of evaluation results."""
    lines: list[str] = [
        "# TxProbe Network Topology Evaluation Report",
        "",
        f"**Generated**: {report.timestamp}  ",
        "**Target Network**: Bitcoin Testnet4  ",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        f"- **Inferred Network Scale**: **{report.global_topology.num_nodes}** surviving nodes and **{report.global_topology.num_edges}** active undirected edges.",
        f"- **Network Density**: **{report.global_topology.density:.6f}** (sparse decentralized P2P topology).",
        f"- **Average Node Degree**: **{report.global_topology.degree_stats.mean_degree:.2f}** (median: {report.global_topology.degree_stats.median_degree:.1f}, std: {report.global_topology.degree_stats.std_degree:.2f}).",
        f"- **Average Clustering Coefficient**: **{report.global_topology.average_clustering_coefficient:.4f}** (vs. Erdős–Rényi baseline: {report.global_topology.er_clustering_comparison:.4f}).",
    ]

    if report.global_topology.path_stats:
        lines.append(
            f"- **Giant Component Average Path Length**: **{report.global_topology.path_stats.average_path_length:.2f}** hops (Diameter: {report.global_topology.path_stats.diameter}, Radius: {report.global_topology.path_stats.radius})."
        )

    if report.validation:
        lines.extend([
            "",
            "### Groundtruth Validation Summary",
            "",
            f"- **Precision**: **{report.validation.precision * 100:.2f}%**",
            f"- **Recall (Sensitivity)**: **{report.validation.recall * 100:.2f}%**",
            f"- **Accuracy**: **{report.validation.accuracy * 100:.2f}%**",
            f"- **F1-Score**: **{report.validation.f1_score:.4f}**",
            f"- **Specificity**: **{report.validation.specificity * 100:.2f}%**",
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 2. Groundtruth Validation Metrics",
        "",
    ])

    if report.validation:
        cm = report.validation.confusion_matrix
        lines.extend([
            "### 2.1 Confusion Matrix",
            "",
            "| Metric | Count | Description |",
            "|---|---|---|",
            f"| **True Positives (TP)** | `{cm.tp}` | Genuine edges correctly inferred by TxProbe |",
            f"| **False Positives (FP)** | `{cm.fp}` | Non-existent connections falsely inferred |",
            f"| **True Negatives (TN)** | `{cm.tn}` | Non-connected pairs correctly discarded |",
            f"| **False Negatives (FN)** | `{cm.fn}` | Real groundtruth edges erroneously missed |",
            f"| **Total Candidate Pairs** | `{report.validation.total_candidate_pairs}` | All possible undirected pairs in groundtruth slice |",
            "",
            "### 2.2 Classification Scores",
            "",
            "| Metric | Formula | Value |",
            "|---|---|---|",
            f"| **Precision** | `TP / (TP + FP)` | **{report.validation.precision:.4f}** ({report.validation.precision * 100:.2f}%) |",
            f"| **Recall (Sensitivity)** | `TP / (TP + FN)` | **{report.validation.recall:.4f}** ({report.validation.recall * 100:.2f}%) |",
            f"| **Accuracy** | `(TP + TN) / Total` | **{report.validation.accuracy:.4f}** ({report.validation.accuracy * 100:.2f}%) |",
            f"| **Specificity** | `TN / (TN + FP)` | **{report.validation.specificity:.4f}** ({report.validation.specificity * 100:.2f}%) |",
            f"| **F1-Score** | `2 * (P * R) / (P + R)` | **{report.validation.f1_score:.4f}** |",
            f"| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **{report.validation.fpr:.4f}** |",
            f"| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **{report.validation.fnr:.4f}** |",
        ])
    else:
        lines.append("*Groundtruth validation slice was not provided or evaluated.*")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Global Network Topology Characterization",
        "",
        "### 3.1 Graph Scale & Degree Distribution",
        "",
        "| Property | Value | Notes |",
        "|---|---|---|",
        f"| **Total Nodes (|V|)** | `{report.global_topology.num_nodes}` | Active surviving peers |",
        f"| **Total Edges (|E|)** | `{report.global_topology.num_edges}` | Undirected P2P connections |",
        f"| **Minimum Degree** | `{report.global_topology.degree_stats.min_degree}` | Minimum connections for any single node |",
        f"| **Maximum Degree** | `{report.global_topology.degree_stats.max_degree}` | Most connected node in the network |",
        f"| **Mean Degree** | `{report.global_topology.degree_stats.mean_degree:.2f}` | Expected degree per node |",
        f"| **Median Degree** | `{report.global_topology.degree_stats.median_degree:.1f}` | Median degree across nodes |",
        f"| **Standard Deviation** | `{report.global_topology.degree_stats.std_degree:.2f}` | Degree dispersion |",
        f"| **Graph Density** | `{report.global_topology.density:.6f}` | 2|E| / (|V|(|V|-1)) |",
        "",
        "### 3.2 Degree Distribution Histogram",
        "",
        "| Degree Bucket | Node Count | Percentage |",
        "|---|---|---|",
    ])

    total_n = max(1, report.global_topology.num_nodes)
    for bucket, count in report.global_topology.degree_stats.degree_histogram.items():
        pct = (count / total_n) * 100.0
        lines.append(f"| `{bucket}` | `{count}` | {pct:.1f}% |")

    lines.extend([
        "",
        "### 3.3 Top Network Hubs (Supernodes)",
        "",
        "| Rank | Node Address | Degree |",
        "|---|---|---|",
    ])

    if report.global_topology.degree_stats.top_hubs:
        for idx, (addr, deg) in enumerate(
            report.global_topology.degree_stats.top_hubs, start=1
        ):
            lines.append(f"| {idx} | `{addr}` | `{deg}` |")
    else:
        lines.append("| - | *No hubs detected* | 0 |")

    lines.extend([
        "",
        "### 3.4 Connectivity, Small-World & Clustering Properties",
        "",
        "| Metric | Empirical Value | Theoretical Context |",
        "|---|---|---|",
        f"| **Number of Components** | `{report.global_topology.component_stats.num_components}` | Number of disconnected sub-graphs |",
        f"| **Giant Component Size** | `{report.global_topology.component_stats.giant_component_size}` | `{report.global_topology.component_stats.giant_component_fraction * 100:.1f}%` of total network |",
        f"| **Isolated Nodes** | `{report.global_topology.component_stats.isolated_nodes_count}` | Nodes with degree 0 |",
        f"| **Average Clustering (C_avg)** | `{report.global_topology.average_clustering_coefficient:.4f}` | Local triadic closure |",
        f"| **Erdős–Rényi Clustering (C_ER)** | `{report.global_topology.er_clustering_comparison:.4f}` | Random graph reference baseline |",
    ])

    if report.global_topology.path_stats:
        ps = report.global_topology.path_stats
        lines.extend([
            f"| **Average Shortest Path** | `{ps.average_path_length:.2f}` hops | Characteristic path length |",
            f"| **Network Diameter** | `{ps.diameter}` hops | Maximum shortest path |",
            f"| **Network Radius** | `{ps.radius}` hops | Minimum node eccentricity |",
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 4. Architectural Analysis & Bitcoin P2P Dynamics",
        "",
        "- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.",
        "- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.",
        "- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.",
        "",
    ])

    return "\n".join(lines)
