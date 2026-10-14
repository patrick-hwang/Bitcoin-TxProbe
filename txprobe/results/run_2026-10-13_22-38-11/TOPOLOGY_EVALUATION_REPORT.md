# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-13T16:19:56.435535+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **197** surviving nodes and **2084** active undirected edges.
- **Network Density**: **0.107946** (sparse decentralized P2P topology).
- **Average Node Degree**: **21.16** (median: 17.0, std: 15.25).
- **Average Clustering Coefficient**: **0.2341** (vs. Erdős–Rényi baseline: 0.1079).
- **Giant Component Average Path Length**: **2.12** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **98.21%**
- **Recall (Sensitivity)**: **100.00%**
- **Accuracy**: **99.76%**
- **F1-Score**: **0.9910**
- **Specificity**: **99.73%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `55` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `1` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `367` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `0` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `423` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.9821** (98.21%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **1.0000** (100.00%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9976** (99.76%) |
| **Specificity** | `TN / (TN + FP)` | **0.9973** (99.73%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.9910** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0027** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0000** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `197` | Active surviving peers |
| **Total Edges (|E|)** | `2084` | Undirected P2P connections |
| **Minimum Degree** | `3` | Minimum connections for any single node |
| **Maximum Degree** | `70` | Most connected node in the network |
| **Mean Degree** | `21.16` | Expected degree per node |
| **Median Degree** | `17.0` | Median degree across nodes |
| **Standard Deviation** | `15.25` | Degree dispersion |
| **Graph Density** | `0.107946` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `0` | 0.0% |
| `3-5` | `4` | 2.0% |
| `6-8` | `38` | 19.3% |
| `9-12` | `31` | 15.7% |
| `13-20` | `51` | 25.9% |
| `21-50` | `59` | 29.9% |
| `51-100` | `14` | 7.1% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `5rh3ln6ypycmn57qlmke3dliffg2id3ziz4dhsujng4tk34oklnbqtyd.onion:48333` | `70` |
| 2 | `zdh7vrzykdv7474yioe5jiv3kgajky727t5phxsbt47lefjseo3ypaqd.onion:48333` | `63` |
| 3 | `103.99.171.202:48333` | `61` |
| 4 | `jspxdo33gyrh3tewi55mn2fo5spczzgipq6ao7fa5qu6fj2ezr7bizid.onion:48333` | `60` |
| 5 | `3.235.188.91:48333` | `59` |
| 6 | `yiolb6ahgjry66g3vt4dtlnybhdgy4udakakbjxuekj33ligd57mdlqd.onion:48333` | `57` |
| 7 | `193.30.123.70:48333` | `56` |
| 8 | `zjttaesjhj7ail437ag4emdufr775h5rtgoohlbca5rwc4re6dr5k7ad.onion:48333` | `54` |
| 9 | `159.195.65.171:48333` | `53` |
| 10 | `3.212.232.10:18333` | `52` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `197` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.2341` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.1079` | Random graph reference baseline |
| **Average Shortest Path** | `2.12` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
