# Checkpoint Step 3: Offline Double-Spend & Block Crafter

**Timestamp:** 2026-10-15 16:42:35  
**Module Directory:** `/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/`

---

## 1. Completed Task & Deliverables
- **Offline Block & Conflicting Transaction Crafter (`block_builder.py`):**
  - **Transaction Conflict Generation (`craft_conflicting_transactions`):**
    - Takes mature spendable $tx_0$ (`ParentUtxo`).
    - Constructs $tx_1$: Sends dust amount ($10,000\text{ sats}$) to a random network node, change back to Node 2 (Forker).
    - Constructs $tx_2$: Sends dust amount ($10,000\text{ sats}$) to Node 2 itself, change back to Node 2.
    - Both transactions spend the identical input `vin = [{"txid": tx0.txid, "vout": tx0.vout}]`, establishing a strict mutually exclusive double-spend pair.
    - Signs both transactions via Node 2's wallet (`signrawtransactionwithwallet`).
  - **Offline Block Construction & PoW Solving (`craft_fork_blocks`):**
    - Builds $B_1$: Linked to current tip $H_{\text{parent}}$ at height $h+1$, contains coinbase $+ tx_1$.
    - Builds $B_2$: Linked to the **same** tip $H_{\text{parent}}$ at height $h+1$, contains coinbase $+ tx_2$ (competing head-to-head with $B_1$).
    - Builds $B_3$: Linked to $\text{hash}(B_2)$ at height $h+2$, contains coinbase (heavier branch to trigger reorg).
    - Solves RegTest Proof-of-Work locally in sub-millisecond time.
    - Automatically adds BIP141 witness commitments to coinbase outputs when witness data is present.
    - Bundles all assets into an immutable `ForkPackage` data container ready for phased release.
- **Unit Testing (`test_block_builder.py`):**
  - Verified serialization of `ConflictingTransactions`, `CraftedBlock`, and `ForkPackage`.
  - Verified parent-hash linkages, height progression, distinct hashes between $B_1$ and $B_2$, and PoW validity across all three blocks.
  - Verified RPC transaction construction and input reuse.

---

## 2. Added Files, Classes, and Functions

### Added Files
- [`snapshot-forked-subgraph/one-forker/block_builder.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/block_builder.py)
- [`snapshot-forked-subgraph/one-forker/test_block_builder.py`](file:///mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/snapshot-forked-subgraph/one-forker/test_block_builder.py)

### Added Classes & Functions
* **`ConflictingTransactions`**: Dataclass holding $tx_0, tx_1, tx_2$ raw hexes, txids, destination addresses, dust, and fee.
* **`CraftedBlock`**: Dataclass holding block label ($B_1/B_2/B_3$), height, block hash, parent hash, raw serialized hex, and timestamp.
* **`ForkPackage`**: Dataclass encapsulating $H_{\text{parent}}$, `ConflictingTransactions`, and blocks $B_1, B_2, B_3$.
* **`solve_and_serialize_block(block)`**: Computes Merkle root, BIP141 witness commitment, solves PoW (`block.solve()`), and returns `(hash_hex, block_hex)`.
* **`craft_conflicting_transactions(...)`**: Asynchronously constructs and signs $tx_1$ and $tx_2$.
* **`craft_fork_blocks(parent_hash, parent_height, parent_time, conflicts)`**: Synchronously builds and solves blocks $B_1, B_2, B_3$.
* **`build_fork_package(...)`**: Master async builder orchestrating funding check, random target picking, tx crafting, and block generation.

---

## 3. Test Results

Executed with `pytest snapshot-forked-subgraph/one-forker/ -v`:
* **All 16 unit tests passed** in $0.26\text{s}$.
  * `test_config.py`: 6 passed
  * `test_funding.py`: 7 passed
  * `test_block_builder.py`: 3 passed

---

## 4. Next Step to Implement
* **Step 4:** **Continuous P2P Ingress Event Monitor & Subgraph Snapshotter (`prober.py`)**
  - Asynchronously connects to Node 0 and Node 1 (the probes).
  - Listens for block inventory announcements (`inv`, `headers`, `cmpctblock`) from all 1,000 target nodes with microsecond timestamps.
  - Maintains `node_timings` arrival matrix: $t_{\text{recv}}(v, B_1), t_{\text{recv}}(v, B_2), t_{\text{recv}}(v, B_3)$.
  - Implements dynamic time-query `get_subgraphs_at(t)` and discrete time slicer `export_sliced_snapshots(step_ms=10)`.
  - Implements `test_prober.py`.
