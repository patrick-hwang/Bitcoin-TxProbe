# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-15T12:00:54.208890+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **151** surviving nodes and **1277** active undirected edges.
- **Network Density**: **0.112759** (sparse decentralized P2P topology).
- **Average Node Degree**: **16.91** (median: 15.0, std: 8.03).
- **Average Clustering Coefficient**: **0.1855** (vs. Erdős–Rényi baseline: 0.1128).
- **Giant Component Average Path Length**: **2.09** hops (Diameter: 3, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **0.00%**
- **Recall (Sensitivity)**: **NULL**
- **Accuracy**: **88.72%**
- **F1-Score**: **NULL**
- **Specificity**: **88.72%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `0` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `1277` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `10048` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `0` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `11325` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.0000** (0.00%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **NULL** |
| **Accuracy** | `(TP + TN) / Total` | **0.8872** (88.72%) |
| **Specificity** | `TN / (TN + FP)` | **0.8872** (88.72%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **NULL** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.1128** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0000** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `151` | Active surviving peers |
| **Total Edges (|E|)** | `1277` | Undirected P2P connections |
| **Minimum Degree** | `5` | Minimum connections for any single node |
| **Maximum Degree** | `38` | Most connected node in the network |
| **Mean Degree** | `16.91` | Expected degree per node |
| **Median Degree** | `15.0` | Median degree across nodes |
| **Standard Deviation** | `8.03` | Degree dispersion |
| **Graph Density** | `0.112759` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `4` | 2.6% |
| `6-8` | `20` | 13.2% |
| `9-12` | `26` | 17.2% |
| `13-20` | `55` | 36.4% |
| `21-50` | `46` | 30.5% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `52.1.114.214:48333` | `38` |
| 2 | `103.99.169.208:48333` | `35` |
| 3 | `157.180.32.177:48333` | `35` |
| 4 | `103.99.168.211:48333` | `33` |
| 5 | `103.99.171.201:48333` | `33` |
| 6 | `103.99.171.209:48333` | `33` |
| 7 | `103.99.171.202:48333` | `32` |
| 8 | `3.135.25.32:48333` | `32` |
| 9 | `3.69.160.185:48333` | `32` |
| 10 | `34.228.207.112:48333` | `32` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `151` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.1855` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.1128` | Random graph reference baseline |
| **Average Shortest Path** | `2.09` hops | Characteristic path length |
| **Network Diameter** | `3` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
