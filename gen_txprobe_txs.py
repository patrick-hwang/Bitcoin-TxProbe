#!/usr/bin/env python3
import subprocess
import json
import sys
from decimal import Decimal

RPC_ARGS = ["-rpcport=48347", "-rpcuser=expuser0", "-rpcpassword=strongpassword0"]

def bcli_raw(*args):
    cmd = ["build/bin/bitcoin-cli", "-rpcwallet=mywallet"] + RPC_ARGS + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"bitcoin-cli error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

def bcli_json(*args):
    cmd = ["build/bin/bitcoin-cli", "-rpcwallet=mywallet"] + RPC_ARGS + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"bitcoin-cli error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)

def ensure_wallet():
    if "mywallet" not in bcli_json("listwallets"):
        bcli_json("loadwallet", "mywallet")

def get_utxo():
    ensure_wallet()
    utxos = bcli_json("listunspent")
    candidates = []
    for u in utxos:
        if not u.get("spendable"):
            continue
        amt = Decimal(str(u["amount"]))
        if amt >= Decimal("0.00003000"):
            candidates.append((amt, u["txid"], u["vout"]))
    if not candidates:
        print("Error: no spendable UTXO >= 3000 sats in wallet. Fund the wallet first.", file=sys.stderr)
        sys.exit(1)
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2], candidates[0][0]

def get_own_address():
    ensure_wallet()
    return bcli_raw("getnewaddress")

def main():
    if len(sys.argv) != 4:
        print("Usage: python gen_txprobe_txs.py <n> <source_set> <sink_set>")
        print("  <source_set>  JSON array of peer IDs for source set (size = n)")
        print("  <sink_set>    JSON array of peer IDs for sink set")
        sys.exit(1)

    n = int(sys.argv[1])
    source_list = json.loads(sys.argv[2])
    sink_list = json.loads(sys.argv[3])

    if len(source_list) != n:
        print(f"Error: source_set size {len(source_list)} != n ({n})", file=sys.stderr)
        sys.exit(1)
    if len(sink_list) < 1:
        print("Error: sink_set must not be empty", file=sys.stderr)
        sys.exit(1)

    txid, vout, amount_btc = get_utxo()
    final_addr = get_own_address()
    print(f"Using UTXO: {txid}:{vout} ({amount_btc} BTC)", file=sys.stderr)
    print(f"Destination address: {final_addr}", file=sys.stderr)

    amount_sats = int(amount_btc * Decimal(100_000_000))
    if amount_sats < 3000:
        print("Error: UTXO amount must be >= 0.00003000 BTC (3000 satoshi)", file=sys.stderr)
        sys.exit(1)

    descs = bcli_json("listdescriptors")
    wpkh_desc = None
    for entry in descs["descriptors"]:
        desc = entry.get("desc", "")
        if entry.get("active") and desc.startswith("wpkh("):
            wpkh_desc = desc
            break
    if wpkh_desc is None:
        print("Error: cannot find active wpkh descriptor", file=sys.stderr)
        sys.exit(1)

    change_addrs = bcli_json("deriveaddresses", wpkh_desc, f"[0,{n}]")
    if len(change_addrs) != n + 1:
        print(f"Error: expected {n+1} addresses, got {len(change_addrs)}", file=sys.stderr)
        sys.exit(1)

    parent_sats = amount_sats - 1000
    marker_sats = amount_sats - 2000
    parent_btc = parent_sats / 1e8
    marker_btc = marker_sats / 1e8

    conflicting_txs = []
    utxo_input = json.dumps([{"txid": txid, "vout": vout}])

    for i in range(n + 1):
        change_addr = change_addrs[i]
        output = json.dumps({change_addr: parent_btc})

        unsigned_hex = bcli_raw("createrawtransaction", utxo_input, output)

        signed = bcli_json("signrawtransactionwithwallet", unsigned_hex)
        if not signed.get("complete"):
            print(f"Error: signing failed for tx {i}", file=sys.stderr)
            sys.exit(1)
        signed_hex = signed["hex"]

        decoded = bcli_json("decoderawtransaction", signed_hex)
        txid_new = decoded["txid"]
        wtxid = decoded.get("hash", txid_new)
        spk = decoded["vout"][0]["scriptPubKey"]["hex"]

        conflicting_txs.append({
            "uhex": unsigned_hex,
            "hex": signed_hex,
            "txid": txid_new,
            "wtxid": wtxid,
            "spk": spk,
            "amount_btc": parent_btc,
        })

    parent_txs = conflicting_txs[:n]
    flooding_tx = conflicting_txs[n].copy()

    marker_txs = []
    for i in range(n):
        parent = conflicting_txs[i]
        prevtxs = json.dumps([{
            "txid": parent["txid"],
            "vout": 0,
            "scriptPubKey": parent["spk"],
            "amount": parent["amount_btc"],
        }])

        marker_input = json.dumps([{"txid": parent["txid"], "vout": 0}])
        marker_output = json.dumps({final_addr: marker_btc})

        unsigned_hex = bcli_raw("createrawtransaction", marker_input, marker_output)
        signed = bcli_json("signrawtransactionwithwallet", unsigned_hex, prevtxs)
        if not signed.get("complete"):
            print(f"Error: signing failed for marker tx {i}", file=sys.stderr)
            sys.exit(1)
        signed_hex = signed["hex"]

        decoded = bcli_json("decoderawtransaction", signed_hex)
        txid_m = decoded["txid"]
        wtxid_m = decoded.get("hash", txid_m)

        marker_txs.append({
            "uhex": unsigned_hex,
            "hex": signed_hex,
            "txid": txid_m,
            "wtxid": wtxid_m,
        })

    cli_base = "build/bin/bitcoin-cli -rpcwallet=mywallet -rpcport=48347 -rpcuser=expuser0 -rpcpassword=strongpassword0"

    all_txs  = json.dumps([t["hex"] for t in conflicting_txs])
    parents  = json.dumps([t["hex"] for t in parent_txs])
    markers  = json.dumps([t["hex"] for t in marker_txs])
    src      = json.dumps(source_list)
    snk      = json.dumps(sink_list)
    all_peer = json.dumps(source_list + sink_list)

    phase_1_command = f"{cli_base} sendinv_orphan '{all_txs}' '{all_peer}'"
    phase_2_command = f"{cli_base} sendtxs_orphan '{src}' '{snk}' '{parents}' '{markers}' '{flooding_tx['hex']}'"
    phase_3_command = f"{cli_base} sendinv_orphan '{markers}' '{snk}'"

    for item in parent_txs + [flooding_tx]:
        del item["spk"]
        del item["amount_btc"]

    print(json.dumps({
        "parent_txs": parent_txs,
        "flooding_tx": flooding_tx,
        "marker_txs": marker_txs,
        "phase_1_command": phase_1_command,
        "phase_2_command": phase_2_command,
        "phase_3_command": phase_3_command,
    }, indent=2))
    print(file=sys.stderr)
    print("## Phase 1: INV all conflicting txs to all peers", file=sys.stderr)
    print(phase_1_command, file=sys.stderr)
    print(file=sys.stderr)
    print("## Phase 2: flood→sink, sleep 10s, parents→source, sleep 10s, markers→source", file=sys.stderr)
    print(phase_2_command, file=sys.stderr)
    print(file=sys.stderr)
    print("## Phase 3: INV marker txs to sink set", file=sys.stderr)
    print(phase_3_command, file=sys.stderr)

if __name__ == "__main__":
    main()
