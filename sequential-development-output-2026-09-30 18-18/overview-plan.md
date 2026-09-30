# TxProbe on Bitcoin Testnet4 — Overview Architecture & Roadmap

## 1. Goal & Environment
- **Goal**: Capture and infer the network topology of ~1000 nodes in Bitcoin Testnet4 using the TxProbe technique, with 2 probe nodes (**Probe 0** and **Probe 1**) and groundtruth validation (**Nodes 2–6**).
- **Environment**: Linux server, nodes and Tor daemon launched via [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh) with `-rpcthreads=64 -rpcworkqueue=256 -txprobelogfile="txprobe_${i}.log"`:
  - **Node 0 & Node 1**: Custom `bitcoind` (`[TxProbe]`) with `sendinv_orphan`, `sendrawtransaction_orphan`, `clearinv_probe`, and raised connection limits (`MAX_ADDNODE_CONNECTIONS = 1100`, `DEFAULT_MAX_PEER_CONNECTIONS = 1200`).
  - **Nodes 2, 3, 4, 5, 6**: Official Bitcoin Core 31.1 (`[Official 31.1]`) acting as groundtruth nodes.

---

## 2. TxProbe Core Protocol
For each round with reachable nodes partitioned into source set ($S$) and sink set ($K$):
1. **Conflicting Txs**: Create $n+1$ conflicting transactions using the same single UTXO output as input ($n$ parent transactions $ptx_1 \dots ptx_n$ and 1 flooding transaction $ftx$).
2. **Marker Txs**: Create $n$ marker transactions $mtx_1 \dots mtx_n$, each spending the output of parent transaction $ptx_i$.
3. **INVBLOCK**: Send INV messages of $[ptx_1 \dots ptx_n, ftx]$ to all reachable nodes using custom RPC `sendinv_orphan`. Wait 5 seconds.
4. **Distribute FTX & PTX**:
   - Send $ftx$ to all sink nodes via `sendrawtransaction_orphan` (wait 1s).
   - Send $ptx_i$ to source node $i$ via `sendrawtransaction_orphan` (wait 5s).
   - Clear probe INVBLOCK tracking (`clearinv_probe`), truncate `txprobe_0.log` (Clear Log #1), and send marker $mtx_i$ to source node $i$ via `sendrawtransaction_orphan`.
5. **Propagation Wait & Log-Based Malfunction Detection**:
   - Wait 10 seconds for marker transactions to propagate across the network.
   - Parse `txprobe_0.log` for any source node $s_i$ that requested `GETDATA` for its own $ptx_i$ (indicating $s_i$ rejected $ptx_i$ and placed $mtx_i$ into `txorphanage`).
6. **Query Peers (Clear Log #2)**:
   - Truncate `txprobe_0.log` a second time and send all marker transaction inventories to all active peers ($S \cup K$) via `sendinv_orphan` (registering `probe_0` as an announcer in `txorphanage` via `AddAnnouncer`).
7. **Inference (Method 2: Complete Graph $\to$ Discard on `GETDATA`)**:
   - Start with Complete Graph $K_V$ over all qualified nodes.
   - In round $r$, if a `GETDATA` request for marker $mtx_i$ is received from sink node $k_j \implies$ **discard edge** $\{s_i, k_j\}$ permanently.
   - After all $R$ rounds, retain only pairs tested in $\ge 1$ round and never discarded.
8. **Post-Round Orphanage Cleanup**:
   - Call `clearinv_probe()` and send the remaining parent transactions ($ptx_1 \dots ptx_n$ and $ftx$) to all active peers that did not receive them earlier so every node triggers 1P1C package evaluation / conflict rejection and erases $mtx_i$ from `txorphanage` before round $r+1$.

---

## 3. Matrix Splitting Strategy
For $rn$ reachable nodes:
- Let $w = \min(75, \lceil\sqrt{rn}\rceil)$, $h = \lceil rn / w \rceil = (rn + w - 1) // w$.
- Arrange $rn$ nodes into a matrix $\text{grid}[h][w]$.
- **If $w \ge h$** (holds for all $rn \le 75^2 = 5625$):
  - For column $c \in [0, w-2]$: source = col $c$, sink = remaining nodes.
  - For row $r \in [0, h-2]$: source = row $r$, sink = remaining nodes.
  - Total rounds: $h + w - 2$.
- **Else ($w < h$)**:
  - For row $r \in [0, h-2]$: source = row $r$, sink = remaining nodes.
  - For col $c \in [0, w-2]$: block partitions along columns of size $\le \text{max\_source\_size}$.

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
- **Step 3: Raw Transaction Crafting (Matrix Partitioning, UTXO Splitting & Pre-Crafting)** *(Completed)*
  - Generates all $(S_r, K_r)$ matrix rounds upfront ($w = \min(75, \lceil\sqrt{rn}\rceil)$, $h = \lceil rn / w \rceil$).
  - Checks Probe 0's wallet for confirmed UTXOs ($\ge 2000\text{ sats}$):
    - Automatically splits any large UTXO (`len(vin) == 1` $\to$ up to 500 outputs of $2000\text{ sats}$ + remainder) when total projected UTXOs $< R$.
    - Distinguishes between `0-conf` mempool UTXOs and actual funding deficits; prompts user with Probe 0 deposit address if needed and waits for 1 block confirmation + propagation.
  - Pre-crafts and signs all $R$ rounds (`parent_txs`, `flood_tx`, `marker_txs`) via batched JSON-RPC and saves `crafted_rounds.json`.
- **Step 4: TxProbe Execution Loop & Multi-Round Topology Inference** *(Completed)*
  - Executes all pre-crafted matrix rounds sequentially without waiting for blocks:
    - Method 2 topology inference (Complete Graph $K_V \to$ Discard on `GETDATA`).
    - Double log clearing in Step 2.5 and Step 2.6 so stale `INVBLOCK` requests never contaminate marker or parent `GETDATA` parsing.
    - Unified log-based malfunctioning source detection (via Bitcoin Core orphan resolution `GETDATA(parent_txs[i])` in Step 2.5 and `GETDATA(marker_txs[i])` in Step 2.6) across all ~1000 public and groundtruth nodes without needing `getrawmempool`.
    - Post-round `txorphanage` cleanup in Step 2.8 via batched parent & flood broadcasts so every peer evicts `marker_txs` via 1P1C package evaluation before round $r+1$.
    - Outputs `txprobe_execution.json` (and live per-round `txprobe_execution_checkpoint.json`).
- **Step 5: Malfunction Filtering & Post-Probing Groundtruth Reconciliation** *(Next)*
  - Capture final groundtruth snapshot after probing, reconcile transitory/churned edges and malfunctioning/dropped nodes across Step 1, Step 2, and Step 4 snapshots.
- **Step 6: Metric Calculation & Topology Evaluation**
  - Precision, Recall, F1 against groundtruth, graph density, degree distribution.
