# TxProbe on Bitcoin Testnet4 — Overview Architecture & Roadmap

## 1. Goal & Environment
- **Goal**: Capture and infer the network topology of ~1000 nodes in Bitcoin Testnet4 using the TxProbe technique, with 2 probe nodes (**Probe 0** and **Probe 1**) and groundtruth validation (**Nodes 2–6**).
- **Environment**: Linux server, nodes and Tor daemon launched via [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh) with `-rpcthreads=64 -rpcworkqueue=256 -txprobelogfile="txprobe_${i}.log"`:
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
    - Prioritized address collection: Groundtruth self `.onion` identities [2..6] $\to$ Groundtruth peers [2..6] $\to$ Probe peers [0,1] $\to$ DNS seeds $\to$ Address manager [0..6].
    - Active reachability test (TCP connect + P2P version handshake; Tor SOCKS5 support).
    - `src/net.h` connection limits raised (`MAX_ADDNODE_CONNECTIONS = 1100`, `DEFAULT_MAX_PEER_CONNECTIONS = 1200`).
  - **Phase 2: Batch Connection & Probe Selection** *(Completed)*
    - Dual independent worker pools per probe node (`clearnet_onetry_concurrency = 32`, `tor_onetry_concurrency = 8`) starting simultaneously at $t=0$ so Tor circuit setup never blocks Clearnet connections.
    - Polling loop (`poll_interval_sec = 5s`, `crawling_time_sec = 180s`) with early exit when $\ge 1000$ mutually connected full-relay peers are found.
    - Intersect peers connected to both Probe 0 and Probe 1, select up to 1000 nodes preserving `CandidatePriority` order, and disconnect excess peers via `disconnectnode`.
- **Step 1: Groundtruth Capture** *(Completed)*
  - Pure, fast snapshot querying `getnetworkinfo` + `getpeerinfo` on Groundtruth nodes [2..6] and `getpeerinfo` on Probe nodes [0, 1].
  - Prunes any target node that dropped since Step 0, builds symmetric undirected `adj_list` of valid full-relay edges, and saves `initial_groundtruth.json`.
- **Step 2: INVBLOCK Pre-filtering (Dual-Condition Filter)** *(Completed)*
  - Dual-condition filter:
    - **Filter 1 (Relay Responsiveness)**: Eliminates nodes that fail to send `GETDATA` to Probe 0 for an unbroadcast test transaction (filters out IBD, blocksonly mode, crawler spiders, and high-latency timeouts).
    - **Filter 2 (INVBLOCK Compliance)**: Eliminates nodes that send duplicate `GETDATA` to Probe 1 for a transaction already blocked/in-flight from Probe 0.
  - Disconnects all eliminated nodes from both probes in parallel, prunes `GraphSnapshot`, clears probe transaction memory via `clearinv_probe`, and outputs `filtered_groundtruth.json`.
- **Step 3: Raw Transaction Crafting** *(Next)*
  - Automated construction, signing, and UTXO management for $n+1$ parent/flood txs and $n$ markers with conflict-chaining.
- **Step 4: TxProbe Execution Loop**
  - Matrix rounds execution, INVBLOCK, sending order, GETDATA tracking.
- **Step 5: Malfunction Filtering**
  - Filter misbehaving / disconnected nodes during probing.
- **Step 6: Metric Calculation & Topology Evaluation**
  - Precision, Recall, F1 against groundtruth, graph density, degree distribution.
