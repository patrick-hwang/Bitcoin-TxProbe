# Checkpoint Step 4: Continuous P2P Ingress Event Monitor & Subgraph Snapshotter

**Timestamp:** 2026-10-15 16:47:20  
**Module Directory:** `/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/`

---

## 1. Completed Task & Deliverables
- **Ingress Event Monitoring & Continuous Tracking Engine (`prober.py`):**
  - **Raw Event Logger (`BlockArrivalEvent`):** Captures high-precision arrival timestamps $\langle t, \text{node\_id}, \text{block\_hash}, \text{probe\_id} \rangle$.
  - **Timing Matrix (`NodeTimingInfo`):** Maps each of the 1,000 nodes to its earliest arrival timestamps for $B_1, B_2, B_3$ along with its BFS hop distance from the forker.
  - **Consensus Tip Evaluator (`get_node_active_tip`):** Determines which block any node $v$ considers active at continuous timestamp $t$ adhering strictly to Bitcoin consensus:
    1. Heavier chainwork ($B_3$ at height $h+2$) triggers instant chain reorganization.
    2. Head-to-head blocks at equal height ($B_1$ vs $B_2$) follow the first-seen arrival rule.
    3. Pre-fork nodes remain in the parent chain.
  - **Dynamic Continuous Snapshot Slicing (`get_subgraphs_at`, `generate_sliced_snapshots`):**
    - Evaluates complete network subgraph distribution at any instant $t \in \mathbb{R}$.
    - Generates discrete time-series slices at exact $10\text{ms}$ steps without floating-point accumulation drift.
  - **File Serialization (`export_to_json`):** Exports the output schema for height $H$ to `fork_subgraph_height_<H>.json`.
- **Unit Testing (`test_prober.py`):**
  - Tested event recording and duplicate arrival idempotence (preserving earliest timestamp).
  - Tested consensus tip state transitions across parent $\to B_1 \to B_2$ tiebreak $\to B_3$ reorg.
  - Tested subgraph partition counting and membership.
  - Tested $10\text{ms}$ interval generation and relative millisecond timing.
  - Tested JSON serialization with temporary file output.
  - Tested factory initialization with full 1,000-node topology and BFS hop distances.

---

## 2. Added Files, Classes, and Functions

### Added Files
- [`snapshot-forked-subgraph/one-forker/prober.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/prober.py)
- [`snapshot-forked-subgraph/one-forker/test_prober.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/test_prober.py)

### Added Classes & Functions
* **`BlockArrivalEvent`**: Dataclass representing a block announcement event.
* **`NodeTimingInfo`**: Dataclass representing per-node arrival timestamps and hop distance.
* **`SubgraphSnapshot`**: Dataclass holding discrete snapshot state (index, relative ms, subgraphs, node counts).
* **`SubgraphTracker`**: Core tracking engine managing timings, event logs, tip evaluation, and snapshot slicing.
  * `record_event(node_id, block_hash, timestamp, probe_id)`
  * `get_node_active_tip(node_id, t)`
  * `get_subgraphs_at(t, snapshot_index, rel_origin_t)`
  * `generate_sliced_snapshots(start_time, end_time, step_ms=10.0)`
  * `export_to_json(out_path, fork_metadata, snapshots, step_ms)`
* **`create_subgraph_tracker_from_config(height, parent_hash, b1_hash, b2_hash, b3_hash, config)`**: Factory instantiating tracker loaded with 1,000-node topology.

---

## 3. Test Results

Executed with `pytest snapshot-forked-subgraph/one-forker/ -v`:
* **All 22 unit tests passed** in $0.30\text{s}$.
  * `test_config.py`: 6 passed
  * `test_funding.py`: 7 passed
  * `test_block_builder.py`: 3 passed
  * `test_prober.py`: 6 passed

---

## 4. Next Step to Implement
* **Step 5:** **Forker Actuator & Master Orchestrator (`forker.py` and `run_experiment.py`)**
  - Implement `forker.py`:
    - Submits $B_1$ to Node 2 via `submitblock`.
    - Coordinates propagation wait (monitoring Hop-5 peripheral nodes until 100% convergence or analytical timeout).
    - Submits $B_2$ followed immediately by $B_3$ to trigger the chain reorganization.
  - Implement `run_experiment.py`:
    - Links funding, block crafting, forker publishing, and prober snapshotting into a master executable CLI.
    - Exports the final `fork_subgraph_height_<H>.json`.
  - Implement `test_forker.py`.
