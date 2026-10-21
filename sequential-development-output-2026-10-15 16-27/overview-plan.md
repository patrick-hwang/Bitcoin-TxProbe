# Overview Plan: Fork Injection and High-Frequency Subgraph Snapshotting

## 1. Project Goal
Develop an automated, high-precision framework to simulate, monitor, and record the propagation dynamics of an intentional blockchain fork and chain reorganization across a 1,000-node Bitcoin RegTest network.

- **Network Environment:** RegTest network with 1,000 target nodes (Nodes 2..1001) and 2 Probe nodes (Nodes 0 and 1) provisioned in `/mnt/ssd/hdhphat-mindfullab/regtest-node-data/`.
- **Target Location:** `/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/`
- **Role 1 (The Forker - Node 2):**
  - Spends a mature parent UTXO ($tx_0$) into two conflicting double-spending transactions ($tx_1$ to random node, $tx_2$ back to Node 2).
  - Crafts Block $B_1$ (containing $tx_1$) off current tip $H_{\text{parent}}$.
  - Crafts competing Block $B_2$ (containing $tx_2$) off the same parent $H_{\text{parent}}$.
  - Crafts extension Block $B_3$ off $B_2$.
  - Publishes $B_1$, waits for full network convergence (calculated wait / dynamic barrier), then publishes $B_2 + B_3$ to trigger network-wide reorganization.
- **Role 2 (The Prober - Nodes 0 and 1):**
  - Fully peered with all 1,000 nodes.
  - Intercepts block announcements (`inv`, `headers`, `cmpctblock`) across all 1,000 nodes with microsecond timestamps.
  - Records continuous arrival timestamps for each block on every node $v \in \{2..1001\}$.
  - Provides dynamic continuous snapshot querying ($t \in \mathbb{R}$) and discrete 10ms slicing.
  - Exports comprehensive results for the fork event at height $H$ to `fork_subgraph_height_<H>.json`.

---

## 2. Sequential Development Steps

| Step | Title | Description | Deliverables |
| :--- | :--- | :--- | :--- |
| **Step 1** | **Configuration & Environment Foundations** | Setup module folder, `config.py`, topology graph parsing, BFS distance calculator, and unit tests. | `config.py`, `test_config.py`, Checkpoint 1 |
| **Step 2** | **Funding Engine & UTXO Management** | Wallet and UTXO setup on Node 2 (Forker) ensuring spendable $tx_0$ via Probe 0 coinbase transfer or mining. | `funding.py`, `test_funding.py`, Checkpoint 2 |
| **Step 3** | **Offline Double-Spend & Block Crafter** | Construct $tx_1, tx_2, B_1, B_2, B_3$ using Bitcoin Core serialization and low-level PoW mining without premature broadcasting. | `block_builder.py`, `test_block_builder.py`, Checkpoint 3 |
| **Step 4** | **P2P Ingress Event Monitor & Snapshotter** | Asynchronous block announcement listener from Probes 0 & 1, timestamp matrix recorder, dynamic $t$-snapshot utility. | `prober.py`, `test_prober.py`, Checkpoint 4 |
| **Step 5** | **Forker Actuator & Master Orchestrator** | Implementation of `forker.py` and `run_experiment.py`, executing the complete $B_1 \to \text{wait} \to B_2+B_3$ reorg workflow. | `forker.py`, `run_experiment.py`, End-to-end Verification |
