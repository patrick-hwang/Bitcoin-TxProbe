# Checkpoint: Step 3 — Matrix Partitioning, UTXO Splitting & Raw Transaction Crafting

**Date**: 2026-09-30 01:28  
**Status**: Completed & Verified  

---

## 1. Completed Tasks Summary (Since Previous Checkpoint)

1. **Matrix Splitting Partitioner (`txprobe.transactions.compute_matrix_dimensions` & `generate_matrix_rounds`)**:
   - Implemented the full-network Matrix Splitting algorithm with $w = \min(\text{max\_source\_size}, \lceil\sqrt{rn}\rceil)$ and $h = \lceil rn / w \rceil$.
   - Guarantees $w \ge h$ for all networks up to $\text{max\_source\_size}^2 = 5,625$ nodes (producing $w + h - 2 = 62$ rounds for $1,000$ nodes without redundant column sub-splitting), while also supporting $w < h$ column chunking when $rn > \text{max\_source\_size}^2$.
   - Verifies that every pair of distinct nodes $\{u, v\}$ is separated into `(source_nodes, sink_nodes)` in at least one round.
2. **Automatic Single-Input UTXO Splitting (`calculate_split_outputs` & `split_single_utxo`)**:
   - Splits 1 large UTXO (`len(vin) == 1`) into as many $2,000\text{-sat}$ outputs as possible (capped at `max_outputs_per_split_tx = 500` to stay safely inside Bitcoin Core's `MAX_STANDARD_TX_WEIGHT` and `DEFAULT_KEYPOOL_SIZE = 1000` descriptor lookahead).
   - Places any leftover satoshis into the final output so zero funds are lost to excess miner fees.
3. **Smart UTXO Preparation & Mempool-Aware Polling (`prepare_utxos_for_rounds`)**:
   - Fast-path: When $\ge R$ confirmed UTXOs ($\ge 2,000\text{ sats}$) already exist, skips UTXO splitting completely and selects the $R$ smallest qualifying UTXOs (`sort by amount_sats ASC`) so large remainder UTXOs are preserved.
   - Distinguishes between `confirmed_ready` (`confirmations >= 1`) and `unconfirmed_ready` (`confirmations == 0` in mempool) so a pending split transaction never triggers a false "insufficient funds" warning.
   - Prompts the user with a Probe 0 `bech32` deposit address and exact satoshi deficit only when `confirmed_ready + unconfirmed_ready < R` after splitting all eligible large UTXOs.
4. **Batched Raw Transaction Pre-Crafting (`craft_conflicting_transactions`, `craft_marker_transactions`, `craft_all_rounds`)**:
   - Uses `AsyncBitcoinRpc.call_batch` to construct, sign, and decode all $n + 1$ conflicting transactions ($n$ `parent_txs` + $1$ `flood_tx`) and $n$ child `marker_txs` (with explicit `prevtxs` metadata) in just 6 HTTP batch requests per round.
   - Reuses a single bounded pool of $\max(n_r) + 1$ derived descriptor addresses across rounds (since each round spends a distinct `utxo[r]`), preventing wallet keypool exhaustion.
   - Uses exact integer satoshi arithmetic internally and 8-decimal string formatting (`sats_to_btc_str`) for JSON-RPC calls.
5. **Data Models, RPC Extensions & CLI Entry Point**:
   - Extended [`AsyncBitcoinRpc`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/rpc/client.py) with `from_node_config`, `listwallets`, `loadwallet`, `listunspent`, `listdescriptors`, `deriveaddresses`, `getnewaddress`, `signrawtransactionwithwallet`, `sendrawtransaction`, and `sendrawtransaction_orphan`.
   - Added [`UtxoInfo`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/transaction.py), [`MatrixRound`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/transaction.py), [`TxProbeRoundTxs`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/transaction.py), [`TxCraftingStats`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/transaction.py), and [`TxProbeCraftingResult`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/transaction.py).
   - Added [`TxCraftingConfig`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py) to `config.py` and [`testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml).
   - Created CLI script [`txprobe/scripts/craft_transactions.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/craft_transactions.py) outputting `crafted_rounds.json`.

---

## 2. Added & Modified Files

### Modified Files:
- [`txprobe/txprobe/rpc/client.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/rpc/client.py): Added `from_node_config` and wallet/raw-transaction RPC wrappers.
- [`txprobe/txprobe/config.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/config.py): Added `TxCraftingConfig` and integrated into `Config` and `load_config`.
- [`txprobe/config/testnet4.yaml`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/config/testnet4.yaml): Added `tx_crafting` configuration section.
- [`txprobe/txprobe/models/transaction.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/transaction.py): Added `UtxoInfo`, `MatrixRound`, `TxProbeRoundTxs`, `TxCraftingStats`, and `TxProbeCraftingResult`.
- [`txprobe/txprobe/models/__init__.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/models/__init__.py): Exported new transaction and round models.

### Created Files:
- [`txprobe/txprobe/transactions.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/txprobe/transactions.py): Core Step 3 implementation.
- [`txprobe/scripts/craft_transactions.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/scripts/craft_transactions.py): CLI script for Step 3.
- [`txprobe/tests/test_transactions.py`](file:///d:/MAIN%20QUEST%2003%20-%20Bitcoin/Bitcoin-TxProbe/txprobe/tests/test_transactions.py): 12 unit tests covering Step 3 functions and edge cases.

---

## 3. Unit Tests of Each Function (Inputs, Outputs & Results)

All **85 unit tests** across the test suite passed (`85 passed in 0.83s`):

| Function / Method | Test Case | Input | Expected Output | Result |
|---|---|---|---|---|
| `sats_to_btc_str` & `btc_to_sats` | `test_sats_and_btc_conversions` | `2000` sats, `"0.00002000"`, `-1` sats | `"0.00002000"`, `2000` sats, `ValueError` on negative | **PASSED** |
| `compute_matrix_dimensions` | `test_compute_matrix_dimensions` | `1000`, `2`, `10000` nodes; invalid `<2` | `(32, 32)`, `(2, 1)`, `(75, 134)`, `ValueError` | **PASSED** |
| `generate_matrix_rounds` | `test_generate_matrix_rounds_pairwise_separation` | 10 nodes ($w \ge h$) and 14 nodes ($w < h$, `max_source_size=3`) | Every pair $\{u, v\}$ separated into `(source, sink)` in $\ge 1$ round | **PASSED** |
| `calculate_split_outputs` | `test_calculate_split_outputs` | `3500` sats (too small), `4500` sats, `1,000,000` sats (`max_outputs=100`) | `[]`, `[2000, 2218]`, 100 outputs (`99 x 2000` + remainder) | **PASSED** |
| `ensure_wallet_loaded` | `test_ensure_wallet_loaded` | Wallet already loaded vs missing | Calls `loadwallet` only when missing | **PASSED** |
| `derive_recipient_addresses` | `test_derive_recipient_addresses_and_fallback` | Active `wpkh` descriptor; `>1000` limit; RPC failure fallback | Distinct derived addresses; `ValueError` on `>1000`; fallback to `getnewaddress` | **PASSED** |
| `split_single_utxo` | `test_split_single_utxo` | `10,000`-sat UTXO vs `2,500`-sat UTXO | Broadcasts `len(vin)==1` tx with 4 outputs; returns `None` for small UTXO | **PASSED** |
| `prepare_utxos_for_rounds` | `test_prepare_utxos_fast_path_sorts_smallest_first` | 3 small UTXOs (`2000, 2100, 2000`) + 1 big UTXO (`500,000`) | Skips splitting; returns `[2000, 2000, 2100]` sorted ascending | **PASSED** |
| `prepare_utxos_for_rounds` | `test_prepare_utxos_auto_split_and_mempool_wait` | 1 confirmed `10,000`-sat UTXO $\to$ 4 mempool `0-conf` $\to$ 4 `1-conf` | Splits once, waits on `0-conf` without false funding prompt, returns 3 UTXOs | **PASSED** |
| `prepare_utxos_for_rounds` | `test_prepare_utxos_prompts_funding_and_times_out` | Empty wallet (`listunspent = []`), `max_wait_polls=1` | Invokes `funding_callback` with deposit address, raises `TimeoutError` | **PASSED** |
| `craft_conflicting_transactions` & `craft_marker_transactions` | `test_craft_conflicting_and_marker_transactions` | `2000`-sat UTXO, `num_parents=3`, `fee=500`; `600`-sat dust UTXO | 3 parents + 1 flood + 3 markers with unique `txid`s; `ValueError` on dust | **PASSED** |
| `craft_all_rounds` & `TxProbeCraftingResult` | `test_craft_all_rounds_and_serialization_roundtrip` | 6-node `GraphSnapshot`, 5 UTXOs of `2000` sats | Crafts 3 rounds ($3 \times 2$ grid) with distinct UTXOs; exact JSON save/load | **PASSED** |

---

## 4. Next Step to Implement

**Step 4: TxProbe Execution Loop**:
- Load the pre-crafted `TxProbeCraftingResult` (`crafted_rounds.json`) from Step 3.
- Execute each `TxProbeRoundTxs` round sequentially across the live P2P network without waiting for blocks:
  1. **INVBLOCK**: Send `sendinv_orphan([*parent_txs, flood_tx], all_active_peer_ids)`.
  2. **Flood Sinks**: Send `sendrawtransaction_orphan(flood_tx, sink_peer_ids)`.
  3. **Distribute Parents 1-to-1**: Send `sendrawtransaction_orphan(parent_txs[i], [source_peer_ids[i]])`.
  4. **Clear INVBLOCK & Distribute Markers 1-to-1**: Call `clearinv_probe()`, then send `sendrawtransaction_orphan(marker_txs[i], [source_peer_ids[i]])`.
  5. **Query Sinks & Deduce Edges**: Clear `txprobe_0.log`, send `sendinv_orphan(marker_txs, sink_peer_ids)`, parse `GETDATA` responses, and accumulate inferred edges across all rounds into the inferred `GraphSnapshot`.
