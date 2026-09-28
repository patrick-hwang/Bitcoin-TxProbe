# Checkpoint: Step 1 — Groundtruth Capture & Dual-Pool Connection Optimization

**Date**: 2026-09-29 01:25  
**Status**: Completed & Verified  

---

## 1. Completed Tasks Summary (Since Previous Checkpoint)

1. **Step 0 Enhancements (Fast Dual-Pool Connection + Groundtruth Self-Identities)**:
   - Updated [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh) to launch `bitcoind` with `-rpcthreads=64 -rpcworkqueue=256`.
   - Updated [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml) and [`DiscoveryConfig`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py#L24-L31):
     - `crawling_time_sec = 180.0`, `poll_interval_sec = 5.0`.
     - Split concurrency into `clearnet_onetry_concurrency: int = 32` and `tor_onetry_concurrency: int = 8`.
   - Updated [`txprobe/txprobe/discovery/harvester.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/discovery/harvester.py):
     - Added Step 1.0 (`_harvest_groundtruth_self_parallel` / `_harvest_groundtruth_self_one`) to harvest the `.onion` identities of Groundtruth nodes (`2..6`) via `getnetworkinfo()["localaddresses"]` at the very front of `CandidatePriority.GROUNDTRUTH_PEER` (skipping external reachability testing since they just answered RPC).
   - Updated [`txprobe/txprobe/discovery/peer_scanner.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/discovery/peer_scanner.py):
     - Added `_split_clearnet_and_tor` and launched 2 independent concurrent worker pools per probe node (Clearnet 32 threads + Tor 8 threads) at $t=0$, eliminating head-of-line blocking between Tor and Clearnet.
2. **Graph Model Extensions (`txprobe.models.graph`)**:
   - Added `num_nodes`, `num_edges` properties and `save(path)` / `load(path)` methods to [`GraphSnapshot`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/graph.py#L14-L78).
3. **Step 1 — Groundtruth Capture (`txprobe.groundtruth`)**:
   - Implemented [`GroundtruthStats`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/groundtruth.py#L25-L34) and [`GroundtruthResult`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/groundtruth.py#L37-L106) dataclasses with JSON serialization (`to_dict`, `save`, `from_dict`, `load`).
   - Implemented [`get_node_onion_identity`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/groundtruth.py#L109-L152) and [`fetch_groundtruth_identities`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/groundtruth.py#L155-L176) to query `getnetworkinfo()` on Groundtruth nodes (`2..6`) in parallel.
   - Implemented [`capture_initial_groundtruth`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/groundtruth.py#L179-L299):
     - Queries Groundtruth identities and Probe 0 / Probe 1 peer lists in parallel.
     - Prunes any target node that disconnected from either probe since Step 0 and disconnects half-dropped peers on the remaining probe.
     - Queries `getpeerinfo()` on online Groundtruth nodes (`2..6`), filtering out `127.0.0.1*`, `feeler`, `addr-fetch`, `block-relay-only`, and `version <= 0`.
     - Constructs a deterministic, symmetric undirected `adj_list` and returns `GroundtruthResult`.
4. **CLI Groundtruth Script (`txprobe/scripts/capture_groundtruth.py`)**:
   - Reads `--nodes-file` (`discovered_nodes.json`), executes `capture_initial_groundtruth`, and writes `initial_groundtruth.json`.

---

## 2. Added & Modified Files

### Modified Files:
- [`txprobe/A_start_nodes.sh`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/A_start_nodes.sh): Added `-rpcthreads=64 -rpcworkqueue=256`.
- [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml): Set `crawling_time_sec: 180`, `poll_interval_sec: 5`, `clearnet_onetry_concurrency: 32`, `tor_onetry_concurrency: 8`.
- [`txprobe/txprobe/config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py): Updated `DiscoveryConfig` and `load_config` with `clearnet_onetry_concurrency` and `tor_onetry_concurrency`.
- [`txprobe/txprobe/rpc/client.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/rpc/client.py): Added `AsyncBitcoinRpc.getnetworkinfo()`.
- [`txprobe/txprobe/discovery/harvester.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/discovery/harvester.py): Added `groundtruth_self_count`, `_harvest_groundtruth_self_parallel`, `_harvest_groundtruth_self_one`.
- [`txprobe/txprobe/discovery/peer_scanner.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/discovery/peer_scanner.py): Added `_split_clearnet_and_tor` and dual-pool concurrent `onetry` workers per probe.
- [`txprobe/txprobe/models/graph.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/graph.py): Added `num_nodes`, `num_edges`, `save()`, and `load()` to `GraphSnapshot`.
- [`txprobe/scripts/harvest_addresses.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/harvest_addresses.py): Added `Groundtruth self (P0)` output line.

### Created Files:
- [`txprobe/txprobe/groundtruth.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/groundtruth.py): Step 1 Groundtruth Capture implementation.
- [`txprobe/scripts/capture_groundtruth.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/capture_groundtruth.py): CLI entry point for Step 1.
- [`txprobe/tests/test_groundtruth.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_groundtruth.py): Unit tests for Step 1.

---

## 3. Unit Tests of Each Function (Inputs, Outputs & Results)

All **64 unit tests** across the test suite passed (`64 passed in 0.65s`):

| Function / Method | Test Case | Input | Expected Output | Result |
|---|---|---|---|---|
| `_harvest_groundtruth_self_one` | `test_harvest_groundtruth_self_identity` | Node 2 `localaddresses` with `gt2node.onion:48333` | Appends `CandidateNode("gt2node.onion:48333", GROUNDTRUTH_PEER, "onion", 2)` | **PASSED** |
| `_split_clearnet_and_tor` | `test_split_clearnet_and_tor_separates_and_skips_already_connected` | `[gt2.onion, 1.1.1.1, 2.2.2.2]` with `1.1.1.1` already connected | `clearnet=["2.2.2.2:48333"]`, `tor=["gt2.onion:48333"]` | **PASSED** |
| `get_node_onion_identity` | `test_get_node_onion_identity_prefers_onion` | `localaddresses` containing both IPv4 `8.8.8.8` and `gt2abc.onion` | Returns `NodeIdentity("gt2abc.onion:48333")` | **PASSED** |
| `get_node_onion_identity` | `test_get_node_onion_identity_offline_returns_none` | Node RPC raises `ConnectionRefusedError` | Returns `None` gracefully without raising | **PASSED** |
| `fetch_groundtruth_identities` | `test_fetch_groundtruth_identities_parallel` | Node 2 has `gt2.onion`, Node 3 has empty `localaddresses` | Returns `{2: NodeIdentity("gt2.onion:48333")}` | **PASSED** |
| `capture_initial_groundtruth` | `test_capture_initial_groundtruth_builds_symmetric_adj_and_prunes_dropped` | 5 target nodes (`gt2, gt3, peer_a, peer_b, peer_dropped`), `peer_dropped` missing on Probe 1, `peer_b` is `block-relay-only` on `gt2` | Prunes `peer_dropped` (`active_nodes_count=4`, `pruned_disconnected_count=1`), ignores `block-relay-only` edge, builds 3 symmetric undirected edges `(gt2, peer_a)`, `(gt3, peer_b)`, `(gt3, gt2)` | **PASSED** |
| `GroundtruthResult.save` / `load` & `GraphSnapshot.save` / `load` | `test_groundtruth_result_save_and_load` | `GroundtruthResult` with 2 nodes, 1 edge | Roundtrip JSON preserves `groundtruth_identities`, `snapshot`, `num_nodes=2`, `num_edges=1`, and `stats` | **PASSED** |

---

## 4. Next Step to Implement

**Step 2: INVBLOCK Pre-filtering**:
- Create a dummy/test transaction on Probe 0 (or use an unbroadcast transaction), send its `INV` to all active peers on Probe 0 and Probe 1 via `sendinv_orphan` to block them, then verify whether any peer improperly requests `GETDATA` (or fails to support `sendinv_orphan` / INV-blocking), and filter out malfunctioning nodes from the active `GraphSnapshot`.
