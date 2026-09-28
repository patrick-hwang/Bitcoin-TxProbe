# TxProbe on Bitcoin Testnet4 — Overview Architecture & Roadmap

## 1. Goal & Environment
- **Goal**: Capture and infer the network topology of ~1000 nodes in Bitcoin Testnet4 using the TxProbe technique, with 2 probe nodes (**Probe 0** and **Probe 1**) and groundtruth validation (**Nodes 2–6**).
- **Environment**: Linux server, nodes and Tor daemon launched via [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh):
  - **Node 0 & Node 1**: Custom `bitcoind` (`[TxProbe]`) with `sendinv_orphan` and raised connection limits (`MAX_ADDNODE_CONNECTIONS = 1100`, `DEFAULT_MAX_PEER_CONNECTIONS = 1200`).
  - **Nodes 2, 3, 4, 5, 6**: Official Bitcoin Core 31.1 (`[Official 31.1]`) acting as groundtruth nodes.

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
    - Prioritized address collection (Groundtruth peers [2..6] $\to$ Probe peers [0,1] $\to$ DNS seeds $\to$ Address manager [0..6]).
    - Active reachability test (TCP connect + P2P version handshake; Tor SOCKS5 support).
    - `src/net.h` connection limits raised (`MAX_ADDNODE_CONNECTIONS = 1100`, `DEFAULT_MAX_PEER_CONNECTIONS = 1200`).
  - **Phase 2: Batch Connection & Probe Selection** *(Completed)*
    - Concurrent `addnode("addr", "onetry")` connection workers (`onetry_concurrency = 12`) from Probe 0 and Probe 1, prioritizing clearnet before onion within each priority tier.
    - Polling loop with `crawling_time_sec = 600s` threshold and early exit when $\ge 1000$ mutually connected full-relay peers are found.
    - Intersect peers connected to both Probe 0 and Probe 1, select up to 1000 nodes preserving `CandidatePriority` order, and disconnect excess peers via `disconnectnode` (no `addnode "add"` needed since `"onetry"` creates persistent `ConnectionType::MANUAL` connections).
- **Step 1: Groundtruth Capture** *(Next)*
  - Record groundtruth peer adjacencies among test nodes (Nodes 2–6 and the selected target peers).
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
