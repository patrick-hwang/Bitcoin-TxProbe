# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-02T13:18:49.104834+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **25** surviving nodes and **30** active undirected edges.
- **Network Density**: **0.100000** (sparse decentralized P2P topology).
- **Average Node Degree**: **2.40** (median: 2.0, std: 1.72).
- **Average Clustering Coefficient**: **0.0352** (vs. Erdős–Rényi baseline: 0.1000).
- **Giant Component Average Path Length**: **3.31** hops (Diameter: 8, Radius: 4).

### Groundtruth Validation Summary

- **Precision**: **53.33%**
- **Recall (Sensitivity)**: **88.89%**
- **Accuracy**: **94.67%**
- **F1-Score**: **0.6667**
- **Specificity**: **95.04%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `16` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `14` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `268` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `2` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `300` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.5333** (53.33%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.8889** (88.89%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9467** (94.67%) |
| **Specificity** | `TN / (TN + FP)` | **0.9504** (95.04%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.6667** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0496** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.1111** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `25` | Active surviving peers |
| **Total Edges (|E|)** | `30` | Undirected P2P connections |
| **Minimum Degree** | `0` | Minimum connections for any single node |
| **Maximum Degree** | `7` | Most connected node in the network |
| **Mean Degree** | `2.40` | Expected degree per node |
| **Median Degree** | `2.0` | Median degree across nodes |
| **Standard Deviation** | `1.72` | Degree dispersion |
| **Graph Density** | `0.100000` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `2` | 8.0% |
| `1-2` | `13` | 52.0% |
| `3-5` | `8` | 32.0% |
| `6-8` | `2` | 8.0% |
| `9-12` | `0` | 0.0% |
| `13-20` | `0` | 0.0% |
| `21-50` | `0` | 0.0% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `upiuurfhixst6z5gbif6eziw4dush2wtfjy6tcpbkycqkra5trb575id.onion:48333` | `7` |
| 2 | `b6yjsgsx3jbzxosfu3gsnbih4hmt3nspizetslm7ok6wfvsrylv3ysqd.onion:48333` | `6` |
| 3 | `13.140.162.77:48333` | `5` |
| 4 | `65.108.141.219:48333` | `4` |
| 5 | `89.58.9.219:48333` | `4` |
| 6 | `13.57.190.12:48333` | `3` |
| 7 | `134.199.227.217:48333` | `3` |
| 8 | `136.49.112.63:47333` | `3` |
| 9 | `89.117.50.252:48333` | `3` |
| 10 | `pnvbolsqnqmiwbmrrtqoz3cbfwvnrhdesn3wxbvimifvhs2c5r5z5uad.onion:48333` | `3` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `3` | Number of disconnected sub-graphs |
| **Giant Component Size** | `23` | `92.0%` of total network |
| **Isolated Nodes** | `2` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.0352` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.1000` | Random graph reference baseline |
| **Average Shortest Path** | `3.31` hops | Characteristic path length |
| **Network Diameter** | `8` hops | Maximum shortest path |
| **Network Radius** | `4` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
