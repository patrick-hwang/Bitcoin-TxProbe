# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-09T03:47:36.751307+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **235** surviving nodes and **1839** active undirected edges.
- **Network Density**: **0.066885** (sparse decentralized P2P topology).
- **Average Node Degree**: **15.65** (median: 12.0, std: 10.69).
- **Average Clustering Coefficient**: **0.1541** (vs. Erdős–Rényi baseline: 0.0669).
- **Giant Component Average Path Length**: **2.31** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **86.29%**
- **Recall (Sensitivity)**: **84.83%**
- **Accuracy**: **99.20%**
- **F1-Score**: **0.8555**
- **Specificity**: **99.61%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `151` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `24` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `6178` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `27` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `6380` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.8629** (86.29%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **0.8483** (84.83%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9920** (99.20%) |
| **Specificity** | `TN / (TN + FP)` | **0.9961** (99.61%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.8555** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0039** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.1517** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `235` | Active surviving peers |
| **Total Edges (|E|)** | `1839` | Undirected P2P connections |
| **Minimum Degree** | `0` | Minimum connections for any single node |
| **Maximum Degree** | `54` | Most connected node in the network |
| **Mean Degree** | `15.65` | Expected degree per node |
| **Median Degree** | `12.0` | Median degree across nodes |
| **Standard Deviation** | `10.69` | Degree dispersion |
| **Graph Density** | `0.066885` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `1` | 0.4% |
| `1-2` | `3` | 1.3% |
| `3-5` | `15` | 6.4% |
| `6-8` | `70` | 29.8% |
| `9-12` | `29` | 12.3% |
| `13-20` | `50` | 21.3% |
| `21-50` | `66` | 28.1% |
| `51-100` | `1` | 0.4% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `jspxdo33gyrh3tewi55mn2fo5spczzgipq6ao7fa5qu6fj2ezr7bizid.onion:48333` | `54` |
| 2 | `159.195.65.171:48333` | `50` |
| 3 | `193.30.123.70:48333` | `49` |
| 4 | `zjttaesjhj7ail437ag4emdufr775h5rtgoohlbca5rwc4re6dr5k7ad.onion:48333` | `46` |
| 5 | `zdh7vrzykdv7474yioe5jiv3kgajky727t5phxsbt47lefjseo3ypaqd.onion:48333` | `45` |
| 6 | `116.203.184.251:48333` | `43` |
| 7 | `89.58.9.219:48333` | `43` |
| 8 | `yiolb6ahgjry66g3vt4dtlnybhdgy4udakakbjxuekj33ligd57mdlqd.onion:48333` | `43` |
| 9 | `hb44egze5hjbi3n2rc6w4pwahr6zltc4ilfzin3kkdi2rmozvxlo65qd.onion:48333` | `42` |
| 10 | `vizb74h32bx3u6zksgsi6seq6hcqdhok5pd4z2x5yj3ll72tu7pcu7id.onion:48333` | `41` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `2` | Number of disconnected sub-graphs |
| **Giant Component Size** | `234` | `99.6%` of total network |
| **Isolated Nodes** | `1` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.1541` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0669` | Random graph reference baseline |
| **Average Shortest Path** | `2.31` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
