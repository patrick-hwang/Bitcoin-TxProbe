"""Step 3: Matrix Partitioning, UTXO Splitting & Raw Transaction Crafting.

Given the surviving GraphSnapshot from Step 2:
1. Partitions the reachable nodes into a 2D grid (w x h) and generates all
   matrix rounds (source_nodes, sink_nodes).
2. Inspects Probe 0's wallet for spendable UTXOs (>= 2000 sats):
   - If the number of available UTXOs (< R rounds), automatically splits any
     large UTXO (len(vin) == 1 -> K outputs of 2000 sats + remainder).
   - If total UTXOs (confirmed + unconfirmed in mempool) are still < R, prompts
     the user to deposit more tBTC and polls until >= R confirmed UTXOs are ready.
3. Pre-crafts and signs all parent, flood, and marker transactions for all R
   rounds upfront using batched JSON-RPC calls, so Step 4 can execute rounds
   back-to-back without waiting on the blockchain.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from decimal import Decimal, ROUND_HALF_UP
import logging
import math
from typing import Any

from .config import TxCraftingConfig
from .models.graph import GraphSnapshot
from .models.node import NodeIdentity
from .models.transaction import (
    MatrixRound,
    TxCraftingStats,
    TxMessage,
    TxProbeCraftingResult,
    TxProbeRoundTxs,
    UtxoInfo,
)
from .rpc.client import AsyncBitcoinRpc

log = logging.getLogger(__name__)

SATS_PER_BTC = 100_000_000
P2WPKH_DUST_SATS = 294
MAX_KEYPOOL_DERIVATION = 1000


def sats_to_btc_str(sats: int) -> str:
    """Format an integer satoshi amount into an exact 8-decimal BTC string.

    Bitcoin Core's ``AmountFromValue`` accepts strings formatted to 8 decimals,
    avoiding floating-point inaccuracy and aiohttp Decimal serialization errors.
    """
    if sats < 0:
        raise ValueError(f"Satoshi amount cannot be negative: {sats}")
    whole = sats // SATS_PER_BTC
    frac = sats % SATS_PER_BTC
    return f"{whole}.{frac:08d}"


def btc_to_sats(btc_val: int | float | str | Decimal) -> int:
    """Convert a BTC value (from JSON-RPC) to exact integer satoshis."""
    dec = Decimal(str(btc_val))
    sats = (dec * Decimal(SATS_PER_BTC)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(sats)


def compute_matrix_dimensions(
    num_nodes: int, max_source_size: int = 75
) -> tuple[int, int]:
    """Compute grid width (w) and height (h) for Matrix Splitting.

    Uses ``w = min(max_source_size, ceil(sqrt(num_nodes)))`` and
    ``h = ceil(num_nodes / w)``, ensuring ``w >= h`` for all networks up to
    ``max_source_size ** 2`` nodes (5,625 nodes when ``max_source_size = 75``).

    Args:
        num_nodes: Total number of qualified reachable nodes (must be >= 2).
        max_source_size: Maximum allowed source set size per round.

    Returns:
        Tuple ``(w, h)`` representing matrix width and height.
    """
    if num_nodes < 2:
        raise ValueError(
            f"At least 2 nodes are required for TxProbe matrix partitioning, got {num_nodes}"
        )
    if max_source_size < 1:
        raise ValueError(
            f"max_source_size must be >= 1, got {max_source_size}"
        )

    ceil_sqrt = math.isqrt(num_nodes - 1) + 1
    w = min(max_source_size, ceil_sqrt)
    h = (num_nodes + w - 1) // w
    return w, h


def generate_matrix_rounds(
    nodes: Sequence[NodeIdentity],
    max_source_size: int = 75,
) -> list[MatrixRound]:
    """Partition nodes into (source_nodes, sink_nodes) rounds via Matrix Splitting.

    Arranges ``rn`` nodes into a grid of ``h`` rows by ``w`` columns:
    - If ``w >= h``:
      - Column rounds ``c in [0, w - 2]``: source = col ``c``, sink = remaining.
      - Row rounds ``r in [0, h - 2]``: source = row ``r``, sink = remaining.
      - Total rounds: ``w + h - 2``.
    - If ``w < h`` (when ``rn > max_source_size ** 2``):
      - Row rounds ``r in [0, h - 2]``: source = row ``r``, sink = remaining.
      - Column rounds ``c in [0, w - 2]``: each column is partitioned into blocks
        of size at most ``max_source_size``.

    Args:
        nodes: Ordered sequence of qualified NodeIdentity instances.
        max_source_size: Maximum number of source nodes in any single round.

    Returns:
        List of MatrixRound instances with 0-based sequential ``round_index``.
    """
    unique_nodes = list(dict.fromkeys(nodes))
    rn = len(unique_nodes)
    w, h = compute_matrix_dimensions(rn, max_source_size=max_source_size)

    # Build h x w grid row by row
    grid: list[list[NodeIdentity]] = []
    for r in range(h):
        start = r * w
        end = min(start + w, rn)
        grid.append(unique_nodes[start:end])

    rounds: list[MatrixRound] = []

    def _add_round(source_list: list[NodeIdentity]) -> None:
        if not source_list:
            return
        source_set = set(source_list)
        sink_list = [n for n in unique_nodes if n not in source_set]
        if not sink_list:
            return
        rounds.append(
            MatrixRound(
                round_index=len(rounds),
                source_nodes=tuple(source_list),
                sink_nodes=tuple(sink_list),
            )
        )

    if w >= h:
        # 1. Column rounds: c in [0, w - 2]
        for c in range(max(0, w - 1)):
            col_nodes = [grid[r][c] for r in range(h) if c < len(grid[r])]
            _add_round(col_nodes)

        # 2. Row rounds: r in [0, h - 2]
        for r in range(max(0, h - 1)):
            row_nodes = list(grid[r])
            _add_round(row_nodes)
    else:
        # 1. Row rounds: r in [0, h - 2]
        for r in range(max(0, h - 1)):
            row_nodes = list(grid[r])
            _add_round(row_nodes)

        # 2. Column rounds: c in [0, w - 2], sliced into chunks <= max_source_size
        for c in range(max(0, w - 1)):
            col_nodes = [grid[r][c] for r in range(h) if c < len(grid[r])]
            for offset in range(0, len(col_nodes), max_source_size):
                chunk = col_nodes[offset : offset + max_source_size]
                _add_round(chunk)

    return rounds


async def ensure_wallet_loaded(
    rpc: AsyncBitcoinRpc, wallet_name: str
) -> None:
    """Ensure the specified wallet is loaded on the target bitcoind node."""
    if not wallet_name:
        return
    loaded_wallets = await rpc.listwallets()
    if wallet_name not in loaded_wallets:
        log.info("Loading wallet '%s'...", wallet_name)
        await rpc.loadwallet(wallet_name)


async def derive_recipient_addresses(
    rpc: AsyncBitcoinRpc,
    count: int,
    start_index: int = 0,
) -> list[str]:
    """Derive ``count`` distinct P2WPKH addresses from the active wallet descriptor.

    Stays strictly within ``[0, MAX_KEYPOOL_DERIVATION - 1]`` so the wallet's
    descriptor lookahead cache always recognizes and can sign for the derived
    scriptPubKeys. Falls back to ``getnewaddress`` if descriptor derivation is
    unavailable.
    """
    if count < 1:
        raise ValueError(f"Address count must be >= 1, got {count}")
    if start_index < 0 or start_index + count > MAX_KEYPOOL_DERIVATION:
        raise ValueError(
            f"Requested address range [{start_index}, {start_index + count - 1}] "
            f"exceeds wallet keypool lookahead limit ({MAX_KEYPOOL_DERIVATION})"
        )

    try:
        descs_resp = await rpc.listdescriptors()
        descriptors = descs_resp.get("descriptors", [])
        target_desc: str | None = None

        # Prefer active internal (change) wpkh descriptor if available, else any active wpkh
        for entry in descriptors:
            desc = entry.get("desc", "")
            if entry.get("active") and desc.startswith("wpkh(") and entry.get("internal"):
                target_desc = desc
                break
        if target_desc is None:
            for entry in descriptors:
                desc = entry.get("desc", "")
                if entry.get("active") and desc.startswith("wpkh("):
                    target_desc = desc
                    break

        if target_desc is not None:
            addrs = await rpc.deriveaddresses(
                target_desc, [start_index, start_index + count - 1]
            )
            if len(addrs) == count:
                return list(addrs)
    except Exception as e:
        log.warning(
            "Descriptor address derivation failed (%s), falling back to getnewaddress",
            e,
        )

    # Fallback: batch getnewaddress calls
    calls = [("getnewaddress", "", "bech32") for _ in range(count)]
    results = await rpc.call_batch(calls)
    return [str(addr) for addr in results]


def estimate_split_tx_vsize(num_inputs: int, num_outputs: int) -> int:
    """Estimate virtual size (vBytes) of a P2WPKH transaction."""
    if num_inputs < 1 or num_outputs < 1:
        raise ValueError("num_inputs and num_outputs must be >= 1")
    return 11 + 68 * num_inputs + 31 * num_outputs


def calculate_split_outputs(
    input_sats: int,
    target_sats: int = 2000,
    fee_rate_sat_vb: int = 2,
    max_outputs: int = 500,
) -> list[int]:
    """Calculate output satoshi amounts for splitting 1 large UTXO (len(vin) == 1).

    Creates as many ``target_sats`` outputs as possible (up to ``max_outputs``),
    placing any leftover remainder into the final output so zero funds are
    wasted on excess miner fees.

    Args:
        input_sats: Amount of the single input UTXO in satoshis.
        target_sats: Minimum amount per split UTXO (default 2000 sats).
        fee_rate_sat_vb: Fee rate in sat/vB for the split transaction.
        max_outputs: Maximum number of outputs in a single split transaction.

    Returns:
        List of output amounts in satoshis (length >= 2), or ``[]`` if the
        input UTXO is too small to split into at least 2 outputs of ``target_sats``.
    """
    if target_sats < P2WPKH_DUST_SATS:
        raise ValueError(
            f"target_sats ({target_sats}) cannot be below P2WPKH dust ({P2WPKH_DUST_SATS})"
        )
    if fee_rate_sat_vb < 1:
        raise ValueError(f"fee_rate_sat_vb must be >= 1, got {fee_rate_sat_vb}")
    if max_outputs < 2 or max_outputs > MAX_KEYPOOL_DERIVATION:
        raise ValueError(
            f"max_outputs must be in [2, {MAX_KEYPOOL_DERIVATION}], got {max_outputs}"
        )

    base_vsize = 11 + 68  # 79 vBytes for 1 P2WPKH input + tx header
    base_fee = base_vsize * fee_rate_sat_vb
    per_output_cost = target_sats + 31 * fee_rate_sat_vb

    available = input_sats - base_fee
    if available < 2 * per_output_cost:
        return []

    num_outputs = min(max_outputs, available // per_output_cost)
    if num_outputs < 2:
        return []

    total_fee = estimate_split_tx_vsize(1, num_outputs) * fee_rate_sat_vb
    remainder = input_sats - total_fee - (num_outputs - 1) * target_sats

    outputs = [target_sats] * (num_outputs - 1) + [remainder]
    return outputs


async def split_single_utxo(
    rpc: AsyncBitcoinRpc,
    utxo: UtxoInfo,
    target_sats: int = 2000,
    fee_rate_sat_vb: int = 2,
    max_outputs: int = 500,
    addresses: list[str] | None = None,
) -> str | None:
    """Split a single large UTXO (len(vin) == 1) into multiple smaller UTXOs.

    Constructs, signs, and broadcasts the split transaction to the network.

    Args:
        rpc: Wallet-scoped AsyncBitcoinRpc client.
        utxo: The single UTXO to split.
        target_sats: Target satoshis per output (default 2000).
        fee_rate_sat_vb: Split transaction fee rate in sat/vB.
        max_outputs: Maximum outputs per split transaction.
        addresses: Optional pre-derived distinct recipient addresses.

    Returns:
        Broadcast transaction txid if split succeeded, or ``None`` if the UTXO
        is too small to split into >= 2 outputs.
    """
    output_amounts = calculate_split_outputs(
        input_sats=utxo.amount_sats,
        target_sats=target_sats,
        fee_rate_sat_vb=fee_rate_sat_vb,
        max_outputs=max_outputs,
    )
    if len(output_amounts) < 2:
        return None

    k = len(output_amounts)
    if addresses is None or len(addresses) < k:
        recipient_addrs = await derive_recipient_addresses(rpc, count=k, start_index=0)
    else:
        recipient_addrs = addresses[:k]

    if len(set(recipient_addrs)) != k:
        raise ValueError(
            "createrawtransaction requires all output addresses in a split tx to be distinct"
        )

    inputs = [{"txid": utxo.txid, "vout": utxo.vout}]
    outputs = [
        {addr: sats_to_btc_str(amt)}
        for addr, amt in zip(recipient_addrs, output_amounts)
    ]

    raw_hex = await rpc.createrawtransaction(inputs, outputs)
    signed_res = await rpc.signrawtransactionwithwallet(raw_hex)
    if not signed_res.get("complete"):
        errors = signed_res.get("errors", [])
        raise RuntimeError(
            f"Failed to sign UTXO split transaction for {utxo.txid}:{utxo.vout}: {errors}"
        )

    txid = await rpc.sendrawtransaction(signed_res["hex"])
    log.info(
        "Broadcast UTXO split tx %s: spent 1 UTXO (%d sats) -> %d outputs (>= %d sats each)",
        txid,
        utxo.amount_sats,
        k,
        target_sats,
    )
    return str(txid)


def _parse_utxos(
    raw_utxos: list[dict[str, Any]],
    excluded_outpoints: set[tuple[str, int]],
) -> list[UtxoInfo]:
    """Convert raw listunspent dicts into filtered UtxoInfo objects."""
    parsed: list[UtxoInfo] = []
    for u in raw_utxos:
        if not u.get("spendable", False):
            continue
        txid = str(u["txid"])
        vout = int(u["vout"])
        if (txid, vout) in excluded_outpoints:
            continue
        amount_sats = btc_to_sats(u["amount"])
        confs = int(u.get("confirmations", 0))
        spk = str(u.get("scriptPubKey", ""))
        parsed.append(
            UtxoInfo(
                txid=txid,
                vout=vout,
                amount_sats=amount_sats,
                confirmations=confs,
                script_pub_key=spk,
            )
        )
    return parsed


async def prepare_utxos_for_rounds(
    rpc: AsyncBitcoinRpc,
    num_rounds: int,
    config: TxCraftingConfig | None = None,
    excluded_outpoints: set[tuple[str, int]] | None = None,
    max_wait_polls: int | None = None,
    funding_callback: Callable[[str, int, int], None] | None = None,
) -> tuple[list[UtxoInfo], list[str]]:
    """Ensure at least ``num_rounds`` confirmed UTXOs (>= target_sats) are ready.

    Workflow:
    1. Queries ``listunspent(minconf=0)`` to inspect both confirmed and
       mempool-pending UTXOs.
    2. If ``len(confirmed_ready) >= num_rounds``, sorts them by ``amount_sats``
       ascending (preferring exact 2000-sat UTXOs over large remainder UTXOs)
       and returns the first ``num_rounds`` UTXOs immediately.
    3. If ``len(confirmed_ready) + len(unconfirmed_ready) < num_rounds``:
       - Splits confirmed large UTXOs one by one (``len(vin) == 1``) until
         projected UTXOs >= ``num_rounds``.
       - If still short after splitting all eligible large UTXOs, prints a
         deposit address and required tBTC amount, calling ``funding_callback``.
    4. Polls until ``len(confirmed_ready) >= num_rounds`` (plus a brief block
       propagation delay if a new block was just mined during polling).

    Returns:
        Tuple of ``(selected_utxos, broadcast_split_txids)``.
    """
    if num_rounds < 1:
        raise ValueError(f"num_rounds must be >= 1, got {num_rounds}")

    cfg = config or TxCraftingConfig()
    min_needed_sats = max(
        cfg.utxo_target_sats,
        cfg.parent_fee_sats + cfg.marker_fee_sats + P2WPKH_DUST_SATS,
    )
    excluded = set(excluded_outpoints) if excluded_outpoints else set()
    already_split_outpoints: set[tuple[str, int]] = set()
    split_txids: list[str] = []
    waited_for_block = False
    polls = 0
    cached_deposit_addr: str | None = None

    while True:
        raw_utxos = await rpc.listunspent(minconf=0)
        all_utxos = _parse_utxos(raw_utxos, excluded)

        confirmed_ready = [
            u
            for u in all_utxos
            if u.confirmations >= 1
            and u.amount_sats >= min_needed_sats
            and u.outpoint not in already_split_outpoints
        ]
        unconfirmed_ready = [
            u
            for u in all_utxos
            if u.confirmations == 0 and u.amount_sats >= min_needed_sats
        ]

        if len(confirmed_ready) >= num_rounds:
            if waited_for_block and cfg.block_propagation_wait_sec > 0:
                log.info(
                    "New block confirmed UTXOs! Waiting %.1fs for block propagation across network...",
                    cfg.block_propagation_wait_sec,
                )
                await asyncio.sleep(cfg.block_propagation_wait_sec)

            # Sort ascending by amount so 2000-sat UTXOs are used before any large remainder UTXO
            confirmed_ready.sort(key=lambda u: (u.amount_sats, u.txid, u.vout))
            return confirmed_ready[:num_rounds], split_txids

        total_projected = len(confirmed_ready) + len(unconfirmed_ready)

        # Only split large UTXOs if total projected (confirmed + mempool) is still < num_rounds
        if total_projected < num_rounds:
            splittable = [
                u
                for u in confirmed_ready
                if len(
                    calculate_split_outputs(
                        u.amount_sats,
                        target_sats=min_needed_sats,
                        fee_rate_sat_vb=cfg.split_fee_rate_sat_vb,
                        max_outputs=cfg.max_outputs_per_split_tx,
                    )
                )
                >= 2
            ]
            # Split largest UTXO first to maximize output count in minimum transactions
            splittable.sort(key=lambda u: u.amount_sats, reverse=True)

            for big_utxo in splittable:
                if total_projected >= num_rounds:
                    break
                expected_outs = calculate_split_outputs(
                    big_utxo.amount_sats,
                    target_sats=min_needed_sats,
                    fee_rate_sat_vb=cfg.split_fee_rate_sat_vb,
                    max_outputs=cfg.max_outputs_per_split_tx,
                )
                txid = await split_single_utxo(
                    rpc=rpc,
                    utxo=big_utxo,
                    target_sats=min_needed_sats,
                    fee_rate_sat_vb=cfg.split_fee_rate_sat_vb,
                    max_outputs=cfg.max_outputs_per_split_tx,
                )
                if txid is not None:
                    already_split_outpoints.add(big_utxo.outpoint)
                    split_txids.append(txid)
                    # Subtract the 1 parent UTXO we spent and add the K new outputs
                    total_projected = total_projected - 1 + len(expected_outs)

        if total_projected < num_rounds:
            deficit_count = num_rounds - total_projected
            deficit_sats = deficit_count * (
                min_needed_sats + 31 * cfg.split_fee_rate_sat_vb
            ) + 200
            if cached_deposit_addr is None:
                cached_deposit_addr = await rpc.getnewaddress("txprobe_funding", "bech32")
            log.warning(
                "Insufficient UTXOs: have %d/%d ready (%d confirmed, %d in mempool). "
                "Please fund at least %s tBTC (%d sats) to Probe 0 address: %s",
                total_projected,
                num_rounds,
                len(confirmed_ready),
                len(unconfirmed_ready),
                sats_to_btc_str(deficit_sats),
                deficit_sats,
                cached_deposit_addr,
            )
            if funding_callback is not None:
                funding_callback(cached_deposit_addr, total_projected, num_rounds)
        else:
            log.info(
                "Waiting for block confirmation: %d/%d UTXOs confirmed (%d pending in mempool)...",
                len(confirmed_ready),
                num_rounds,
                total_projected - len(confirmed_ready),
            )

        polls += 1
        if max_wait_polls is not None and polls > max_wait_polls:
            raise TimeoutError(
                f"Timed out waiting for {num_rounds} confirmed UTXOs "
                f"(currently {len(confirmed_ready)} confirmed, {len(unconfirmed_ready)} unconfirmed)"
            )

        waited_for_block = True
        await asyncio.sleep(cfg.poll_interval_sec)


async def craft_conflicting_transactions(
    rpc: AsyncBitcoinRpc,
    utxo: UtxoInfo,
    num_parents: int,
    fee_sats: int = 500,
    addresses: Sequence[str] | None = None,
) -> tuple[list[TxMessage], TxMessage, list[dict[str, Any]]]:
    """Craft ``num_parents`` parent transactions and 1 flood transaction spending ``utxo``.

    Uses batched JSON-RPC calls (``createrawtransaction``,
    ``signrawtransactionwithwallet``, ``decoderawtransaction``) to construct all
    ``num_parents + 1`` conflicting transactions in 3 HTTP roundtrips.

    Returns:
        Tuple ``(parent_txs, flood_tx, parent_decoded_dicts)``.
    """
    if num_parents < 1:
        raise ValueError(f"num_parents must be >= 1, got {num_parents}")

    output_sats = utxo.amount_sats - fee_sats
    if output_sats < P2WPKH_DUST_SATS:
        raise ValueError(
            f"UTXO {utxo.txid}:{utxo.vout} amount ({utxo.amount_sats} sats) minus "
            f"parent fee ({fee_sats} sats) = {output_sats} sats is below dust ({P2WPKH_DUST_SATS} sats)"
        )

    total_txs = num_parents + 1
    if addresses is None or len(addresses) < total_txs:
        recipient_addrs = await derive_recipient_addresses(rpc, count=total_txs, start_index=0)
    else:
        recipient_addrs = list(addresses[:total_txs])

    if len(set(recipient_addrs)) < total_txs:
        raise ValueError(
            f"All {total_txs} conflicting transactions must have distinct recipient addresses"
        )

    out_btc_str = sats_to_btc_str(output_sats)
    tx_inputs = [{"txid": utxo.txid, "vout": utxo.vout}]

    # 1. Batch createrawtransaction
    create_calls = [
        ("createrawtransaction", tx_inputs, [{addr: out_btc_str}])
        for addr in recipient_addrs
    ]
    unsigned_hexes: list[str] = await rpc.call_batch(create_calls)

    # 2. Batch signrawtransactionwithwallet
    sign_calls = [
        ("signrawtransactionwithwallet", raw_hex) for raw_hex in unsigned_hexes
    ]
    signed_results: list[dict[str, Any]] = await rpc.call_batch(sign_calls)

    signed_hexes: list[str] = []
    for idx, res in enumerate(signed_results):
        if not res or not res.get("complete"):
            raise RuntimeError(
                f"Failed to sign conflicting tx #{idx} spending {utxo.txid}:{utxo.vout}: {res}"
            )
        signed_hexes.append(str(res["hex"]))

    # 3. Batch decoderawtransaction
    decode_calls = [("decoderawtransaction", s_hex) for s_hex in signed_hexes]
    decoded_list: list[dict[str, Any]] = await rpc.call_batch(decode_calls)

    tx_messages: list[TxMessage] = []
    for s_hex, dec in zip(signed_hexes, decoded_list):
        txid = str(dec["txid"])
        wtxid = str(dec.get("hash", txid))
        tx_messages.append(TxMessage(hexstr=s_hex, txid=txid, wtxid=wtxid))

    parent_txs = tx_messages[:num_parents]
    flood_tx = tx_messages[num_parents]
    parent_decoded = decoded_list[:num_parents]

    return parent_txs, flood_tx, parent_decoded


async def craft_marker_transactions(
    rpc: AsyncBitcoinRpc,
    parent_txs: Sequence[TxMessage],
    parent_decoded: Sequence[dict[str, Any]],
    parent_output_sats: int,
    fee_sats: int = 500,
    marker_address: str | None = None,
) -> list[TxMessage]:
    """Craft ``n`` marker transactions, each spending ``parent_txs[i]`` vout 0.

    Since ``parent_txs[i]`` is unbroadcast (kept only in memory), passes explicit
    ``prevtxs`` metadata into ``signrawtransactionwithwallet``.
    """
    if len(parent_txs) != len(parent_decoded):
        raise ValueError("parent_txs and parent_decoded must have identical length")
    if not parent_txs:
        raise ValueError("parent_txs cannot be empty")

    marker_output_sats = parent_output_sats - fee_sats
    if marker_output_sats < P2WPKH_DUST_SATS:
        raise ValueError(
            f"Parent output ({parent_output_sats} sats) minus marker fee ({fee_sats} sats) "
            f"= {marker_output_sats} sats is below dust ({P2WPKH_DUST_SATS} sats)"
        )

    if not marker_address:
        derived = await derive_recipient_addresses(rpc, count=1, start_index=0)
        marker_address = derived[0]

    parent_btc_str = sats_to_btc_str(parent_output_sats)
    marker_btc_str = sats_to_btc_str(marker_output_sats)

    # 1. Batch createrawtransaction for all markers
    create_calls = [
        (
            "createrawtransaction",
            [{"txid": ptx.txid, "vout": 0}],
            [{marker_address: marker_btc_str}],
        )
        for ptx in parent_txs
    ]
    unsigned_hexes: list[str] = await rpc.call_batch(create_calls)

    # 2. Batch signrawtransactionwithwallet with explicit prevtxs
    sign_calls = []
    for ptx, p_dec, raw_hex in zip(parent_txs, parent_decoded, unsigned_hexes):
        vout_0 = p_dec["vout"][0]
        spk_hex = str(vout_0["scriptPubKey"]["hex"])
        prevtxs = [
            {
                "txid": ptx.txid,
                "vout": 0,
                "scriptPubKey": spk_hex,
                "amount": parent_btc_str,
            }
        ]
        sign_calls.append(("signrawtransactionwithwallet", raw_hex, prevtxs))

    signed_results: list[dict[str, Any]] = await rpc.call_batch(sign_calls)

    signed_hexes: list[str] = []
    for idx, res in enumerate(signed_results):
        if not res or not res.get("complete"):
            raise RuntimeError(
                f"Failed to sign marker tx #{idx} spending parent {parent_txs[idx].txid}: {res}"
            )
        signed_hexes.append(str(res["hex"]))

    # 3. Batch decoderawtransaction
    decode_calls = [("decoderawtransaction", s_hex) for s_hex in signed_hexes]
    decoded_list: list[dict[str, Any]] = await rpc.call_batch(decode_calls)

    marker_txs: list[TxMessage] = []
    for s_hex, dec in zip(signed_hexes, decoded_list):
        txid = str(dec["txid"])
        wtxid = str(dec.get("hash", txid))
        marker_txs.append(TxMessage(hexstr=s_hex, txid=txid, wtxid=wtxid))

    return marker_txs


async def craft_round_transactions(
    rpc: AsyncBitcoinRpc,
    matrix_round: MatrixRound,
    utxo: UtxoInfo,
    parent_fee_sats: int = 500,
    marker_fee_sats: int = 500,
    addresses: Sequence[str] | None = None,
) -> TxProbeRoundTxs:
    """Craft the full set of conflicting parent/flood and marker transactions for 1 round."""
    num_sources = matrix_round.num_sources
    if num_sources < 1:
        raise ValueError(f"Round {matrix_round.round_index} has no source nodes")

    parent_txs, flood_tx, parent_decoded = await craft_conflicting_transactions(
        rpc=rpc,
        utxo=utxo,
        num_parents=num_sources,
        fee_sats=parent_fee_sats,
        addresses=addresses,
    )

    parent_output_sats = utxo.amount_sats - parent_fee_sats
    marker_addr = addresses[0] if addresses else None

    marker_txs = await craft_marker_transactions(
        rpc=rpc,
        parent_txs=parent_txs,
        parent_decoded=parent_decoded,
        parent_output_sats=parent_output_sats,
        fee_sats=marker_fee_sats,
        marker_address=marker_addr,
    )

    return TxProbeRoundTxs(
        round_index=matrix_round.round_index,
        source_nodes=matrix_round.source_nodes,
        sink_nodes=matrix_round.sink_nodes,
        utxo=utxo,
        parent_txs=tuple(parent_txs),
        flood_tx=flood_tx,
        marker_txs=tuple(marker_txs),
    )


async def craft_all_rounds(
    snapshot: GraphSnapshot,
    rpc: AsyncBitcoinRpc,
    config: TxCraftingConfig | None = None,
    wallet_name: str = "",
    excluded_outpoints: set[tuple[str, int]] | None = None,
    max_wait_polls: int | None = None,
    progress_callback: Callable[[str, float], None] | None = None,
    funding_callback: Callable[[str, int, int], None] | None = None,
) -> TxProbeCraftingResult:
    """Execute the complete Step 3 pipeline: Matrix Partitioning + UTXO Prep + Pre-Crafting.

    Args:
        snapshot: Qualified GraphSnapshot from Step 2.
        rpc: Wallet-scoped AsyncBitcoinRpc client for Probe 0.
        config: Optional TxCraftingConfig parameters.
        wallet_name: Optional wallet name to ensure loaded on Probe 0.
        excluded_outpoints: Optional set of (txid, vout) outpoints to exclude.
        max_wait_polls: Optional cap on UTXO polling iterations.
        progress_callback: Optional callback ``(stage_description, progress_ratio)``.
        funding_callback: Optional callback ``(deposit_address, ready_count, needed_count)``.

    Returns:
        TxProbeCraftingResult containing all pre-crafted rounds and statistics.
    """
    cfg = config or TxCraftingConfig()

    if progress_callback:
        progress_callback("Ensuring Probe 0 wallet is loaded", 0.02)
    if wallet_name:
        await ensure_wallet_loaded(rpc, wallet_name)

    # 1. Compute Matrix Partitioning rounds
    if progress_callback:
        progress_callback("Generating matrix round partitions", 0.05)
    w, h = compute_matrix_dimensions(
        snapshot.num_nodes, max_source_size=cfg.max_source_size
    )
    matrix_rounds = generate_matrix_rounds(
        snapshot.nodes, max_source_size=cfg.max_source_size
    )
    num_rounds = len(matrix_rounds)
    log.info(
        "Matrix partitioning for %d nodes: grid %dx%d -> %d rounds",
        snapshot.num_nodes,
        w,
        h,
        num_rounds,
    )

    # 2. Prepare >= num_rounds confirmed UTXOs (splitting if needed)
    if progress_callback:
        progress_callback(f"Preparing {num_rounds} UTXOs", 0.10)
    utxos, split_txids = await prepare_utxos_for_rounds(
        rpc=rpc,
        num_rounds=num_rounds,
        config=cfg,
        excluded_outpoints=excluded_outpoints,
        max_wait_polls=max_wait_polls,
        funding_callback=funding_callback,
    )

    # 3. Derive reusable address pool of size (max_sources_in_any_round + 1)
    max_sources = max(r.num_sources for r in matrix_rounds)
    if progress_callback:
        progress_callback(f"Deriving {max_sources + 1} recipient addresses", 0.15)
    address_pool = await derive_recipient_addresses(
        rpc, count=max_sources + 1, start_index=0
    )

    # 4. Craft transactions for each round
    crafted_rounds: list[TxProbeRoundTxs] = []
    for idx, (m_round, utxo) in enumerate(zip(matrix_rounds, utxos)):
        if progress_callback:
            ratio = 0.15 + 0.85 * ((idx + 1) / num_rounds)
            progress_callback(
                f"Crafting round {idx + 1}/{num_rounds} ({m_round.num_sources} sources)",
                ratio,
            )
        round_txs = await craft_round_transactions(
            rpc=rpc,
            matrix_round=m_round,
            utxo=utxo,
            parent_fee_sats=cfg.parent_fee_sats,
            marker_fee_sats=cfg.marker_fee_sats,
            addresses=address_pool,
        )
        crafted_rounds.append(round_txs)

    total_parents = sum(len(r.parent_txs) for r in crafted_rounds)
    total_markers = sum(len(r.marker_txs) for r in crafted_rounds)

    stats = TxCraftingStats(
        total_nodes=snapshot.num_nodes,
        matrix_width=w,
        matrix_height=h,
        total_rounds=num_rounds,
        total_parent_txs=total_parents,
        total_flood_txs=num_rounds,
        total_marker_txs=total_markers,
        split_txids=tuple(split_txids),
    )

    log.info(
        "Completed Step 3 crafting: %d rounds, %d parent txs, %d flood txs, %d marker txs",
        num_rounds,
        total_parents,
        num_rounds,
        total_markers,
    )

    return TxProbeCraftingResult(
        snapshot=snapshot,
        rounds=tuple(crafted_rounds),
        stats=stats,
    )
