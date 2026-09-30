# Checkpoint: Step 4 — TxProbe Execution Loop & Multi-Round Topology Inference

**Date**: 2026-09-30 18:18  
**Status**: Completed & Verified  

---

## 1. Completed Tasks Summary (Since Previous Checkpoint)

1. **Method 2 Multi-Round Topology Inference (`run_txprobe_execution` & `execute_single_round`)**:
   - Initializes the candidate edge set as a Complete Graph ($K_V$) over all qualified nodes in `crafting_result.snapshot.nodes`.
   - In each round $r$, whenever sink node $k_j$ sends `GETDATA` for `marker_txs[i]` (`mtx_i`), permanently discards edge $\{s_i, k_j\}$ from `candidate_edges`.
   - Retains only pairs that were validly tested in at least 1 round (`candidate_edges & tested_pairs`) and builds the symmetric undirected `inferred_snapshot` via `build_inferred_snapshot_from_edges`.
2. **Double Log Clearing (Step 2.5 & Step 2.6)**:
   - **Clear Log #1 (Step 2.5)**: Calls `clear_log_file(probe_0_log_path)` right after `clearinv_probe()` and before sending `marker_txs[i]` to `source_nodes[i]`, eliminating all `GETDATA` log lines generated during Step 2.2 (`INVBLOCK`).
   - **Clear Log #2 (Step 2.6)**: After parsing Step 2.5's log for parent `GETDATA` requests, calls `clear_log_file(probe_0_log_path)` a second time before `sendinv_orphan(marker_txs, all_active_pids)` so Step 2.7 only sees `GETDATA` responses to the marker `INV` query.
3. **Unified Log-Based Malfunctioning Source Detection (`detect_malfunctioning_sources`)**:
   - Replaces the validation-only `getrawmempool` RPC check with a uniform log-based check across all ~1000 nodes (both public and groundtruth nodes):
     - If source $s_i$ rejected `parent_txs[i]` (because `flood_tx` or another conflicting parent leaked into its mempool prior to Step 2.4), then upon receiving `marker_txs[i]` in Step 2.5, `marker_txs[i]` enters `txorphanage` (`TX_MISSING_INPUTS`) and Bitcoin Core's orphan resolution (`MaybeAddOrphanResolutionCandidate`) sends `GETDATA` for `parent_txs[i]` back to Probe 0.
     - Or in Step 2.6, $s_i$ sends `GETDATA` for `marker_txs[i]` back to Probe 0.
   - Any source $s_i$ requesting its own `parent_txs[i]` or `marker_txs[i]` is flagged as malfunctioning, excluded from edge inference in that round and subsequent rounds, and pruned from both `inferred_snapshot` and `filtered_groundtruth_snapshot`.
4. **Post-Round `txorphanage` Cleanup (`build_cleanup_batch_calls`, Step 2.8)**:
   - In Step 2.6, `sendinv_orphan(marker_txs, all_active_pids)` announces all marker transactions to **both active sources and active sinks**, registering `probe_0` as an announcer (`m_orphanage->AddAnnouncer`) on every node holding `mtx_i` in its `txorphanage`.
   - In Step 2.8, calls `clearinv_probe()` and batch-sends `parent_txs[i]` to all active peers except `active_sources[i]`, plus `flood_tx` to all active sources via `sendrawtransaction_orphan`. This triggers Bitcoin Core's 1P1C package evaluation (`Find1P1CPackage` $\to$ `ProcessPackageResult` $\to$ `EraseTx`) so every peer evicts `mtx_i` from `txorphanage` before round $r+1$, with zero DoS/misbehavior penalty.
5. **Configuration, Data Models & CLI Entry Point**:
   - Added [`TxProbeExecutionConfig`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py) (`invblock_wait_sec=5.0`, `flood_wait_sec=1.0`, `parent_wait_sec=5.0`, `marker_propagation_wait_sec=10.0`, `getdata_wait_sec=5.0`, `cleanup_wait_sec=2.0`) to [`txprobe/txprobe/config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py) and [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml).
   - Added [`RoundExecutionResult`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/probing.py), [`TxProbeExecutionStats`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/probing.py), and [`TxProbeExecutionResult`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/probing.py) with full JSON serialization and incremental per-round checkpointing.
   - Created CLI script [`txprobe/scripts/run_txprobe.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/run_txprobe.py) outputting `txprobe_execution.json` and `txprobe_execution_checkpoint.json`.

---

## 2. Added & Modified Files

### Modified Files:
- [`txprobe/txprobe/config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py): Added `TxProbeExecutionConfig` and integrated into `Config` and `load_config`.
- [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml): Added `txprobe_execution` configuration section.
- [`txprobe/tests/test_config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_config.py): Added `test_txprobe_execution_config_defaults_and_custom`.

