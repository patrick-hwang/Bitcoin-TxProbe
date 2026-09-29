# Checkpoint: Step 2 — INVBLOCK Pre-filtering (Dual-Condition Filter)

**Date**: 2026-09-29 22:18  
**Status**: Completed & Verified  

---

## 1. Completed Tasks Summary (Since Previous Checkpoint)

1. **Step 2 INVBLOCK Pre-filtering Implementation (`txprobe.invblock`)**:
   - Implemented a **Dual-Condition Filtering Pipeline** that solves both P2P relay unresponsiveness and INVBLOCK protocol violations:
     - **Filter 1 (Relay Responsiveness)**: Probe 0 broadcasts an unbroadcast test transaction inventory (`sendinv_orphan`) to all active peers and waits for responses. Nodes failing to respond with `GETDATA` are classified as non-responsive (e.g., nodes in Initial Block Download (IBD), running in `-blocksonly` mode, crawler/spider bots, or experiencing high-latency network drops) and are eliminated.
     - **Filter 2 (INVBLOCK Compliance)**: Probe 1 then announces the identical transaction inventory to all responsive peers. Nodes that erroneously send a duplicate `GETDATA` to Probe 1 despite the transaction already being in-flight / blocked from Probe 0 violate Bitcoin Core's duplicate inventory suppression and are eliminated.
   - Implemented parallel disconnect (`disconnectnode` + `addnode remove`) on both Probe 0 and Probe 1 for all eliminated nodes.
   - Clears probe memory via `clearinv_probe()` on both probes concurrently upon completion.
   - Prunes the network topology (`GraphSnapshot`), eliminating disconnected and malfunctioning nodes while preserving all valid internal edges between surviving nodes.
2. **Transaction Crafting for Probing (`craft_dummy_test_transaction` & `craft_test_transaction`)**:
   - Implemented pure-Python, zero-dependency valid raw Bitcoin transaction generation (1-input, 1-output P2WPKH, valid double-SHA256 txid/wtxid) with nonce seeding so tests can run without wallet dependencies or Testnet4 faucet UTXOs.
   - Added RPC fallback to `createrawtransaction` + `decoderawtransaction` when connected to a live bitcoind node.
3. **Log Parsing & Pre-clearing Engine (`parse_getdata_peers_from_log` & `clear_log_file`)**:
   - Added `clear_log_file(log_path)` to safely truncate probe log files before a run begins (`clear_logs=True`), eliminating unbounded file growth and ensuring tests only process current events.
   - Parses custom `bitcoind` log output targeting both `BLOCKED_NOTFOUND peer=<id> addr=<addr> hash=<hash>` and `received getdata for: <type> <hash> peer=<id>`.
   - Filters strictly by target transaction hash to prevent interference from historical log entries.
4. **Graph Pruning Methods (`txprobe.models.graph`)**:
   - Added `GraphSnapshot.prune_nodes(keep_nodes)` and `GraphSnapshot.remove_nodes(remove_nodes)` returning a new immutable `GraphSnapshot` with updated node tuples and adjacency lists.
5. **Config & Startup Enhancements**:
   - Added `NodeConfig.txprobe_log_file` and `Config.invblock` (`InvblockConfig.wait_time_sec`).
   - Updated [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml) with `txprobe_0.log` and `txprobe_1.log` configuration.
   - Updated [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh) to launch Probe 0 and Probe 1 with `-txprobelogfile="txprobe_${i}.log"`, ensuring clean multi-process log isolation.
6. **CLI Script (`txprobe/scripts/filter_invblock.py`)**:
   - Created CLI entry point with progress reporting via `tqdm`, accepting `--groundtruth-file`, `--config`, `--wait-time`, and `--no-clear-logs`, outputting `filtered_groundtruth.json`.

---

## 2. Added & Modified Files

