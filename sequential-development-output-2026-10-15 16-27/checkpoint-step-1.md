# Checkpoint Step 1: Configuration & Environment Foundations

**Timestamp:** 2026-10-15 16:30:15  
**Module Directory:** `/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/`

---

## 1. Completed Task & Deliverables
- **Package Setup:** Created `snapshot-forked-subgraph/one-forker/` with clean modular architecture.
- **Config & Model Definition (`config.py`):**
  - Configured port conventions for 1,002 nodes:
    - Base P2P port: $10000$ (Ports $10000..11001$)
    - Base RPC port: $20000$ (Ports $20000..21001$)
  - Configured node roles:
    - Probes: Node 0 & Node 1
    - Forker: Node 2
    - Targets: Nodes 3..1001
  - Implemented `load_topology()` loading `/mnt/ssd/hdhphat-mindfullab/regtest-node-data/groundtruth_topology.json`.
  - Implemented `compute_bfs_distances()` to calculate shortest path hop distances from Forker (Node 2) to all 1,000 target nodes.
- **Unit Testing (`test_config.py`):**
  - Verified port formulas, credential generators, and dataclasses.
  - Verified 100% undirected edge reciprocity across all 4,005 edges.
  - Verified full network connectivity and graph diameter from Node 2.

---

## 2. Added Files, Classes, and Functions

### Added Files
- [`snapshot-forked-subgraph/one-forker/__init__.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/__init__.py)
- [`snapshot-forked-subgraph/one-forker/config.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/config.py)
- [`snapshot-forked-subgraph/one-forker/test_config.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/test_config.py)

### Added Classes & Functions
* **`NodeConfig`**: Dataclass with `node_id`, `role`, `p2p_port`, `rpc_port`, `rpc_user`, `rpc_pass`, `datadir`, `rpc_url`.
* **`ExperimentConfig`**: Dataclass encapsulating experiment parameters (`forker_id=2`, `probe_ids=[0, 1]`, `dust_amount_sats=10000`, `fee_sats=1000`, `snapshot_interval_ms=10.0`).
* **`get_ports(node_id)`**: Returns `(10000 + node_id, 20000 + node_id)`.
* **`get_node_config(node_id)`**: Builds `NodeConfig` for any node $0 \le i \le 1001$.
* **`load_all_nodes()`**: Loads config mapping for all 1,002 nodes.
* **`load_topology(path)`**: Parses `groundtruth_topology.json` into undirected adjacency list.
* **`compute_bfs_distances(adj, source)`**: Calculates hop distances from any source.

---

## 3. Test Results & Topological Insights

Executed with `pytest snapshot-forked-subgraph/one-forker/test_config.py -v -s`:
* **All 6 unit tests passed** in $0.06\text{s}$.
* **Hop Distance Distribution from Forker (Node 2):**
  * **Hop 0 (Forker):** 1 node
  * **Hop 1 (Direct peers):** 8 nodes
  * **Hop 2:** 55 nodes
  * **Hop 3:** 306 nodes
  * **Hop 4:** 587 nodes
  * **Hop 5 (Peripheral / furthest boundary):** 43 nodes
  * **Total target nodes reached:** $1,000$ ($100\%$ connectivity)
  * **Network Diameter from Forker:** Exactly 5 hops.

> [!NOTE]
> The 43 nodes at **Hop 5** serve as our deterministic **convergence barrier**: when all 43 Hop-5 nodes accept $B_1$, the entire network is guaranteed to have fully absorbed $B_1$ before $B_2 + B_3$ are published.

---

## 4. Next Step to Implement
* **Step 2:** **Funding Engine & UTXO Setup (`funding.py`)**
  - Query Node 2 wallet for spendable UTXOs.
  - If insufficient, automatically route mature coinbase funds from Node 0 (`mywallet`) to Node 2 via a funded transfer and confirm with a block.
  - Return spendable parent UTXO `tx0 = (txid, vout, amount)` ready for double-spending.
