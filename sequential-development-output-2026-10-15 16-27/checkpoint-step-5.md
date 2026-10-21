# Checkpoint Step 5: Forker Actuator & Master Orchestrator

**Timestamp:** 2026-10-15 16:51:15  
**Module Directory:** `/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/`

---

## 1. Completed Task & Deliverables
- **Forker Actuator (`forker.py`):**
  - **Phase 1 ($B_1$ Release):** Publishes Block $B_1$ to Node 2 via `submitblock`.
  - **Phase 2 (Convergence Barrier):** Dynamically monitors the 43 peripheral nodes at Hop 5 (maximum distance $d=5$) using async RPC `getbestblockhash` until $100\%$ of peripheral nodes adopt $B_1$.
  - **Phase 3 ($B_2 + B_3$ Release):** Submits Block $B_2$ (accepted as competing side branch), then immediately submits Block $B_3$ (heavier work triggering `ActivateBestChain()` and network-wide reorganization).
  - **Phase 4 (Reorganization Convergence):** Monitors peripheral nodes until $100\%$ converge on $B_3$.
  - Records detailed timings in `ForkerExecutionTimings` (`b1_published_at`, `b1_converged_at`, `b1_propagation_duration_ms`, `b2_published_at`, `b3_published_at`, `reorg_converged_at`, `reorg_propagation_duration_ms`).
- **Master Orchestrator CLI (`run_experiment.py`):**
  - Full CLI interface supporting `--live`, `--dry-run`, `--step-ms` (default: 10.0ms), `--funding-sats` (default: 100,000), `--timeout`, and `--out`.
  - Implements both `run_live_experiment` (targeting live 1,000-node network) and `run_simulated_experiment` (validating end-to-end pipeline without live nodes).
  - Automatically exports full dataset to `results/fork_subgraph_height_<H>.json`.
- **Unit Testing (`test_forker.py`):**
  - Verified `ForkerExecutionTimings` serialization.
  - Verified asynchronous batch polling of `check_nodes_best_block`.
  - Verified convergence barrier loop termination on $100\%$ node adoption.
  - Verified `execute_forker_sequence` submission order and tracker event recording.

---

## 2. Added Files, Classes, and Functions

### Added Files
- [`snapshot-forked-subgraph/one-forker/forker.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/forker.py)
- [`snapshot-forked-subgraph/one-forker/run_experiment.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/run_experiment.py)
- [`snapshot-forked-subgraph/one-forker/test_forker.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/test_forker.py)

### Added Classes & Functions
* **`ForkerExecutionTimings`**: Dataclass holding precise publish and convergence timestamps.
* **`submit_block_to_node(node_id, block_hex)`**: RPC wrapper submitting block via `submitblock`.
* **`check_nodes_best_block(node_ids, target_hash)`**: Async parallel batch query checking best block hash on nodes.
* **`wait_for_convergence_barrier(target_block_hash, peripheral_node_ids, ...)`**: Dynamic barrier monitoring propagation to furthest boundary.
* **`execute_forker_sequence(...)`**: Main actuator executing $B_1 \to \text{wait} \to B_2+B_3 \to \text{reorg}$.
* **`run_simulated_experiment(config, step_ms, out_path)`**: Dry-run simulation generator.
* **`run_live_experiment(config, step_ms, out_path)`**: Live network runner.

---

## 3. Test & Simulation Results

1. **Unit Test Suite:**
   Executed with `pytest snapshot-forked-subgraph/one-forker/ -v`:
   * **All 26 unit tests passed** in $0.31\text{s}$.
     * `test_config.py`: 6 passed
     * `test_funding.py`: 7 passed
     * `test_block_builder.py`: 3 passed
     * `test_prober.py`: 6 passed
     * `test_forker.py`: 4 passed

2. **Dry-Run Pipeline Simulation:**
   Executed with `python snapshot-forked-subgraph/one-forker/run_experiment.py --dry-run --step-ms 10.0`:
   * Sliced 26 snapshots spanning $250\text{ms}$ at exact $10.0\text{ms}$ increments.
   * Saved output to [`results/fork_subgraph_height_102.json`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/results/fork_subgraph_height_102.json).
   * Verified progression:
     * Snapshot 0: Parent: 999 nodes, $B_1$: 1 node (Forker).
     * Snapshot 10: Parent: 0 nodes, $B_1$: 1000 nodes ($100\%$ network convergence).
     * Snapshot 11: Reorg initiated by Forker ($B_2 + B_3$).
     * Snapshot 25: Parent: 0, $B_1$: 0, $B_2$: 0, $B_3$: 1000 nodes ($100\%$ reorg convergence).

---

## 4. Completed Project Milestone
All 5 modular steps are complete and verified! The codebase is ready for live execution on the 1,000-node RegTest network whenever the nodes are started.
