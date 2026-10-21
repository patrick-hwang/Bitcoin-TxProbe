# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-19T15:58:28.718903+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **154** surviving nodes and **1762** active undirected edges.
- **Network Density**: **0.149563** (sparse decentralized P2P topology).
- **Average Node Degree**: **22.88** (median: 17.0, std: 16.66).
- **Average Clustering Coefficient**: **0.3216** (vs. Erdős–Rényi baseline: 0.1496).
- **Giant Component Average Path Length**: **2.02** hops (Diameter: 4, Radius: 2).

### Groundtruth Validation Summary

- **Precision**: **0.00%**
- **Recall (Sensitivity)**: **NULL**
- **Accuracy**: **85.04%**
- **F1-Score**: **NULL**
- **Specificity**: **85.04%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `0` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `1762` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `10019` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `0` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `11781` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.0000** (0.00%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **NULL** |
| **Accuracy** | `(TP + TN) / Total` | **0.8504** (85.04%) |
| **Specificity** | `TN / (TN + FP)` | **0.8504** (85.04%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **NULL** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.1496** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0000** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `154` | Active surviving peers |
| **Total Edges (|E|)** | `1762` | Undirected P2P connections |
| **Minimum Degree** | `4` | Minimum connections for any single node |
| **Maximum Degree** | `64` | Most connected node in the network |
| **Mean Degree** | `22.88` | Expected degree per node |
| **Median Degree** | `17.0` | Median degree across nodes |
| **Standard Deviation** | `16.66` | Degree dispersion |
| **Graph Density** | `0.149563` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `4` | 2.6% |
| `6-8` | `22` | 14.3% |
| `9-12` | `30` | 19.5% |
| `13-20` | `43` | 27.9% |
| `21-50` | `41` | 26.6% |
| `51-100` | `14` | 9.1% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `103.99.171.202:48333` | `64` |
| 2 | `44.210.35.117:48333` | `63` |
| 3 | `77.90.35.156:48333` | `59` |
| 4 | `116.203.184.251:48333` | `56` |
| 5 | `a6yijgwn4vtmmhl7uybtbuyvtl7mtj7arld5f4csqsx4syeii4gt3vqd.onion:48333` | `55` |
| 6 | `157.180.32.177:48333` | `53` |
| 7 | `188.132.178.33:48333` | `53` |
| 8 | `44.228.181.244:48333` | `53` |
| 9 | `51.158.61.33:48333` | `53` |
| 10 | `5.182.4.106:48333` | `52` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `154` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.3216` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.1496` | Random graph reference baseline |
| **Average Shortest Path** | `2.02` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `2` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
