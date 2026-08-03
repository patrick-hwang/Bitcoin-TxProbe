import json
import sys
import time
from decimal import Decimal
from dataclasses import dataclass

from .cli import nodes_cli

@dataclass
class RoundInfo:
    source_set: list
    sink_set: list
    marker_txs: list
    phase_1_command: str
    phase_2_command: str
    phase_3_command: str

def ensure_wallet():
    if "mywallet" not in nodes_cli[0].wsl_cli_json("listwallets"):
        nodes_cli[0].wsl_cli_json("loadwallet", "mywallet")

def get_utxo():
    ensure_wallet()
    elapsed = 0
    timeout = 300
    interval = 2

    while True:
        while elapsed < timeout:
            utxos = nodes_cli[0].wsl_cli_json("listunspent")
            candidates = []
            for u in utxos:
                if not u.get("spendable"):
                    continue
                amt = Decimal(str(u["amount"]))
                if amt >= Decimal("0.00003000"):
                    candidates.append((amt, u["txid"], u["vout"]))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                return candidates[0][1], candidates[0][2], candidates[0][0]
            time.sleep(interval)
            elapsed += interval
        print("No spendable UTXO >= 3000 sats in wallet found. Fund more!", file=sys.stderr)
        ans = input("Wait for the spendable UTXO - 5 minutes (Enter) / Halt (h): ").strip().lower()
        if ans == "h":
            sys.exit(1)
        elapsed = 0

def get_own_address():
    ensure_wallet()
    return nodes_cli[0].wsl_cli_raw("getnewaddress")

def generate_rounds(vertices):
    nodes_by_height = {}

    def traverse(l, r, height):
        if r - l <= 1:
            return
        mid = (l + r) // 2
        nodes_by_height.setdefault(height, []).append((l, r))
        traverse(l, mid, height + 1)
        traverse(mid, r, height + 1)

    traverse(0, len(vertices), 0)

    rounds = []
    for h in sorted(nodes_by_height):
        source = []
        sink = []
        for l, r in nodes_by_height[h]:
            mid = (l + r) // 2
            source.extend(vertices[l:mid])
            sink.extend(vertices[mid:r])
        rounds.append((source, sink))

    return rounds

def preparing_commands_for_a_round(source_list, sink_list, debug=False):
    n = len(source_list)

    txid, vout, amount_btc = get_utxo()
    final_addr = get_own_address()

    amount_sats = int(amount_btc * Decimal(100_000_000))

    descs = nodes_cli[0].wsl_cli_json("listdescriptors")
    wpkh_desc = None
    for entry in descs["descriptors"]:
        desc = entry.get("desc", "")
        if entry.get("active") and desc.startswith("wpkh("):
            wpkh_desc = desc
            break
    if wpkh_desc is None:
        print("Error: cannot find active wpkh descriptor", file=sys.stderr)
        sys.exit(1)

    change_addrs = nodes_cli[0].wsl_cli_json("deriveaddresses", wpkh_desc, f"[0,{n}]")
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
        unsigned_hex = nodes_cli[0].wsl_cli_raw("createrawtransaction", utxo_input, output)
        signed = nodes_cli[0].wsl_cli_json("signrawtransactionwithwallet", unsigned_hex)
        if not signed.get("complete"):
            print(f"Error: signing failed for tx {i}", file=sys.stderr)
            sys.exit(1)
        signed_hex = signed["hex"]
        decoded = nodes_cli[0].wsl_cli_json("decoderawtransaction", signed_hex)
        txid_new = decoded["txid"]
        wtxid = decoded.get("hash", txid_new)
        spk = decoded["vout"][0]["scriptPubKey"]["hex"]
        conflicting_txs.append({
            "uhex": unsigned_hex, "hex": signed_hex,
            "txid": txid_new, "wtxid": wtxid,
            "spk": spk, "amount_btc": parent_btc,
        })

    parent_txs = conflicting_txs[:n]
    flooding_tx = conflicting_txs[n].copy()

    marker_txs = []
    for i in range(n):
        parent = conflicting_txs[i]
        prevtxs = json.dumps([{
            "txid": parent["txid"], "vout": 0,
            "scriptPubKey": parent["spk"], "amount": parent["amount_btc"],
        }])
        marker_input = json.dumps([{"txid": parent["txid"], "vout": 0}])
        marker_output = json.dumps({final_addr: marker_btc})
        unsigned_hex = nodes_cli[0].wsl_cli_raw("createrawtransaction", marker_input, marker_output)
        signed = nodes_cli[0].wsl_cli_json("signrawtransactionwithwallet", unsigned_hex, prevtxs)
        if not signed.get("complete"):
            print(f"Error: signing failed for marker tx {i}", file=sys.stderr)
            sys.exit(1)
        signed_hex = signed["hex"]
        decoded = nodes_cli[0].wsl_cli_json("decoderawtransaction", signed_hex)
        txid_m = decoded["txid"]
        wtxid_m = decoded.get("hash", txid_m)
        marker_txs.append({
            "uhex": unsigned_hex, "hex": signed_hex,
            "txid": txid_m, "wtxid": wtxid_m,
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

    result = RoundInfo(
        source_set=source_list, sink_set=sink_list, marker_txs=marker_txs,
        phase_1_command=phase_1_command, phase_2_command=phase_2_command,
        phase_3_command=phase_3_command,
    )

    if debug:
        print(result.__str__())

    return result
