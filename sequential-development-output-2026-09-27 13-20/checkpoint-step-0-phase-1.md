# Checkpoint: Step 0 — Phase 1 (Initial Address Harvest)

**Date**: 2026-09-27 13:20  
**Status**: Completed & Verified  

---

## 1. Completed Tasks Summary

1. **C++ Connection Limits Raised**:
   - Modified `src/net.h`:
     - `MAX_ADDNODE_CONNECTIONS`: changed from `125` to `1100`.
     - `DEFAULT_MAX_PEER_CONNECTIONS`: changed from `125` to `1200`.
2. **Project Scaffolding (`txprobe/`)**:
   - Created clean, modular Python package at `C:\Bin\Bitcoin-TxProbe\txprobe\`.
   - Setup `pyproject.toml` with `setuptools.build_meta` and explicit package discovery.
   - Installed `txprobe` in editable mode with all dependencies (`aiohttp`, `python-socks`, `pytest`, `pytest-asyncio`, `pyyaml`, `tqdm`).
3. **Async JSON-RPC Client (`txprobe.rpc.client`)**:
   - Built `AsyncBitcoinRpc` with direct HTTP communication via `aiohttp.ClientSession`.
   - Native support for JSON-RPC batching (`call_batch`).
   - Standardized error handling via `RpcError`.
   - Modernized basic authentication using `aiohttp.encode_basic_auth` (zero deprecation warnings).
4. **Data Models (`txprobe.models`)**:
   - `NodeIdentity`: immutable identity tracking `host:port`.
   - `CandidateNode`: candidate node representation with priority, network type, source node id, last seen timestamp.
   - `CandidatePriority`: priority enum (`GROUNDTRUTH_PEER=0`, `PROBE_PEER=1`, `DNS_SEED=2`, `ADDRMAN=3`).
   - `TxMessage`: immutable representation of raw and signed transactions.
   - `GraphSnapshot`: immutable graph snapshot with JSON serialization.
   - `normalize_addr`, `_has_port`, `split_addr_port`: robust address format normalization supporting IPv4, bracketed IPv6 `[addr]:port`, and Tor `.onion:port`, with port range validation (1–65535).
5. **DNS Seed Resolution (`txprobe.discovery.dns_seeds`)**:
   - Asynchronous DNS resolution via `asyncio.getaddrinfo`.
   - Explicit `type=socket.SOCK_STREAM` filtering for TCP addresses.
   - Automatic IPv6 bracket formatting.
6. **Active Reachability Testing (`txprobe.discovery.reachability`)**:
   - Active TCP connect and testnet4 Bitcoin P2P `version` handshake (`TESTNET4_MAGIC = 0x1c163f28`, `PROTOCOL_VERSION = 70016`).
   - Remote node confirmation upon receiving `version` message (no `verack` wait required).
   - Tor `.onion` routing via SOCKS5 proxy (`127.0.0.1:9050`) using `python-socks`.
   - Concurrency throttling using `asyncio.Semaphore` (50 for clearnet, 20 for Tor).
7. **Phase 1 Harvest Orchestration (`txprobe.discovery.harvester`)**:
   - Four-stage harvest pipeline matching priority order:
     - Priority 0: Groundtruth nodes (1–5) peers via `getpeerinfo` (includes block-relay-only).
     - Priority 1: Probe nodes (0, 6) peers via `getpeerinfo` (skips block-relay-only without disconnecting).
     - Priority 2: DNS seeds (`seed.testnet4.bitcoin.sprovoost.nl`, `seed.testnet4.wiz.biz`).
     - Priority 3: Address manager via `getnodeaddresses(0)` on all 7 nodes.
   - Automatic reachability filtering for stages 0, 2, and 3; probe peers skip test as they are already connected.
   - Deduplication and output serialization to `HarvestResult` JSON.
8. **CLI Harvest Script (`scripts/harvest_addresses.py`)**:
   - Command-line entry point with `--config`, `--output-dir`, and `--verbose` flags.

---

## 2. Added & Modified Files

### Modified Files:
- [`src/net.h`](file:///C:/Bin/Bitcoin-TxProbe/src/net.h#L71-L81): Raised `MAX_ADDNODE_CONNECTIONS` to 1100, `DEFAULT_MAX_PEER_CONNECTIONS` to 1200.

### Created Package Files (`txprobe/`):
- `pyproject.toml`: Build system, metadata, dependencies.
- `config/testnet4.yaml`: Configuration file for testnet4, nodes 0–6, reachability and discovery parameters.
- `txprobe/__init__.py`: Package root.
- `txprobe/config.py`: `Config`, `NodeConfig`, `DiscoveryConfig`, `ReachabilityConfig`, `load_config`.
- `txprobe/models/__init__.py`: Re-exports models.
- `txprobe/models/node.py`: `CandidatePriority`, `NodeIdentity`, `CandidateNode`, `normalize_addr`, `_has_port`, `_is_ipv6`, `split_addr_port`.
- `txprobe/models/transaction.py`: `TxMessage`.
- `txprobe/models/graph.py`: `GraphSnapshot`.
- `txprobe/rpc/__init__.py`: Re-exports RPC client.
- `txprobe/rpc/client.py`: `AsyncBitcoinRpc`, `RpcError`.
- `txprobe/discovery/__init__.py`: Discovery package init.
- `txprobe/discovery/dns_seeds.py`: `resolve_dns_seeds`, `_resolve_one_seed`.
- `txprobe/discovery/reachability.py`: `test_reachability`, `batch_test_reachability`, `_build_version_message`, `_parse_message_header`, `_open_connection`, `_open_tor_connection`.
- `txprobe/discovery/harvester.py`: `harvest_addresses`, `_harvest_peers_parallel`, `_harvest_addrman_parallel`, `HarvestResult`, `HarvestStats`.
- `txprobe/ui/__init__.py`: UI init.
- `txprobe/ui/progress.py`: `wait_seconds_with_progressbar`.
- `scripts/harvest_addresses.py`: CLI execution script.
- `tests/__init__.py`: Test package init.
- `tests/test_config.py`: Unit tests for config loading.
- `tests/test_rpc_client.py`: Unit tests for async JSON-RPC client.
- `tests/test_reachability.py`: Unit tests for address normalization and P2P wire formatting.
- `tests/test_harvester.py`: Unit tests for priority ordering, deduplication, offline handling, and filtering.

---

## 3. Unit Test Results

All 47 tests passed with zero errors and zero warnings:

| Test File | Test Cases | Status |
|-----------|------------|--------|
| `tests/test_config.py` | 7 tests (basic load, nodes, properties, get_node, discovery config, reachability config, missing file error) | **47/47 PASSED** (100%) |
| `tests/test_harvester.py` | 8 tests (skip local, skip feeler, include block-relay for groundtruth, skip block-relay for probe, deduplication, IPv6 normalization, offline node resilience, priority ordering) | **PASSED** |
| `tests/test_reachability.py` | 25 tests (`_has_port` tests across IPv4/IPv6/Onion/port boundaries, `normalize_addr` tests, `split_addr_port` tests, `P2P` version header/payload serialization and parsing) | **PASSED** |
| `tests/test_rpc_client.py` | 7 tests (basic url, wallet url, auth header, call JSON format, call return result, call error raising, batch requests array) | **PASSED** |

Execution time: **0.41s**.

---

## 4. Next Step to Implement

**Step 0 — Phase 2: Batch Connection & Probe Selection**:
- Implement `txprobe.discovery.peer_scanner`:
  - Take prioritized candidate addresses from Phase 1.
  - Dispatch JSON-RPC batch `addnode("addr", "onetry")` from Probe 0 and Probe 6.
  - Implement polling loop with `CRAWLING_TIME = 180s` threshold and early exit when $\ge 1000$ mutually connected peers are found.
  - Intersect connected peers of Probe 0 and Probe 6.
  - Select 1000 targets, disconnect excess peers, and persist the selected 1000 nodes via `addnode("addr", "add")`.
  - Save final experiment peer list to `results/<timestamp>/discovered_nodes.json`.
