# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-12T15:39:02.036727+00:00  
**Target Network**: Bitcoin RegTest  

---

## 1. Executive Summary

- **Inferred Network Scale**: **1000** surviving nodes and **3962** active undirected edges.
- **Network Density**: **0.007932** (sparse decentralized P2P topology).
- **Average Node Degree**: **7.92** (median: 8.0, std: 0.43).
- **Average Clustering Coefficient**: **0.0066** (vs. Erdős–Rényi baseline: 0.0079).
- **Giant Component Average Path Length**: **3.61** hops (Diameter: 5, Radius: 5).

### Groundtruth Validation Summary

- **Precision**: **99.90%**
- **Recall (Sensitivity)**: **98.83%**
- **Accuracy**: **99.99%**
- **F1-Score**: **0.9936**
- **Specificity**: **100.00%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `3958` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `4` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `495491` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `47` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `499500` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.9990** (99.90%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.9883** (98.83%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9999** (99.99%) |
| **Specificity** | `TN / (TN + FP)` | **1.0000** (100.00%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.9936** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0000** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0117** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `1000` | Active surviving peers |
| **Total Edges (|E|)** | `3962` | Undirected P2P connections |
| **Minimum Degree** | `5` | Minimum connections for any single node |
| **Maximum Degree** | `15` | Most connected node in the network |
| **Mean Degree** | `7.92` | Expected degree per node |
| **Median Degree** | `8.0` | Median degree across nodes |
| **Standard Deviation** | `0.43` | Degree dispersion |
| **Graph Density** | `0.007932` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `2` | 0.2% |
| `6-8` | `989` | 98.9% |
| `9-12` | `8` | 0.8% |
| `13-20` | `1` | 0.1% |
| `21-50` | `0` | 0.0% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `127.0.0.1:10864` | `15` |
| 2 | `127.0.0.1:10197` | `12` |
| 3 | `127.0.0.1:10147` | `9` |
| 4 | `127.0.0.1:10161` | `9` |
| 5 | `127.0.0.1:10635` | `9` |
| 6 | `127.0.0.1:10846` | `9` |
| 7 | `127.0.0.1:10876` | `9` |
| 8 | `127.0.0.1:10897` | `9` |
| 9 | `127.0.0.1:10997` | `9` |
| 10 | `127.0.0.1:10002` | `8` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `1000` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.0066` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0079` | Random graph reference baseline |
| **Average Shortest Path** | `3.61` hops | Characteristic path length |
| **Network Diameter** | `5` hops | Maximum shortest path |
| **Network Radius** | `5` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
