# TxProbe on Bitcoin Testnet4 — Overview Architecture & Roadmap

## 1. Goal
Capture and infer the network topology of ~1000 nodes in Bitcoin Testnet4 using the TxProbe technique, with 2 probe nodes (probe 0 and probe 6) and groundtruth validation.

---

## 2. TxProbe Core Protocol
For each round with reachable nodes partitioned into source set ($S$) and sink set ($K$):
1. **Conflicting Txs**: Create $n+1$ conflicting transactions using the same single UTXO output as input ($n$ parent transactions $ptx_1 \dots ptx_n$ and 1 flooding transaction $ftx$).
2. **Marker Txs**: Create $n$ marker transactions $mtx_1 \dots mtx_n$, each spending the output of parent transaction $ptx_i$.
3. **INVBLOCK**: Send INV messages of $[ptx_1 \dots ptx_n, ftx]$ to all reachable nodes using custom RPC `sendinv_orphan`. Wait 2 seconds.
4. **Distribute FTX & PTX**:
   - Send $ftx$ to all sink nodes via `sendinv_orphan` (wait 1–2s).
   - Send $ptx_i$ to source node $i$ via `sendinv_orphan` (wait 3–4s).
   - Send marker $mtx_i$ to source node $i$ via `sendinv_orphan`.
5. **Propagation Wait**: Wait 10 seconds for transactions to propagate across the network.
6. **Query Sinks**: Send all marker transaction inventories to sink nodes via `sendinv_orphan`.
7. **Inference**:
   - If a GETDATA request for marker $mtx_i$ is received from sink node $j \implies$ **NO edge** exists between source $i$ and sink $j$ (the sink had already received $ftx$, conflicting with $ptx_i$).
   - Otherwise $\implies$ an **edge exists** between source $i$ and sink $j$.

---

## 3. Matrix Splitting Strategy
For $rn$ reachable nodes:
- Let $w = \min(75, \lfloor\sqrt{rn}\rfloor)$, $h = \lceil rn / w \rceil = (rn + w - 1) // w$.
- Arrange $rn$ nodes into a matrix $\text{nodes}[w][h]$ (or $h \times w$).
- **If $w \ge h$**:
  - For column $i \in [0, w-2]$: source = col $i$, sink = remaining nodes.
  - For row $i \in [0, h-2]$: source = row $i$, sink = remaining nodes.
  - Total rounds: $h + w - 2$.
- **Else ($w < h$)**:
  - For row $i \in [0, h-2]$: source = row $i$, sink = remaining nodes.
  - For col $i \in [0, w-2]$: block partitions along columns.
  - Total rounds: $\approx 2h$.

---

## 4. Pipeline Roadmap

- **Step 0: Node Discovery & Setup**
  - **Phase 1: Initial Address Harvest** *(Completed)*
    - Direct JSON-RPC via `aiohttp` (no `bitcoin-cli` subprocesses).
    - Prioritized address collection (Groundtruth peers $\to$ Probe peers $\to$ DNS seeds $\to$ Address manager).
    - Active reachability test (TCP connect + P2P version handshake; Tor SOCKS5 support).
    - `src/net.h` connection limits raised (`MAX_ADDNODE_CONNECTIONS = 1100`, `DEFAULT_MAX_PEER_CONNECTIONS = 1200`).
  - **Phase 2: Batch Connection & Probe Selection** *(Next)*
    - Batch `addnode` connection attempts from Probe 0 and Probe 6.
    - CRAWLING_TIME threshold with early exit when $\ge 1000$ reachable nodes are connected.
    - Intersect peers connected to both probes, select 1000 nodes, persist with `addnode "add"`.
- **Step 1: Groundtruth Capture**
  - Record groundtruth peer adjacencies among test nodes.
- **Step 2: INVBLOCK Pre-filtering**
  - Filter out nodes that fail to process `sendinv_orphan`.
- **Step 3: Raw Transaction Crafting**
  - Automated construction, signing, and UTXO management for $n+1$ parent/flood txs and $n$ markers.
- **Step 4: TxProbe Execution Loop**
  - Matrix rounds execution, INVBLOCK, sending order, GETDATA tracking.
- **Step 5: Malfunction Filtering**
  - Filter misbehaving / disconnected nodes during probing.
- **Step 6: Metric Calculation & Topology Evaluation**
  - Precision, Recall, F1 against groundtruth, graph density, degree distribution.
