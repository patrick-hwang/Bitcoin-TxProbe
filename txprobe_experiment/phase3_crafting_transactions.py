from decimal import Decimal
import json
import sys
from dataclasses import dataclass

from .groundtruth import (
    GroundTruthSnapshot,
    #NodeIdentity
)
from .cli import (
    nodes_cli,
)

@dataclass
class TxProbeTransaction:
    conflicting_transactions: list
    marker_transactions: list

def crafting_txprobe_transactions(
    snapshot: GroundTruthSnapshot,
    debug: bool = False,
) -> None:
    source_set = (identity for identity in snapshot.nodes if isinstance(identity, int))
    sink_set = (identity for identity in snapshot.nodes if isinstance(identity, int) == False)
    txid, vout, amount_btc = nodes_cli[0].get_utxo()
    final_addr = nodes_cli[0].get_own_address("mywallet")
    amount_sats = int(amount_btc * Decimal(100_000_000))
    change_addresses = nodes_cli[0].get_change_addresses(len(source_set) + 1)

    parent_sats = amount_sats - 1000
    marker_sats = amount_sats - 2000
    parent_btc = parent_sats / 1e8
    marker_btc = marker_sats / 1e8
    conflicting_txs = []
    utxo_input = json.dumps([{"txid": txid, "vout": vout}])
    n = len(source_set)
    for i in range(n + 1):
        change_addr = change_addresses[i]
        output = json.dumps({change_addr: parent_btc})
        unsigned_hex = nodes_cli[0].cli_raw("createrawtransaction", utxo_input, output)
        signed = nodes_cli[0].cli_json("signrawtransactionwithwallet", unsigned_hex)
        if not signed.get("complete"):
            print(f"Error: signing failed for tx {i}", file=sys.stderr)
            sys.exit(1)
        signed_hex = signed["hex"]
        decoded = nodes_cli[0].cli_json("decoderawtransaction", signed_hex)
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
        unsigned_hex = nodes_cli[0].cli_raw("createrawtransaction", marker_input, marker_output)
        signed = nodes_cli[0].cli_json("signrawtransactionwithwallet", unsigned_hex, prevtxs)
        if not signed.get("complete"):
            print(f"Error: signing failed for marker tx {i}", file=sys.stderr)
            sys.exit(1)
        signed_hex = signed["hex"]
        decoded = nodes_cli[0].cli_json("decoderawtransaction", signed_hex)
        txid_m = decoded["txid"]
        wtxid_m = decoded.get("hash", txid_m)
        marker_txs.append({
            "uhex": unsigned_hex, "hex": signed_hex,
            "txid": txid_m, "wtxid": wtxid_m,
        })

    result = TxProbeTransaction(
        conflicting_transactions = conflicting_txs,
        marker_transactions = marker_txs
    )

    if (debug): 
        print(result.__str__())

    return result