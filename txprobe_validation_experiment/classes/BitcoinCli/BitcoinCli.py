import json
import re
import subprocess
import sys
import shlex
import time

from collections import defaultdict
from collections.abc import Mapping, Iterable, Sequence
from decimal import Decimal

from .BitcoinCliError import BitcoinCliError, BitcoinCliNoWallet
from ...dataclasses.TX_message import TX_message
from ...dataclasses.NodeIdentity import NodeIdentity
from ...objects.node_indices import probe_nodes

class BitcoinCli:
    def __init__(self, id: int, rpcport: int, rpcuser: str, rpcpassword: str, wsl: bool = False,
                 wallet_name: str = ""):
        self.id = id
        self.RPCARGS = [f"-rpcport={rpcport}", f"-rpcuser={rpcuser}", f"-rpcpassword={rpcpassword}"]
        self.wsl = wsl
        self.wallet_name = wallet_name
        if (len(self.wallet_name) > 0):
            self.load_wallet()

    def wsl_cli(self, *args, ignore: bool = False):
        quoted = [shlex.quote(a) for a in ["build/bin/bitcoin-cli"] + self.RPCARGS + list(args)]
        cmd = "wsl " + " ".join(quoted)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if ignore == False and result.returncode != 0:
            err_str = result.stderr.strip()
            code_match = re.search(r"error code:\s*(-?\d+)", err_str)
            code = int(code_match.group(1)) if code_match else None
            raise BitcoinCliError(self.id, code, err_str.splitlines()[-1], err_str)
        else:
            return result

    def win_cli(self, *args, ignore: bool = False):
        cmd = ["bitcoin-cli"] + self.RPCARGS + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if ignore == False and result.returncode != 0:
            err_str = result.stderr.strip()
            code_match = re.search(r"error code:\s*(-?\d+)", err_str)
            code = int(code_match.group(1)) if code_match else None
            raise BitcoinCliError(self.id, code, err_str.splitlines()[-1], err_str)
        else:
            return result

    def cli_raw(self, *args, ignore: bool = False):
        if self.wsl:
            return self.wsl_cli(*args, ignore=ignore).stdout.strip()
        else:
            return self.win_cli(*args, ignore=ignore).stdout.strip()

    def cli_json(self, *args):
        if self.wsl:
            return json.loads(self.wsl_cli(*args).stdout)
        else:
            return json.loads(self.win_cli(*args).stdout)

    ### Identity
    def get_identity(self) -> NodeIdentity:
        local_addresses = self.cli_json("getnetworkinfo")["localaddresses"]
        onion_entry = next(
            (item for item in local_addresses if item.get("address", "").endswith(".onion")),
            None
        )
        if onion_entry is None:
            raise LookupError(f"Node {id} does not have a .onion address!")
        return NodeIdentity(f"{onion_entry['address']}:{onion_entry['port']}")

    def get_peer_address(self, id: int, ignore: bool = False) -> str | None:
        peers = self.cli_json("getpeerinfo")
        for peer in peers:
            if peer["id"] == id:
                return peer["addr"]
        if ignore:
            return None
        else:
            raise RuntimeError(f"Cannot find the peer with id = {id} in node {self.id}!")

    def get_peer_identity(self, id: int, ignore: bool = False) -> NodeIdentity | None:
        addr = self.get_peer_address(id, ignore=True)
        if addr:
            return NodeIdentity(addr = addr)
        if ignore:
            return None
        raise RuntimeError(f"Cannot find identity of peer with id = {id} in node {self.id}!")

    def get_peer_id(self, addr: str, ignore = False) -> int | None:
        peers = self.cli_json("getpeerinfo")
        for peer in peers:
            if peer["addr"] == addr:
                return peer["id"]
        if ignore:
            return None
        else:
            raise RuntimeError(str(f"Cannot find the peer with addr = {addr} in node {self.id}!"))

    def get_peer_id_from_node_list(self, nodes: list[NodeIdentity]) -> list[int]:
        peers = self.get_peer_list()
        result: list[int] = list()
        for node in nodes:
            if node in peers:
                id = self.get_peer_id(node.addr, ignore=True)
                if id:
                    result.append(id)
        return result

    def get_peer_list(self, block_relay_only: bool = False, local_addr: bool = False) -> list[NodeIdentity]:
        """Get peers' NodeIdentity list"""
        peers = self.cli_json("getpeerinfo")
        result: list[NodeIdentity] = []
        for peer in peers:
            skip = (not block_relay_only and peer["connection_type"] == "block-relay-only") or \
                   (not local_addr and peer["addr"].startswith("127.0.0.1"))
            if skip:
                continue
            result.append(NodeIdentity(addr = peer["addr"]))
        return result

    def get_peerid_list(self, block_relay_only: bool = False, local_addr: bool = False) -> list[int]:
        """Get peers' index list"""
        peers = self.cli_json("getpeerinfo")
        result: list[int] = []
        for peer in peers:
            skip = (not block_relay_only and peer["connection_type"] == "block-relay-only") or \
                   (not local_addr and peer["addr"].startswith("127.0.0.1"))
            if skip:
                continue
            result.append(peer["id"])
        return result

    ### Sending messages
    def send_an_inv_to_all(self, tx: TX_message):
        """Send an INV message to all peers"""
        if self.id not in probe_nodes:
            raise RuntimeError(
                f"Only probe nodes can call send_an_inv_to_all() function.\n"
                f"But node {self.id} which is not a probe node called this!")
        self.cli_json("sendinv_orphan", json.dumps([tx.hexstr]), json.dumps(self.get_peerid_list(block_relay_only = False, local_addr = False)))

    def send_txs_to(self, txs: list[TX_message], ids: list[int]):
        """Send transactions to specific peers"""
        if self.id not in probe_nodes:
            raise RuntimeError(str(f"The node {self.id} is not a probe node while this send_txs_to function required to be called by a probe node."))
        for tx in txs:
            hexstring = tx.hexstr

            with open("txprobe_debug.log", "a") as f:
                f.write(
                    f"Sending transaction:\n"
                    f"    txid: {tx.txid}\n"
                    f"    wtxid: {tx.wtxid}\n"
                    f"    hexstring: {hexstring}\n"
                    f"    peer_ids: {json.dumps(ids)}\n"
                )

            self.cli_raw("sendrawtransaction_orphan", hexstring, json.dumps(0), json.dumps(0), json.dumps(ids)) 

    ### Wallet
    def get_change_descriptors(
        self,
        type: str
    ):
        descs = self.cli_json("listdescriptors")
        target_desc = None
        for entry in descs["descriptors"]:
            desc = entry.get("desc", "")
            if entry.get("active") and desc.startswith(f"{type}("):
                target_desc = desc
                break
        if target_desc is None:
            print("Error: cannot find active wpkh descriptor", file=sys.stderr)
            sys.exit(1)
        return target_desc

    def get_change_addresses(
        self,
        number_of_addresses: int
    ) -> list[str]:
        wpkh_desc = self.get_change_descriptors("wpkh")
        change_addrs = self.cli_json("deriveaddresses", wpkh_desc, f"[0,{number_of_addresses - 1}]")
        if len(change_addrs) != number_of_addresses:
            print(f"Error: expected {number_of_addresses} addresses, got {len(change_addrs)}", file=sys.stderr)
            sys.exit(1)
        return change_addrs

    def load_wallet(self):
        if self.wallet_name not in self.cli_json("listwallets"):
            print(f'Node {self.id} load_wallet: Loading wallet {self.wallet_name}')
            self.cli_json("loadwallet", self.wallet_name)
        if len(self.RPCARGS) < 4:
            self.RPCARGS.append(f"-rpcwallet={self.wallet_name}")

    def ensure_wallet(self, target_wallet: str, debug: bool = False):
        if len(target_wallet) == 0:
            raise BitcoinCliNoWallet(f"Ensure wallet: Did not specified a wallet for node {self.id}")
        if target_wallet not in self.cli_json("listwallets"):
            if debug:
                print(f'Node {self.id} ensure_wallet: The wallet is not loaded, now load it\n')
            self.wallet_name = target_wallet
            self.load_wallet()
        self.RPCARGS[3] = f"-rpcwallet={target_wallet}"

    def get_utxo(self) -> tuple[
            str,
            int,
            Decimal
        ]:
        self.ensure_wallet(self.wallet_name)
        elapsed = 0
        timeout = 60
        interval = 2

        while True:
            while elapsed < timeout:
                utxos = self.cli_json("listunspent")
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
            print(f"Get UTXO node {self.id}: No spendable UTXO >= 3000 sats in wallet found. Fund more!", file=sys.stderr)
            elapsed = 0

    def get_own_address(self, target_wallet: str = "") -> str:
        if not target_wallet:
            target_wallet = self.wallet_name
        self.ensure_wallet(target_wallet)
        return self.cli_raw("getnewaddress")

    ### Create transactions
    def create_a_raw_tx(self,
                        inputs: list[dict[str, str | int]],
                        outputs: list[dict[str, Decimal]]
                        ) -> str:
        return self.cli_raw("createrawtransaction", 
                    json.dumps(inputs), json.dumps(outputs, default=str))

    def sign_a_raw_tx(self, rawhexstr: str, prevtxs: str = "") -> str:
        signed_information = dict()
        if prevtxs:
            signed_information = self.cli_json("signrawtransactionwithwallet", rawhexstr, prevtxs)
        else:
            signed_information = self.cli_json("signrawtransactionwithwallet", rawhexstr)
        if not signed_information.get("complete"):
            raise RuntimeError("Create a new tx: Failed to sign the transaction.")
        return signed_information["hex"]

    def create_a_new_tx(self) -> TX_message:
        """Create a new transaction manually"""
        txid, vout, amount_btc = self.get_utxo()
        final_addr = self.get_own_address(self.wallet_name)
        out_btc = amount_btc - Decimal("0.00010000")

        unsigned_hex = self.create_a_raw_tx(
            [{"txid": txid, "vout": vout}],
            [{final_addr: out_btc}]
        )
        signed_hex = self.sign_a_raw_tx(unsigned_hex)
        signed_transaction = self.cli_json("decoderawtransaction", signed_hex)
        return TX_message(
            hexstr=signed_hex,
            txid=signed_transaction["txid"],
            wtxid=signed_transaction["hash"]
        )
    
    def create_many_new_txs(self, num: int) -> list[TX_message]:
        """Create `num` new raw transactions
        :param num: the number of new transactions wanted
        """
        txid, vout, amount_btc = self.get_utxo()
        out_btc = amount_btc - Decimal("0.00010000")        
        address_list = self.get_change_addresses(num)

        result: list[TX_message] = list()

        for final_addr in address_list:
            unsigned_hex = self.create_a_raw_tx(
                [{"txid": txid, "vout": vout}],
                [{final_addr: out_btc}]
            )
            signed_hex = self.sign_a_raw_tx(unsigned_hex)
            signed_transaction = self.cli_json("decoderawtransaction", signed_hex)
            result.append(TX_message(
                signed_hex,
                signed_transaction["txid"],
                signed_transaction["hash"]
            ))

        return result

    def create_child_transactions(self, parent_transaction_list: list[TX_message]):
        result: list[TX_message] = list()
        for tx in parent_transaction_list:
            info = self.cli_json("decoderawtransaction", tx.hexstr)
            output_btc = Decimal(str(info["vout"][0]["value"])) - Decimal("0.0001000")

            raw_hexstr = self.create_a_raw_tx(
                [{"txid": tx.txid, "vout": 0}],
                [{self.get_own_address(): output_btc}]
            )

            prevtxs = json.dumps([
                {
                    "txid": tx.txid,
                    "vout": 0,
                    "scriptPubKey": info["vout"][0]["scriptPubKey"]["hex"],
                    "amount": info["vout"][0]["value"]
                }
            ])

            signed_hexstr = self.sign_a_raw_tx(raw_hexstr, prevtxs)
            signed_transaction = self.cli_json("decoderawtransaction", signed_hexstr)
            result.append(TX_message(
                signed_hexstr,
                signed_transaction["txid"],
                signed_transaction["hash"]
            ))
        return result

    ### Mempool
    def get_mempool_txids(self) -> set[str]:
        """Retrieve all the txids in the mempool"""
        tx_list = self.cli_json("getrawmempool")
        return set(tx_list)

    def retrieve_getdata_requests(self) -> dict[str, set[int]]:
        GETDATA_PATTERN = re.compile(r"received getdata for: \S+ ([0-9a-f]{64}) peer=(\d+)")
        file_path: str = f"txprobe_{self.id}.log"
        result: dict[str, set[int]] = defaultdict(set)
        with open(file_path) as log_file:
            for line in log_file:
                if "received getdata for:" not in line:
                    continue

                match = GETDATA_PATTERN.search(line)
                if match:
                    logged_hash = match.group(1)
                    logged_peer = int(match.group(2))
                    result[logged_hash].add(logged_peer)
        return result

    ### Eliminate nodes
    def eliminate_cannot_invblock_nodes(self, inv: TX_message, debug: bool = False):
        """Eliminate peers that send GETDATA message about INV message inv"""
        file_path: str = f"txprobe_{self.id}.log"
        txid_list: list[str] = [inv.txid, inv.wtxid]
        peerid_list: list[int] = self.get_peerid_list(block_relay_only = False, local_addr = False)
        try:
            with open(file_path) as log_file:
                for line in log_file:
                    match = re.search(r"received getdata for: \S+ ([0-9a-f]{64}) peer=(\d+)", line)
                    if match is None:
                        continue
                    log_hash = match.group(1)
                    log_peer = int(match.group(2))
                    if log_hash in txid_list and log_peer in peerid_list:
                        addr_peer = self.get_peer_address(log_peer)
                        if debug:
                            print(f"Found an peer that cannot apply INVBLOCK: {addr_peer}! Removing it from node {self.id}'s peer list.")
                        self.cli_raw("addnode", addr_peer, "remove", ignore=True)
                        self.cli_raw("disconnectnode", addr_peer)
                        peerid_list.remove(log_peer)
        except Exception as e:
            print(f"Encounter an exception when eliminating cannot invblock nodes: {e}")

    def eliminate_nodes_not_in_list(self, peer_list: list[NodeIdentity], debug: bool = False):
        """Eliminate nodes that do not belong to a specific list."""
        peers = self.get_peer_list(block_relay_only=False, local_addr=False)
        try:
            for peer in peers:
                if peer not in peer_list:
                    if debug:
                        print(f"Eliminating peer {peer.addr} from node {self.id}'s peer list.")
                    self.cli_raw("addnode", peer.addr, "remove", ignore=True)
                    self.cli_raw("disconnectnode", peer.addr, ignore=True)
        except Exception as e:
            print(f"Encounter an exception when eliminate nodes not in a specified peer list from node {self.id}!")

    ### Logging
    def clear_log_file(self):
        with open(f"txprobe_{self.id}.log", "w") as f:
            pass