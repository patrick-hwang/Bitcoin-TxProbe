# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-05T04:23:03.044857+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **167** surviving nodes and **1386** active undirected edges.
- **Network Density**: **0.099993** (sparse decentralized P2P topology).
- **Average Node Degree**: **16.60** (median: 14.0, std: 9.01).
- **Average Clustering Coefficient**: **0.2039** (vs. Erdős–Rényi baseline: 0.1000).
- **Giant Component Average Path Length**: **2.14** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **88.24%**
- **Recall (Sensitivity)**: **78.95%**
- **Accuracy**: **98.79%**
- **F1-Score**: **0.8333**
- **Specificity**: **99.58%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `15` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `2` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `474` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `4` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `495` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.8824** (88.24%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.7895** (78.95%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9879** (98.79%) |
| **Specificity** | `TN / (TN + FP)` | **0.9958** (99.58%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.8333** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0042** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.2105** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `167` | Active surviving peers |
| **Total Edges (|E|)** | `1386` | Undirected P2P connections |
| **Minimum Degree** | `3` | Minimum connections for any single node |
| **Maximum Degree** | `50` | Most connected node in the network |
| **Mean Degree** | `16.60` | Expected degree per node |
| **Median Degree** | `14.0` | Median degree across nodes |
| **Standard Deviation** | `9.01` | Degree dispersion |
| **Graph Density** | `0.099993` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `8` | 4.8% |
| `6-8` | `23` | 13.8% |
| `9-12` | `36` | 21.6% |
| `13-20` | `52` | 31.1% |
| `21-50` | `48` | 28.7% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `vizb74h32bx3u6zksgsi6seq6hcqdhok5pd4z2x5yj3ll72tu7pcu7id.onion:48333` | `50` |
| 2 | `103.99.171.201:48333` | `48` |
| 3 | `103.99.170.201:48333` | `46` |
| 4 | `zdh7vrzykdv7474yioe5jiv3kgajky727t5phxsbt47lefjseo3ypaqd.onion:48333` | `40` |
| 5 | `116.203.184.251:48333` | `38` |
| 6 | `185.18.221.19:48333` | `37` |
| 7 | `103.99.171.211:48333` | `36` |
| 8 | `3.235.188.91:48333` | `36` |
| 9 | `34.31.40.200:48333` | `36` |
| 10 | `176.169.208.187:48333` | `34` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `167` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.2039` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.1000` | Random graph reference baseline |
| **Average Shortest Path** | `2.14` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
