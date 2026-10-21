# Checkpoint Step 2: Funding Engine & UTXO Management

**Timestamp:** 2026-10-15 16:35:45  
**Module Directory:** `/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/`

---

## 1. Completed Task & Deliverables
- **Funding & Wallet Management (`funding.py`):**
  - Implemented `ParentUtxo` data model to represent $tx_0$ with exact satoshi precision (`txid`, `vout`, `amount_sats`, `address`, `script_pub_key`).
  - Implemented wallet lifecycle management: `ensure_wallet_loaded(rpc, wallet_name)` supporting automatic inspection across `listwallets`, `listwalletdir`, `loadwallet`, and `createwallet`.
  - Implemented UTXO discovery: `find_spendable_utxo(rpc_wallet, min_amount_sats)` filtering for spendable, solvable, confirmed outputs sorted by value.
  - Implemented automated forker funding pipeline `fund_forker_node(forker_id=2, source_node_id=0, target_amount_sats=100_000)`:
    - Fully parameterized via `ExperimentConfig.funding_target_sats` (default: $100,000\text{ sats} = 0.001\text{ BTC}$, completely customizable in `config.py`).
    - Fast path: Checks Node 2 (`forker_wallet`) for existing confirmed UTXOs.
    - Transfer path: If unspent UTXO missing, generates an address on Node 2, sends funds from Node 0 (`mywallet`), and mines 1 block on Node 0 to confirm.
    - Fallback maturation: If Node 0 has insufficient balance, automatically mines 101 blocks on Node 0 to mature coinbase rewards.
- **Unit Testing (`test_funding.py`):**
  - Verified satoshi and BTC string conversion precision (`sats_to_btc_str`, `btc_to_sats`).
  - Tested wallet discovery states (already active, in directory, fresh creation).
  - Tested UTXO filtering, sorting, and spendable qualification.
  - Tested mock funding fast-path.

---

## 2. Added Files, Classes, and Functions

### Added Files
- [`snapshot-forked-subgraph/one-forker/funding.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/funding.py)
- [`snapshot-forked-subgraph/one-forker/test_funding.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/test_funding.py)

### Added Classes & Functions
* **`ParentUtxo`**: Dataclass representing a mature UTXO ($tx_0$) ready to be double-spent.
* **`sats_to_btc_str(sats)`**: Formats integer satoshis to 8-decimal string for Bitcoin Core RPC without floating-point inaccuracies.
* **`btc_to_sats(btc_val)`**: Converts BTC amounts to exact integer satoshis using `Decimal`.
* **`make_rpc_client(node_id, wallet)`**: Helper returning configured `AsyncBitcoinRpc` client.
* **`ensure_wallet_loaded(rpc_base, wallet_name)`**: Automatically loads or creates the specified wallet.
* **`find_spendable_utxo(rpc_wallet, min_amount_sats)`**: Scans for mature spendable UTXOs.
* **`fund_forker_node(forker_id, source_node_id, target_amount_sats)`**: Ensures Node 2 possesses spendable parent UTXO.

---

## 3. Test Results

Executed with `pytest snapshot-forked-subgraph/one-forker/ -v`:
* **All 13 unit tests passed** in $0.24\text{s}$.
  * `test_config.py`: 6 passed
  * `test_funding.py`: 7 passed

---

## 4. Next Step to Implement
* **Step 3:** **Offline Double-Spend & Block Crafter (`block_builder.py`)**
  - Craft conflicting transactions $tx_1$ and $tx_2$ spending the same $tx_0$:
    - $tx_1$: Sends minimal dust (e.g. $10,000\text{ sats}$) to random node $X$, change to Node 2.
    - $tx_2$: Sends dust back to Node 2, change to Node 2.
  - Construct Block $B_1$ (parent $= H_{\text{parent}}$, contains coinbase $+ tx_1$).
  - Construct Block $B_2$ (parent $= H_{\text{parent}}$, contains coinbase $+ tx_2$).
  - Construct Block $B_3$ (parent $= \text{hash}(B_2)$, contains coinbase).
  - Solve PoW in Python (sub-millisecond in RegTest) and return raw serialized block hex strings.
  - Implement `test_block_builder.py`.
