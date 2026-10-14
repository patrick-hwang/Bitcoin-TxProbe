# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-14T06:21:26.963305+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **206** surviving nodes and **1686** active undirected edges.
- **Network Density**: **0.079848** (sparse decentralized P2P topology).
- **Average Node Degree**: **16.37** (median: 14.0, std: 9.84).
- **Average Clustering Coefficient**: **0.1577** (vs. Erdős–Rényi baseline: 0.0798).
- **Giant Component Average Path Length**: **2.24** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **94.79%**
- **Recall (Sensitivity)**: **98.91%**
- **Accuracy**: **99.45%**
- **F1-Score**: **0.9681**
- **Specificity**: **99.50%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `91` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `5` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `998` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `1` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `1095` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.9479** (94.79%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.9891** (98.91%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9945** (99.45%) |
| **Specificity** | `TN / (TN + FP)` | **0.9950** (99.50%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.9681** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0050** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0109** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `206` | Active surviving peers |
| **Total Edges (|E|)** | `1686` | Undirected P2P connections |
| **Minimum Degree** | `1` | Minimum connections for any single node |
| **Maximum Degree** | `53` | Most connected node in the network |
| **Mean Degree** | `16.37` | Expected degree per node |
| **Median Degree** | `14.0` | Median degree across nodes |
| **Standard Deviation** | `9.84` | Degree dispersion |
| **Graph Density** | `0.079848` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `1` | 0.5% |
| `3-5` | `4` | 1.9% |
| `6-8` | `53` | 25.7% |
| `9-12` | `36` | 17.5% |
| `13-20` | `48` | 23.3% |
| `21-50` | `63` | 30.6% |
| `51-100` | `1` | 0.5% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `[2001:df6:7280::92:204]:48333` | `53` |
| 2 | `193.30.123.70:48333` | `50` |
| 3 | `32.196.76.227:48333` | `44` |
| 4 | `[2001:df6:7280::92:206]:48333` | `43` |
| 5 | `zjttaesjhj7ail437ag4emdufr775h5rtgoohlbca5rwc4re6dr5k7ad.onion:48333` | `43` |
| 6 | `5rh3ln6ypycmn57qlmke3dliffg2id3ziz4dhsujng4tk34oklnbqtyd.onion:48333` | `42` |
| 7 | `116.203.184.251:48333` | `40` |
| 8 | `65.108.141.219:48333` | `39` |
| 9 | `vizb74h32bx3u6zksgsi6seq6hcqdhok5pd4z2x5yj3ll72tu7pcu7id.onion:48333` | `39` |
| 10 | `3.235.188.91:48333` | `38` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `206` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.1577` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0798` | Random graph reference baseline |
| **Average Shortest Path** | `2.24` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