### Created Files:
- [`txprobe/txprobe/probing.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/probing.py): Core Step 4 TxProbe execution and multi-round topology inference implementation.
- [`txprobe/scripts/run_txprobe.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/run_txprobe.py): CLI entry point for Step 4.
- [`txprobe/tests/test_probing.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_probing.py): 9 unit tests covering Step 4 functions, double log clearing, log-based malfunction detection, orphanage cleanup, and multi-round Complete Graph $\to$ Discard inference.

---

## 3. Unit Tests of Each Function (Inputs, Outputs & Results)

All **95 unit tests** across the test suite passed (`95 passed in 0.74s`):

| Function / Method | Test Case | Input | Expected Output | Result |
|---|---|---|---|---|
| `load_config` (`TxProbeExecutionConfig`) | `test_txprobe_execution_config_defaults_and_custom` | Default YAML vs custom `txprobe_execution` section | Default timings `(5.0, 1.0, 5.0, 10.0, 5.0, 2.0)` and custom overrides `(3.5, 0.5, 4.0, 8.0, 6.0, 1.5)` | **PASSED** |
| `canonical_edge` | `test_canonical_edge` | `("10.0.0.2:48333", "10.0.0.1:48333")` and reversed | Symmetric tuple `("10.0.0.1:48333", "10.0.0.2:48333")` | **PASSED** |
| `extract_eligible_peer_maps` | `test_extract_eligible_peer_maps` | Peer list with `manual`, `127.0.0.1`, `block-relay-only`, `.onion`, `id=None` | Filters out loopback, `block-relay-only`, and missing IDs; returns `addr_to_id` & `id_to_addr` | **PASSED** |
| `parse_getdata_by_tx_from_log` | `test_parse_getdata_by_tx_from_log_txid_and_wtxid` | Log with `BLOCKED_NOTFOUND` (known + `unknown` addr) and `received getdata` matching `txid` & `wtxid` | `{"1.1.1.1:48333": {0, 2}, "2.2.2.2:48333": {1}}` | **PASSED** |
| `detect_malfunctioning_sources` | `test_detect_malfunctioning_sources` | `s0` requests `ptx_0` in Step 2.5; `s1` requests `mtx_0`; `s2` requests `mtx_2` in Step 2.6 | Returns `{s0, s2}` (`s1` is not malfunctioning because `0 != 1`) | **PASSED** |
| `build_cleanup_batch_calls` | `test_build_cleanup_batch_calls` | 2 sources (`pid 1, 2`), 2 sinks (`pid 3, 4`), `ptx0, ptx1, ftx` | 3 batch `sendrawtransaction_orphan` calls (`ptx0 -> [2,3,4]`, `ptx1 -> [1,3,4]`, `ftx -> [1,2]`) | **PASSED** |
| `build_inferred_snapshot_from_edges` | `test_build_inferred_snapshot_from_edges` | 3 nodes `(n0, n1, n2)`, edges `{n0, n2}`, `{n1, n2}`, self-loop `{n0, n0}` | Symmetric `GraphSnapshot` with 3 nodes, 2 edges, self-loop ignored | **PASSED** |
| `execute_single_round` | `test_execute_single_round_double_log_clear_and_edge_discard` | 2 sources, 2 sinks, stale `INVBLOCK` noise in log, `k0` connected to `s0` | Stale noise cleared; `sendinv_orphan` sent to all `[1,2,3,4]`; 3 edges discarded, `{s0, k0}` kept; 3 cleanup calls executed | **PASSED** |
| `execute_single_round` | `test_execute_single_round_malfunctioning_source_and_midround_disconnect` | `s1` requests `ptx1` in Step 2.5; `k1` disconnects before Step 2.7 | `malfunctioning_sources=(s1,)`, `dropped_nodes=(k1,)`, only `{s0, k0}` tested | **PASSED** |
| `run_txprobe_execution` & `TxProbeExecutionResult` | `test_run_txprobe_execution_complete_graph_discard_multi_round` | 4-node graph ($K_4 = 6$ candidate edges), 2 matrix rounds, true edge `{n0, n2}` | Discards 5 non-edges across 2 rounds, retains only `{n0, n2}`; saves checkpoint & passes JSON roundtrip | **PASSED** |

---

## 4. Next Step to Implement

**Step 5: Malfunction Filtering & Post-Probing Groundtruth Reconciliation**:
- Capture a fresh post-probing groundtruth snapshot (`final_groundtruth.json`) from Groundtruth nodes `[2..6]` and Probe nodes `[0, 1]` immediately after Step 4 completes.
- Reconcile node and edge churn across `initial_groundtruth.json` (Step 1), `filtered_groundtruth.json` (Step 2), `txprobe_execution.json` (Step 4 malfunctioning + dropped nodes), and `final_groundtruth.json` so that transitory edges (edges that formed or broke mid-experiment) and malfunctioning/disconnected nodes are cleanly filtered before Step 6 metric calculation.