### Modified Files:
- [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh): Added `-txprobelogfile="txprobe_${i}.log"` parameter for Node 0 and Node 1.
- [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml): Configured `txprobe_log_file: txprobe_0.log` (Node 0), `txprobe_1.log` (Node 1), and `invblock.wait_time_sec: 5.0`.
- [`txprobe/txprobe/config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py): Added `NodeConfig.txprobe_log_file`, `InvblockConfig`, and post-init defaults on `Config`.
- [`txprobe/txprobe/models/graph.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/graph.py): Added `prune_nodes` and `remove_nodes` to `GraphSnapshot`.
- [`txprobe/txprobe/rpc/client.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/rpc/client.py): Added `sendinv_orphan`, `clearinv_probe`, `createrawtransaction`, and `decoderawtransaction` to `AsyncBitcoinRpc`.

### Created Files:
- [`txprobe/txprobe/invblock.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/invblock.py): Step 2 INVBLOCK Pre-filtering core engine and data models (`InvblockStats`, `InvblockResult`, `run_invblock_prefilter`, `clear_log_file`).
- [`txprobe/scripts/filter_invblock.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/filter_invblock.py): Step 2 CLI command line script.
- [`txprobe/tests/test_invblock.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_invblock.py): 9 comprehensive unit tests for Step 2.

---

## 3. Unit Tests of Each Function (Inputs, Outputs & Results)

All **73 unit tests** across the entire test suite passed (`73 passed in 0.61s`):

| Function / Method | Test Case | Input | Expected Output | Result |
|---|---|---|---|---|
| `craft_dummy_test_transaction` | `test_craft_dummy_test_transaction` | Nonce seeds `"seed1"` and `"seed2"` | Valid 64-char hex `txid`/`wtxid`, distinct transactions | **PASSED** |
| `craft_test_transaction` | `test_craft_test_transaction_fallback_on_rpc_error` | Mock RPC throwing `RuntimeError` | Graceful fallback to pure-Python valid `TxMessage` | **PASSED** |
| `parse_getdata_peers_from_log` | `test_parse_getdata_peers_from_log` | Log with `BLOCKED_NOTFOUND`, `received getdata`, mismatched hashes, and malformed lines | Extracts exactly `{"1.2.3.4:48333", "9.10.11.12:48333"}` | **PASSED** |
| `parse_getdata_peers_from_log` | `test_parse_getdata_peers_missing_log` | Path to non-existent log file | Returns `set()` safely without exception | **PASSED** |
| `clear_log_file` | `test_clear_log_file` | Existing log file with text & non-existent path | Empties file to 0 bytes; handles missing file gracefully | **PASSED** |
| `GraphSnapshot.prune_nodes` / `remove_nodes` | `test_graph_snapshot_prune_and_remove_nodes` | 3 nodes (`n1, n2, n3`), 2 edges; prune to `[n1, n2]` | 2 nodes, 1 mutual edge `(n1, n2)`, drops edge with `n3` | **PASSED** |
| `disconnect_peers_parallel` | `test_disconnect_peers_parallel` | 2 addresses `["1.1.1.1:48333", "2.2.2.2:48333"]` | Calls `disconnectnode` and `addnode remove` 2 times each | **PASSED** |
| `run_invblock_prefilter` | `test_run_invblock_prefilter_dual_condition` | 4 nodes: `A` (good), `B` (non-responsive to P0), `C` (violating P1), `D` (dropped on P1) | Only `A` qualified; `B` in `eliminated_nonresponsive`, `C` in `eliminated_violating`, `clearinv_probe` called on both | **PASSED** |
| `InvblockResult.save` / `load` | `test_invblock_result_save_and_load` | `InvblockResult` with 1 qualified node, 1 eliminated node | Exact roundtrip serialization with stats and topology | **PASSED** |

---

## 4. Next Step to Implement

**Step 3: Raw Transaction Crafting**:
- Design and implement the transaction generation engine for TxProbe rounds:
  - Generate $n+1$ conflicting parent transactions ($ptx_1 \dots ptx_n$) and 1 flooding transaction ($ftx$) spending from the exact same UTXO outpoint.
  - Generate $n$ marker transactions ($mtx_1 \dots mtx_n$), each spending from the corresponding parent transaction $ptx_i$.
  - Manage UTXO splitting / funding or automated transaction chain signing for matrix batches.
