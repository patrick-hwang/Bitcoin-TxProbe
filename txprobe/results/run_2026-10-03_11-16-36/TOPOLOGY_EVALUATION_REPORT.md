# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-03T05:18:26.561210+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **158** surviving nodes and **1012** active undirected edges.
- **Network Density**: **0.081593** (sparse decentralized P2P topology).
- **Average Node Degree**: **12.81** (median: 11.0, std: 7.44).
- **Average Clustering Coefficient**: **0.1567** (vs. Erdős–Rényi baseline: 0.0816).
- **Giant Component Average Path Length**: **2.28** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **1.58%**
- **Recall (Sensitivity)**: **88.89%**
- **Accuracy**: **91.95%**
- **F1-Score**: **0.0311**
- **Specificity**: **91.96%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `16` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `996` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `11389` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `2` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `12403` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.0158** (1.58%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.8889** (88.89%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9195** (91.95%) |
| **Specificity** | `TN / (TN + FP)` | **0.9196** (91.96%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.0311** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0804** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.1111** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `158` | Active surviving peers |
| **Total Edges (|E|)** | `1012` | Undirected P2P connections |
| **Minimum Degree** | `4` | Minimum connections for any single node |
| **Maximum Degree** | `39` | Most connected node in the network |
| **Mean Degree** | `12.81` | Expected degree per node |
| **Median Degree** | `11.0` | Median degree across nodes |
| **Standard Deviation** | `7.44` | Degree dispersion |
| **Graph Density** | `0.081593` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `22` | 13.9% |
| `6-8` | `40` | 25.3% |
| `9-12` | `26` | 16.5% |
| `13-20` | `46` | 29.1% |
| `21-50` | `24` | 15.2% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `103.99.170.201:48333` | `39` |
| 2 | `209.146.50.202:48333` | `36` |
| 3 | `209.146.50.204:48333` | `35` |
| 4 | `103.99.170.202:48333` | `34` |
| 5 | `103.99.171.201:48333` | `32` |
| 6 | `209.146.50.203:48333` | `31` |
| 7 | `103.99.170.203:48333` | `28` |
| 8 | `176.169.208.187:48333` | `26` |
| 9 | `54.180.113.82:8333` | `26` |
| 10 | `52.1.114.214:48333` | `25` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `158` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.1567` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0816` | Random graph reference baseline |
| **Average Shortest Path** | `2.28` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
