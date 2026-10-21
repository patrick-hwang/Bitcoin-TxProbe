"""Funding Engine and UTXO Management for Fork Propagation Experiment.

Ensures Node 2 (the Forker) has a mature, spendable parent UTXO (tx0)
ready to be spent into conflicting double-spending transactions (tx1 and tx2).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
import logging
from pathlib import Path
import sys
from typing import Any

# Add project root and txprobe to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
if str(TXPROBE_DIR) not in sys.path:
    sys.path.insert(0, str(TXPROBE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from txprobe.rpc.client import AsyncBitcoinRpc, RpcError

try:
    from .config import DEFAULT_FUNDING_TARGET_SATS, FORKER_NODE_ID, PROBE_NODE_IDS, get_node_config, get_ports
except ImportError:
    from config import DEFAULT_FUNDING_TARGET_SATS, FORKER_NODE_ID, PROBE_NODE_IDS, get_node_config, get_ports

log = logging.getLogger("snapshot_fork.funding")

SATS_PER_BTC = 100_000_000
DEFAULT_TARGET_SATS = DEFAULT_FUNDING_TARGET_SATS  # 100,000 sats (0.001 BTC)
FORKER_WALLET_NAME = "forker_wallet"
SOURCE_WALLET_NAME = "mywallet"


def sats_to_btc_str(sats: int) -> str:
    """Format an integer satoshi amount into an exact 8-decimal BTC string."""
    if sats < 0:
        raise ValueError(f"Satoshi amount cannot be negative: {sats}")
    whole = sats // SATS_PER_BTC
    frac = sats % SATS_PER_BTC
    return f"{whole}.{frac:08d}"


def btc_to_sats(btc_val: int | float | str | Decimal) -> int:
    """Convert a BTC value (from JSON-RPC) to exact integer satoshis."""
    dec = Decimal(str(btc_val))
    return int((dec * SATS_PER_BTC).quantize(Decimal("1")))


@dataclass(frozen=True)
class ParentUtxo:
    """Spendable parent UTXO (tx0) to be double-spent."""
    txid: str
    vout: int
    amount_sats: int
    address: str
    script_pub_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "txid": self.txid,
            "vout": self.vout,
            "amount_sats": self.amount_sats,
            "address": self.address,
            "script_pub_key": self.script_pub_key,
        }


def make_rpc_client(node_id: int, wallet: str = "", timeout_sec: float = 30.0) -> AsyncBitcoinRpc:
    """Instantiate AsyncBitcoinRpc for a given node ID and optional wallet."""
    cfg = get_node_config(node_id)
    return AsyncBitcoinRpc(
        host="127.0.0.1",
        port=cfg.rpc_port,
        user=cfg.rpc_user,
        password=cfg.rpc_pass,
        wallet=wallet,
        timeout_sec=timeout_sec,
    )


async def ensure_wallet_loaded(rpc_base: AsyncBitcoinRpc, wallet_name: str) -> None:
    """Ensure that the given wallet is created and loaded on the target node."""
    loaded_wallets: list[str] = await rpc_base.call("listwallets")
    if wallet_name in loaded_wallets:
        log.debug("Wallet '%s' is already loaded.", wallet_name)
        return

    # Check available wallet directories
    try:
        wallet_dir_info: dict[str, Any] = await rpc_base.call("listwalletdir")
        existing_wallets = [w["name"] for w in wallet_dir_info.get("wallets", [])]
    except Exception:
        existing_wallets = []

    if wallet_name in existing_wallets:
        log.info("Loading existing wallet '%s'...", wallet_name)
        try:
            await rpc_base.call("loadwallet", wallet_name)
            return
        except RpcError as e:
            if "already loaded" in e.message:
                return
            raise

    # Create new wallet if not found
    log.info("Creating new wallet '%s'...", wallet_name)
    try:
        await rpc_base.call("createwallet", wallet_name)
    except RpcError as e:
        if "already exists" in e.message or "already loaded" in e.message:
            pass
        else:
            raise


async def find_spendable_utxo(
    rpc_wallet: AsyncBitcoinRpc,
    min_amount_sats: int = 50_000_000,
) -> ParentUtxo | None:
    """Scan confirmed UTXOs (minconf=1) on the wallet for one meeting min_amount_sats."""
    unspent: list[dict[str, Any]] = await rpc_wallet.call("listunspent", 1, 9999999)
    # Filter by spendable and solvable
    candidates = [
        u for u in unspent
        if u.get("spendable", False) and btc_to_sats(u["amount"]) >= min_amount_sats
    ]
    if not candidates:
        return None

    # Pick the largest UTXO to ensure ample change
    candidates.sort(key=lambda u: btc_to_sats(u["amount"]), reverse=True)
    best = candidates[0]
    return ParentUtxo(
        txid=best["txid"],
        vout=int(best["vout"]),
        amount_sats=btc_to_sats(best["amount"]),
        address=best.get("address", ""),
        script_pub_key=best.get("scriptPubKey", ""),
    )


async def fund_forker_node(
    forker_id: int = FORKER_NODE_ID,
    source_node_id: int = PROBE_NODE_IDS[0],
    target_amount_sats: int = DEFAULT_TARGET_SATS,
) -> ParentUtxo:
    """Ensure the Forker (Node 2) possesses a mature spendable UTXO of at least target_amount_sats.

    Workflow:
    1. Check Node 2's forker_wallet for existing confirmed UTXOs.
    2. If missing, fund Node 2 from source_node (Probe 0).
    3. If Probe 0 also lacks mature coins, mine 101 blocks on Probe 0 to mature coinbase rewards.
    4. Send target amount to Node 2 and mine 1 block to confirm.
    """
    log.info("Checking funding status on Forker (Node %d)...", forker_id)

    # 1. Connect to Forker (Node 2) base RPC and ensure wallet
    async with make_rpc_client(forker_id) as rpc_forker_base:
        await ensure_wallet_loaded(rpc_forker_base, FORKER_WALLET_NAME)

    # 2. Check for existing spendable UTXO
    async with make_rpc_client(forker_id, wallet=FORKER_WALLET_NAME) as rpc_forker_w:
        existing_utxo = await find_spendable_utxo(rpc_forker_w, min_amount_sats=target_amount_sats)
        if existing_utxo:
            log.info("Forker (Node %d) already has spendable UTXO: %s:%d (%d sats)",
                     forker_id, existing_utxo.txid, existing_utxo.vout, existing_utxo.amount_sats)
            return existing_utxo

        # Generate a new deposit address
        deposit_addr: str = await rpc_forker_w.call("getnewaddress", "forker_deposit")

    # 3. Source node (Probe 0) preparation
    log.info("Funding Forker from Source (Node %d)...", source_node_id)
    async with make_rpc_client(source_node_id) as rpc_source_base:
        await ensure_wallet_loaded(rpc_source_base, SOURCE_WALLET_NAME)

    async with make_rpc_client(source_node_id, wallet=SOURCE_WALLET_NAME) as rpc_source_w:
        source_bal_btc = await rpc_source_w.call("getbalance")
        source_bal_sats = btc_to_sats(source_bal_btc)

        if source_bal_sats < target_amount_sats + 100_000:
            log.info("Source Node %d has insufficient balance (%d sats). Mining 101 blocks to mature coinbase...",
                     source_node_id, source_bal_sats)
            mine_addr = await rpc_source_w.call("getnewaddress", "mining")
            await rpc_source_w.call("generatetoaddress", 101, mine_addr)
            await asyncio.sleep(0.5)

        # Send target amount to Forker
        btc_amount_str = sats_to_btc_str(target_amount_sats)
        log.info("Sending %s BTC (%d sats) from Node %d to Node %d (%s)...",
                 btc_amount_str, target_amount_sats, source_node_id, forker_id, deposit_addr)
        funding_txid = await rpc_source_w.call("sendtoaddress", deposit_addr, float(btc_amount_str))
        log.info("Funding transaction dispatched: %s", funding_txid)

        # Mine 1 block on source node to confirm the transaction
        mine_addr = await rpc_source_w.call("getnewaddress", "mining")
        await rpc_source_w.call("generatetoaddress", 1, mine_addr)

        # Ensure direct connection to forker so the block propagates immediately
        forker_p2p, _ = get_ports(forker_id)
        try:
            await rpc_source_w.call("addnode", f"127.0.0.1:{forker_p2p}", "onetry")
        except Exception:
            pass

    # 4. Wait a brief moment for block propagation to Forker
    log.info("Waiting for block propagation to Forker (Node %d)...", forker_id)
    for i in range(40):
        await asyncio.sleep(0.5)
        async with make_rpc_client(forker_id, wallet=FORKER_WALLET_NAME) as rpc_forker_w:
            utxo = await find_spendable_utxo(rpc_forker_w, min_amount_sats=target_amount_sats)
            if utxo:
                log.info("Successfully confirmed UTXO on Forker: %s:%d (%d sats)",
                         utxo.txid, utxo.vout, utxo.amount_sats)
                return utxo
            if i % 5 == 0:
                h = await rpc_forker_w.call("getblockcount")
                p = await rpc_forker_w.call("getpeerinfo")
                log.debug("Forker (Node %d) status: height=%d, peers=%d", forker_id, h, len(p))

    raise TimeoutError(f"Timed out waiting for confirmed UTXO on Forker (Node {forker_id})")
