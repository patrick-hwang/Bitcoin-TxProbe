# Checkpoint: Step 0 — Phase 2 (Batch Connection & Probe Selection)

**Date**: 2026-09-29 00:38  
**Status**: Completed & Verified  

---

## 1. Completed Tasks Summary (Since Previous Checkpoint)

1. **Linux Environment & Probe Role Reconfiguration (`Node 0` & `Node 1` as Probes)**:
   - Aligned node roles with [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh):
     - **Probe Nodes**: Node `0` (`rpcport: 48347`, `wallet: mywallet`) and Node `1` (`rpcport: 48332`), running custom `[TxProbe]` `bitcoind`.
     - **Groundtruth Nodes**: Nodes `2, 3, 4, 5, 6` (`rpcport: 48335, 48338, 48341, 48344, 48350`), running `[Official 31.1]` `bitcoind`.
   - Added `rpchost: str = "127.0.0.1"` to `NodeConfig` to support both local execution on the Linux server and remote RPC connections.
   - Updated `DiscoveryConfig` default `crawling_time_sec` from `180.0` to `600.0` seconds (10 minutes) and added `onetry_concurrency: int = 12`.
2. **Tolerant Batch RPC Execution (`txprobe.rpc.client`)**:
   - Enhanced `AsyncBitcoinRpc.call_batch` with `raise_on_error: bool = True` (default `True` for backward compatibility).
   - When `raise_on_error=False`, individual RPC errors within a batch (e.g., `disconnectnode` on an already-disconnected peer) are logged at `DEBUG` level and return `None` without aborting the remaining calls in the batch.
   - Added empty-batch guard (`if not calls: return []`).
3. **Dynamic Probe Tracking & Serialization in Phase 1 (`txprobe.discovery.harvester`)**:
   - Refactored `HarvestResult` to store `already_connected_probes: dict[int, set[NodeIdentity]]` keyed dynamically by probe node ID (`0` and `1`) instead of hardcoded `probe0` / `probe6` fields.
   - Added `HarvestResult.from_dict(data)` and `HarvestResult.load(path)` for loading `harvest.json` into Phase 2.
4. **Phase 2 Peer Scanner & Selector (`txprobe.discovery.peer_scanner`)**:
   - Implemented `ScanStats` and `ScanResult` dataclasses with JSON serialization (`to_dict`, `save`, `from_dict`, `load`, `selected_identities`).
   - Implemented `_order_candidates_for_dispatch`: orders candidates by `(priority, is_onion)` so fast clearnet candidates are connected before slower Tor `.onion` candidates within each priority tier.
   - Implemented `_dispatch_onetry_worker`: dispatches concurrent `addnode(addr, "onetry")` RPC calls bounded by `asyncio.Semaphore(onetry_concurrency=12)` per probe node, halting immediately when `stop_event` is set.
   - Implemented `_extract_valid_probe_peers`: filters `getpeerinfo()` output to exclude `127.0.0.1*`, `feeler`, `addr-fetch`, `block-relay-only`, and unhandshaked connections (`version <= 0`).
   - Implemented `scan_and_select_peers`:
     - Runs `_dispatch_onetry_worker` on Probe 0 and Probe 1 concurrently alongside the polling loop.
     - Polls `getpeerinfo()` every `poll_interval_sec` (`10s`) up to `crawling_time_sec` (`600s`), exiting early as soon as `|P_0 ∩ P_1 ∩ Candidates| >= target_count` (`1000`).
     - Selects up to `target_count` mutually connected peers while strictly preserving `CandidatePriority` order (`GROUNDTRUTH_PEER` $\to$ `PROBE_PEER` $\to$ `DNS_SEED` $\to$ `ADDRMAN`).
     - Finalizes connections by calling `disconnectnode(addr)` in batches on excess peers only (no `addnode "add"` or `addnode "remove"` needed since `"onetry"` establishes persistent `ConnectionType::MANUAL` connections).
5. **CLI Peer Selection Script (`txprobe/scripts/select_peers.py`)**:
   - Supports running Phase 2 from an existing `--harvest-file` (`harvest.json`) or running Phase 1 + Phase 2 end-to-end, saving output to `results/<timestamp>/discovered_nodes.json`.

---

## 2. Added & Modified Files

