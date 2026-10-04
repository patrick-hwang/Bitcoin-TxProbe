# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-04T19:17:13.386411+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **163** surviving nodes and **1289** active undirected edges.
- **Network Density**: **0.097629** (sparse decentralized P2P topology).
- **Average Node Degree**: **15.82** (median: 13.0, std: 9.92).
- **Average Clustering Coefficient**: **0.2056** (vs. Erdős–Rényi baseline: 0.0976).
- **Giant Component Average Path Length**: **2.17** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **76.00%**
- **Recall (Sensitivity)**: **82.61%**
- **Accuracy**: **98.44%**
- **F1-Score**: **0.7917**
- **Specificity**: **99.03%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `19` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `6` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `613` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `4` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `642` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.7600** (76.00%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.8261** (82.61%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9844** (98.44%) |
| **Specificity** | `TN / (TN + FP)` | **0.9903** (99.03%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.7917** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0097** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.1739** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `163` | Active surviving peers |
| **Total Edges (|E|)** | `1289` | Undirected P2P connections |
| **Minimum Degree** | `4` | Minimum connections for any single node |
| **Maximum Degree** | `51` | Most connected node in the network |
| **Mean Degree** | `15.82` | Expected degree per node |
| **Median Degree** | `13.0` | Median degree across nodes |
| **Standard Deviation** | `9.92` | Degree dispersion |
| **Graph Density** | `0.097629` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `6` | 3.7% |
| `6-8` | `35` | 21.5% |
| `9-12` | `40` | 24.5% |
| `13-20` | `40` | 24.5% |
| `21-50` | `41` | 25.2% |
| `51-100` | `1` | 0.6% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `103.99.171.201:48333` | `51` |
| 2 | `209.146.50.202:48333` | `49` |
| 3 | `193.30.123.70:48333` | `46` |
| 4 | `116.203.184.251:48333` | `41` |
| 5 | `34.31.40.200:48333` | `39` |
| 6 | `89.117.50.252:48333` | `39` |
| 7 | `103.99.170.201:48333` | `38` |
| 8 | `185.18.221.19:48333` | `38` |
| 9 | `103.99.170.202:48333` | `37` |
| 10 | `72.179.148.45:48333` | `37` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `163` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.2056` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0976` | Random graph reference baseline |
| **Average Shortest Path** | `2.17` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
