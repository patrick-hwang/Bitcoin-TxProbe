# TxProbe Network Topology Evaluation Report

**Generated**: 2026-10-09T12:51:27.604127+00:00  
**Target Network**: Bitcoin Testnet4  

---

## 1. Executive Summary

- **Inferred Network Scale**: **216** surviving nodes and **1717** active undirected edges.
- **Network Density**: **0.073945** (sparse decentralized P2P topology).
- **Average Node Degree**: **15.90** (median: 14.5, std: 9.46).
- **Average Clustering Coefficient**: **0.1416** (vs. Erdős–Rényi baseline: 0.0739).
- **Giant Component Average Path Length**: **2.26** hops (Diameter: 4, Radius: 3).

### Groundtruth Validation Summary

- **Precision**: **0.00%**
- **Recall (Sensitivity)**: **100.00%**
- **Accuracy**: **92.61%**
- **F1-Score**: **0.0000**
- **Specificity**: **92.61%**

---

## 2. Groundtruth Validation Metrics

### 2.1 Confusion Matrix

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | `0` | Genuine edges correctly inferred by TxProbe |
| **False Positives (FP)** | `1717` | Non-existent connections falsely inferred |
| **True Negatives (TN)** | `21503` | Non-connected pairs correctly discarded |
| **False Negatives (FN)** | `0` | Real groundtruth edges erroneously missed |
| **Total Candidate Pairs** | `23220` | All possible undirected pairs in groundtruth slice |

### 2.2 Classification Scores

| Metric | Formula | Value |
|---|---|---|
| **Precision** | `TP / (TP + FP)` | **0.0000** (0.00%) |
| **Recall (Sensitivity)** | `TP / (TP + FN)` | **1.0000** (100.00%) |
| **Accuracy** | `(TP + TN) / Total` | **0.9261** (92.61%) |
| **Specificity** | `TN / (TN + FP)` | **0.9261** (92.61%) |
| **F1-Score** | `2 * (P * R) / (P + R)` | **0.0000** |
| **False Positive Rate (FPR)** | `FP / (FP + TN)` | **0.0739** |
| **False Negative Rate (FNR)** | `FN / (TP + FN)` | **0.0000** |

---

## 3. Global Network Topology Characterization

### 3.1 Graph Scale & Degree Distribution

| Property | Value | Notes |
|---|---|---|
| **Total Nodes (|V|)** | `216` | Active surviving peers |
| **Total Edges (|E|)** | `1717` | Undirected P2P connections |
| **Minimum Degree** | `1` | Minimum connections for any single node |
| **Maximum Degree** | `56` | Most connected node in the network |
| **Mean Degree** | `15.90` | Expected degree per node |
| **Median Degree** | `14.5` | Median degree across nodes |
| **Standard Deviation** | `9.46` | Degree dispersion |
| **Graph Density** | `0.073945` | 2|E| / (|V|(|V|-1)) |

### 3.2 Degree Distribution Histogram

| Degree Bucket | Node Count | Percentage |
|---|---|---|
| `0` | `0` | 0.0% |
| `1-2` | `1` | 0.5% |
| `3-5` | `7` | 3.2% |
| `6-8` | `57` | 26.4% |
| `9-12` | `31` | 14.4% |
| `13-20` | `57` | 26.4% |
| `21-50` | `61` | 28.2% |
| `51-100` | `2` | 0.9% |
| `101+` | `0` | 0.0% |

### 3.3 Top Network Hubs (Supernodes)

| Rank | Node Address | Degree |
|---|---|---|
| 1 | `azccjliswzu5aycse7g7zu2bw3mqicd2mhszczitp332scjgltehrjqd.onion:48333` | `56` |
| 2 | `103.99.171.201:48333` | `53` |
| 3 | `zdh7vrzykdv7474yioe5jiv3kgajky727t5phxsbt47lefjseo3ypaqd.onion:48333` | `46` |
| 4 | `103.99.171.202:48333` | `45` |
| 5 | `jspxdo33gyrh3tewi55mn2fo5spczzgipq6ao7fa5qu6fj2ezr7bizid.onion:48333` | `45` |
| 6 | `yiolb6ahgjry66g3vt4dtlnybhdgy4udakakbjxuekj33ligd57mdlqd.onion:48333` | `41` |
| 7 | `zjttaesjhj7ail437ag4emdufr775h5rtgoohlbca5rwc4re6dr5k7ad.onion:48333` | `40` |
| 8 | `103.99.170.201:48333` | `35` |
| 9 | `144.76.2.169:48333` | `35` |
| 10 | `85.203.53.149:18333` | `34` |

### 3.4 Connectivity, Small-World & Clustering Properties

| Metric | Empirical Value | Theoretical Context |
|---|---|---|
| **Number of Components** | `1` | Number of disconnected sub-graphs |
| **Giant Component Size** | `216` | `100.0%` of total network |
| **Isolated Nodes** | `0` | Nodes with degree 0 |
| **Average Clustering (C_avg)** | `0.1416` | Local triadic closure |
| **Erdős–Rényi Clustering (C_ER)** | `0.0739` | Random graph reference baseline |
| **Average Shortest Path** | `2.26` hops | Characteristic path length |
| **Network Diameter** | `4` hops | Maximum shortest path |
| **Network Radius** | `3` hops | Minimum node eccentricity |

---

## 4. Architectural Analysis & Bitcoin P2P Dynamics

- **Degree Skewness & Supernodes**: Bitcoin Core nodes typically maintain 8 default outbound peers and up to 125 inbound connections. The presence of supernodes reflects public seeders, explorers, or high-capacity mining infrastructure.
- **Low Clustering**: The empirical clustering coefficient aligns with Bitcoin P2P's randomized peer selection protocol designed to prevent eclipse attacks and avoid dense triadic clusters.
- **Small-World Propagation**: Low average path length confirms high network navigability, ensuring unconfirmed transactions reach the vast majority of hashpower within seconds.