### Modified Files:
- [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml): Set nodes `0, 1` to `role: probe`, nodes `2..6` to `role: groundtruth`, `crawling_time_sec: 600`, `onetry_concurrency: 12`.
- [`txprobe/txprobe/config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py): Added `rpchost` to `NodeConfig`, `onetry_concurrency` to `DiscoveryConfig`, updated default `crawling_time_sec` to `600.0`.
- [`txprobe/txprobe/rpc/client.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/rpc/client.py): Added `raise_on_error: bool = True` and empty-list handling to `AsyncBitcoinRpc.call_batch`.
- [`txprobe/txprobe/discovery/harvester.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/discovery/harvester.py): Replaced hardcoded probe sets with `already_connected_probes: dict[int, set[NodeIdentity]]`, added `HarvestResult.from_dict` and `HarvestResult.load`, used `nc.rpchost`.
- [`txprobe/txprobe/discovery/__init__.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/discovery/__init__.py): Exported Phase 1 and Phase 2 classes and functions.
- [`txprobe/tests/test_config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_config.py): Added `test_testnet4_yaml_probes_are_0_and_1` and `onetry_concurrency` assertions.
- [`txprobe/tests/test_rpc_client.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_rpc_client.py): Added `test_batch_raise_on_error_false` and `test_batch_empty`.
- [`txprobe/tests/test_harvester.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_harvester.py): Updated test config to probes `(0, 1)` and added `test_harvest_result_save_and_load`.

### Created Files:
- [`txprobe/txprobe/discovery/peer_scanner.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/discovery/peer_scanner.py): `ScanStats`, `ScanResult`, `scan_and_select_peers`, `_order_candidates_for_dispatch`, `_extract_valid_probe_peers`, `_fetch_valid_probe_peers`, `_dispatch_onetry_worker`, `_disconnect_excess_peers`.
- [`txprobe/scripts/select_peers.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/select_peers.py): CLI entry point for Phase 2.
- [`txprobe/tests/test_peer_scanner.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_peer_scanner.py): Comprehensive unit tests for Phase 2.

---

## 3. Unit Tests of Each Function (Inputs, Outputs & Results)

All **58 unit tests** across the test suite passed (`58 passed in 0.78s`):

| Function / Method | Test Case | Input | Expected Output | Result |
|---|---|---|---|---|
| `load_config` | `test_testnet4_yaml_probes_are_0_and_1` | `config/testnet4.yaml` | `probe_nodes=[0, 1]`, `groundtruth_nodes=[2,3,4,5,6]`, `crawling_time_sec=600.0`, `onetry_concurrency=12` | **PASSED** |
| `AsyncBitcoinRpc.call_batch` | `test_batch_raise_on_error_false` | 2 calls (`disconnectnode`), second returns RPC error `-29`, `raise_on_error=False` | Returns `["ok", None]` without raising `RpcError` | **PASSED** |
| `AsyncBitcoinRpc.call_batch` | `test_batch_empty` | `calls=[]` | Returns `[]` without making HTTP POST | **PASSED** |
| `HarvestResult.save` / `load` | `test_harvest_result_save_and_load` | `HarvestResult` with 2 candidates and `already_connected_probes` for probes `0, 1` | Roundtrip JSON file preserves all candidates, priorities, probe sets, and stats | **PASSED** |
| `_order_candidates_for_dispatch` | `test_order_candidates_for_dispatch_clearnet_before_onion` | `[P2 ipv4, P0 onion, P0 ipv4]` | `[P0 ipv4, P0 onion, P2 ipv4]` (clearnet before onion within same priority) | **PASSED** |
| `_extract_valid_probe_peers` | `test_extract_valid_probe_peers_filters_invalid_types` | 7 mock `getpeerinfo` entries (`127.0.0.1`, `feeler`, `addr-fetch`, `block-relay-only`, `version=0`, `manual`, `outbound-full-relay`) | Returns only the 2 valid handshaked full-relay peers | **PASSED** |
| `_disconnect_excess_peers` | `test_disconnect_excess_peers_batches_only_non_selected` | `selected={1.1.1.1, 2.2.2.2}`, `current={1.1.1.1, 3.3.3.3, 4.4.4.4}`, `chunk_size=1` | Dispatches 2 `call_batch` calls for `3.3.3.3` and `4.4.4.4` with `raise_on_error=False`, returns `2` | **PASSED** |
| `scan_and_select_peers` | `test_scan_requires_two_probes` | Config with only 1 probe node | Raises `ValueError("At least 2 probe nodes are required...")` | **PASSED** |
| `scan_and_select_peers` | `test_scan_early_exit_and_priority_preservation` | 4 candidates `[P3, P0, P1, P2]`, `target_count=3`, `1.0.0.1` already on Probe 0 | Early exits (`early_exit=True`), selects `[P0, P1, P2]`, skips `onetry` for `1.0.0.1` on Probe 0, disconnects excess peers (`2` on P0, `1` on P1) | **PASSED** |
| `scan_and_select_peers` | `test_scan_graceful_when_below_target` | 2 candidates, `target_count=10`, only 1 mutually connected | Completes gracefully after timeout (`early_exit=False`), selects `[1.0.0.1:48333]`, disconnects non-mutual peer on P0 | **PASSED** |
| `ScanResult.save` / `load` | `test_scan_result_save_and_load` | `ScanResult` with 2 selected nodes and `ScanStats` | Roundtrip JSON serialization preserves `probe_ids`, `selected_nodes`, and all `stats` | **PASSED** |

---

## 4. Next Step to Implement

**Step 1: Groundtruth Capture**:
- Query groundtruth nodes (`2, 3, 4, 5, 6`) for their own identities (`getnetworkinfo` / local onion or clearnet addresses) and their active peer lists (`getpeerinfo`).
- Build the initial groundtruth `GraphSnapshot` containing the selected target nodes from Step 0 Phase 2 (`discovered_nodes.json`) and groundtruth adjacencies.
- Save the initial groundtruth topology snapshot to `results/<timestamp>/initial_groundtruth.json`.
