# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-11T08:50:21.108384+00:00  
**Target Network**: Bitcoin RegTest  

---

## 1. Executive Summary

- **Inferred Network Scale**: **200** surviving nodes and **787** active undirected edges.
- **Network Density**: **0.039548** (sparse decentralized P2P topology).
- **Average Node Degree**: **7.87** (median: 8.0, std: 0.34).
- **Average Clustering Coefficient**: **0.0300** (vs. Erdős–Rényi baseline: 0.0395).
- **Giant Component Average Path Length**: **2.78** hops (Diameter: 4, Radius: 4).

### Groundtruth Validation Summary

- **Precision**: **100.00%**
- **Recall (Sensitivity)**: **98.38%**
- **Accuracy**: **99.93%**
- **F1-Score**: **0.9918**
- **Specificity**: **100.00%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `787` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `0` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `19100` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `13` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `19900` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **1.0000** (100.00%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.9838** (98.38%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9993** (99.93%) |
| **Specificity** | `TN / (TN + FP)` | **1.0000** (100.00%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.9918** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0000** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0163** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `200` | Active surviving peers |
| **Total Edges (|E|)** | `787` | Undirected P2P connections |
| **Minimum Degree** | `7` | Minimum connections for any single node |
| **Maximum Degree** | `8` | Most connected node in the network |
| **Mean Degree** | `7.87` | Expected degree per node |
| **Median Degree** | `8.0` | Median degree across nodes |
| **Standard Deviation** | `0.34` | Degree dispersion |
| **Graph Density** | `0.039548` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `0` | 0.0% |
| `6-8` | `200` | 100.0% |
| `9-12` | `0` | 0.0% |
| `13-20` | `0` | 0.0% |
| `21-50` | `0` | 0.0% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `127.0.0.1:18447` | `8` |
| 2 | `127.0.0.1:18448` | `8` |
| 3 | `127.0.0.1:18450` | `8` |
| 4 | `127.0.0.1:18453` | `8` |
| 5 | `127.0.0.1:18454` | `8` |
| 6 | `127.0.0.1:18455` | `8` |
| 7 | `127.0.0.1:18456` | `8` |
| 8 | `127.0.0.1:18457` | `8` |
| 9 | `127.0.0.1:18458` | `8` |
| 10 | `127.0.0.1:18459` | `8` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `200` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.0300` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0395` | Random graph reference baseline |
| **Average Shortest Path** | `2.78` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `4` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
