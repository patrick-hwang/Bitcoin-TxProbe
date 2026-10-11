# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-11T08:04:31.070050+00:00  
**Target Network**: Bitcoin RegTest  

---

## 1. Executive Summary

- **Inferred Network Scale**: **100** surviving nodes and **402** active undirected edges.
- **Network Density**: **0.081212** (sparse decentralized P2P topology).
- **Average Node Degree**: **8.04** (median: 8.0, std: 0.20).
- **Average Clustering Coefficient**: **0.0528** (vs. Erdős–Rényi baseline: 0.0812).
- **Giant Component Average Path Length**: **2.41** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **99.50%**
- **Recall (Sensitivity)**: **100.00%**
- **Accuracy**: **99.96%**
- **F1-Score**: **0.9975**
- **Specificity**: **99.96%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `400` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `2` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `4548` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `0` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `4950` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.9950** (99.50%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **1.0000** (100.00%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9996** (99.96%) |
| **Specificity** | `TN / (TN + FP)` | **0.9996** (99.96%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.9975** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0004** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0000** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `100` | Active surviving peers |
| **Total Edges (|E|)** | `402` | Undirected P2P connections |
| **Minimum Degree** | `8` | Minimum connections for any single node |
| **Maximum Degree** | `9` | Most connected node in the network |
| **Mean Degree** | `8.04` | Expected degree per node |
| **Median Degree** | `8.0` | Median degree across nodes |
| **Standard Deviation** | `0.20` | Degree dispersion |
| **Graph Density** | `0.081212` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `0` | 0.0% |
| `6-8` | `96` | 96.0% |
| `9-12` | `4` | 4.0% |
| `13-20` | `0` | 0.0% |
| `21-50` | `0` | 0.0% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `127.0.0.1:18482` | `9` |
| 2 | `127.0.0.1:18498` | `9` |
| 3 | `127.0.0.1:18505` | `9` |
| 4 | `127.0.0.1:18542` | `9` |
| 5 | `127.0.0.1:18446` | `8` |
| 6 | `127.0.0.1:18447` | `8` |
| 7 | `127.0.0.1:18448` | `8` |
| 8 | `127.0.0.1:18449` | `8` |
| 9 | `127.0.0.1:18450` | `8` |
| 10 | `127.0.0.1:18451` | `8` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `100` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.0528` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0812` | Random graph reference baseline |
| **Average Shortest Path** | `2.41` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
