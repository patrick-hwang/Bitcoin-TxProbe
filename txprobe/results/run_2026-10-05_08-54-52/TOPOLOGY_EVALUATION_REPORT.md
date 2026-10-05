# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-05T02:16:04.859379+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **155** surviving nodes and **1364** active undirected edges.
- **Network Density**: **0.114286** (sparse decentralized P2P topology).
- **Average Node Degree**: **17.60** (median: 14.0, std: 11.60).
- **Average Clustering Coefficient**: **0.2614** (vs. Erdős–Rényi baseline: 0.1143).
- **Giant Component Average Path Length**: **2.12** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **60.00%**
- **Recall (Sensitivity)**: **90.00%**
- **Accuracy**: **97.72%**
- **F1-Score**: **0.7200**
- **Specificity**: **97.98%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `9` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `6` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `291` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `1` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `307` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.6000** (60.00%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.9000** (90.00%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9772** (97.72%) |
| **Specificity** | `TN / (TN + FP)` | **0.9798** (97.98%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.7200** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0202** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.1000** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `155` | Active surviving peers |
| **Total Edges (|E|)** | `1364` | Undirected P2P connections |
| **Minimum Degree** | `2` | Minimum connections for any single node |
| **Maximum Degree** | `69` | Most connected node in the network |
| **Mean Degree** | `17.60` | Expected degree per node |
| **Median Degree** | `14.0` | Median degree across nodes |
| **Standard Deviation** | `11.60` | Degree dispersion |
| **Graph Density** | `0.114286` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `1` | 0.6% |
| `3-5` | `6` | 3.9% |
| `6-8` | `30` | 19.4% |
| `9-12` | `32` | 20.6% |
| `13-20` | `41` | 26.5% |
| `21-50` | `44` | 28.4% |
| `51-100` | `1` | 0.6% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `103.99.171.201:48333` | `69` |
| 2 | `193.30.123.70:48333` | `45` |
| 3 | `65.108.141.219:48333` | `45` |
| 4 | `13.140.162.77:48333` | `43` |
| 5 | `54.78.82.55:48333` | `43` |
| 6 | `89.117.50.252:48333` | `43` |
| 7 | `185.18.221.19:48333` | `42` |
| 8 | `103.165.192.211:48333` | `41` |
| 9 | `103.99.170.201:48333` | `41` |
| 10 | `65.109.112.186:48444` | `41` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `155` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.2614` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.1143` | Random graph reference baseline |
| **Average Shortest Path** | `2.12` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
