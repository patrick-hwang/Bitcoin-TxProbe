# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-03T13:45:21.801872+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **167** surviving nodes and **1213** active undirected edges.
- **Network Density**: **0.087512** (sparse decentralized P2P topology).
- **Average Node Degree**: **14.53** (median: 13.0, std: 8.68).
- **Average Clustering Coefficient**: **0.1673** (vs. Erdős–Rényi baseline: 0.0875).
- **Giant Component Average Path Length**: **2.21** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **2.23%**
- **Recall (Sensitivity)**: **84.38%**
- **Accuracy**: **91.41%**
- **F1-Score**: **0.0434**
- **Specificity**: **91.42%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `27` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `1186` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `12643` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `5` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `13861` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.0223** (2.23%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.8438** (84.38%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9141** (91.41%) |
| **Specificity** | `TN / (TN + FP)` | **0.9142** (91.42%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.0434** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0858** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.1562** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `167` | Active surviving peers |
| **Total Edges (|E|)** | `1213` | Undirected P2P connections |
| **Minimum Degree** | `0` | Minimum connections for any single node |
| **Maximum Degree** | `41` | Most connected node in the network |
| **Mean Degree** | `14.53` | Expected degree per node |
| **Median Degree** | `13.0` | Median degree across nodes |
| **Standard Deviation** | `8.68` | Degree dispersion |
| **Graph Density** | `0.087512` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `1` | 0.6% |
| `1-2` | `0` | 0.0% |
| `3-5` | `13` | 7.8% |
| `6-8` | `42` | 25.1% |
| `9-12` | `26` | 15.6% |
| `13-20` | `48` | 28.7% |
| `21-50` | `37` | 22.2% |
| `51-100` | `0` | 0.0% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `103.99.170.201:48333` | `41` |
| 2 | `13.140.162.77:48333` | `41` |
| 3 | `209.146.50.202:48333` | `38` |
| 4 | `209.146.50.204:48333` | `38` |
| 5 | `103.99.170.202:48333` | `36` |
| 6 | `185.232.70.226:48333` | `34` |
| 7 | `103.99.171.201:48333` | `32` |
| 8 | `52.1.114.214:48333` | `32` |
| 9 | `159.195.65.171:48333` | `31` |
| 10 | `193.30.123.70:48333` | `31` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `2` | Number of disconnected sub-graphs |
| **Giant Component Size** | `166` | `99.4%` of total network |
| **Isolated Nodes** | `1` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.1673` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0875` | Random graph reference baseline |
| **Average Shortest Path** | `2.21` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
