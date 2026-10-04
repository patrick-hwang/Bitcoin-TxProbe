# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-04T15:17:16.752309+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **177** surviving nodes and **1524** active undirected edges.
- **Network Density**: **0.097843** (sparse decentralized P2P topology).
- **Average Node Degree**: **17.22** (median: 14.0, std: 11.88).
- **Average Clustering Coefficient**: **0.2154** (vs. Erdős–Rényi baseline: 0.0978).
- **Giant Component Average Path Length**: **2.18** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **1.18%**
- **Recall (Sensitivity)**: **85.71%**
- **Accuracy**: **90.31%**
- **F1-Score**: **0.0233**
- **Specificity**: **90.32%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `18` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `1506` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `14049` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `3` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `15576` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.0118** (1.18%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.8571** (85.71%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9031** (90.31%) |
| **Specificity** | `TN / (TN + FP)` | **0.9032** (90.32%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.0233** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0968** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.1429** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `177` | Active surviving peers |
| **Total Edges (|E|)** | `1524` | Undirected P2P connections |
| **Minimum Degree** | `0` | Minimum connections for any single node |
| **Maximum Degree** | `56` | Most connected node in the network |
| **Mean Degree** | `17.22` | Expected degree per node |
| **Median Degree** | `14.0` | Median degree across nodes |
| **Standard Deviation** | `11.88` | Degree dispersion |
| **Graph Density** | `0.097843` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `1` | 0.6% |
| `1-2` | `1` | 0.6% |
| `3-5` | `15` | 8.5% |
| `6-8` | `32` | 18.1% |
| `9-12` | `30` | 16.9% |
| `13-20` | `44` | 24.9% |
| `21-50` | `50` | 28.2% |
| `51-100` | `4` | 2.3% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `209.146.50.202:48333` | `56` |
| 2 | `176.169.208.187:48333` | `55` |
| 3 | `193.30.123.70:48333` | `53` |
| 4 | `209.146.50.203:48333` | `53` |
| 5 | `13.140.162.77:48333` | `46` |
| 6 | `103.99.171.211:48333` | `43` |
| 7 | `34.31.40.200:48333` | `43` |
| 8 | `92.118.190.35:48333` | `43` |
| 9 | `103.99.170.201:48333` | `42` |
| 10 | `185.18.221.19:48333` | `41` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `2` | Number of disconnected sub-graphs |
| **Giant Component Size** | `176` | `99.4%` of total network |
| **Isolated Nodes** | `1` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.2154` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0978` | Random graph reference baseline |
| **Average Shortest Path** | `2.18` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
