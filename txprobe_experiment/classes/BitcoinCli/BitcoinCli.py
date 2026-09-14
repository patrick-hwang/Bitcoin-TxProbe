import json
import re
import subprocess
import sys
import shlex
import time

from collections.abc import Mapping, Iterable, Sequence
from decimal import Decimal

from .BitcoinCliError import BitcoinCliError, BitcoinCliNoWallet
from ...dataclasses.INV_message import INV_message
from ...dataclasses.NodeIdentity import NodeIdentity
from ...address import endpoint_tuple_to_str

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
    ):
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

    def get_utxo(self):
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
        self.ensure_wallet(target_wallet)
        return self.cli_raw("getnewaddress")

    def get_identity(self) -> NodeIdentity:
        local_addresses = self.cli_json("getnetworkinfo")["localaddresses"]
        onion_entry = next(
            (item for item in local_addresses if item.get("address", "").endswith(".onion")),
            None
        )
        if onion_entry is None:
            raise LookupError(f"Node {id} does not have a .onion address!")
        return NodeIdentity(f"{onion_entry['address']}:{onion_entry['port']}")

    def get_peer_list(self) -> list[NodeIdentity]:
        """Get peers' NodeIdentity list"""
        peers = self.cli_json("getpeerinfo")
        return [NodeIdentity(peer["addr"]) for peer in peers if not peer["addr"].startswith("127.0.0.1")]

    def get_peerid_list(self) -> list[int]:
        """Get peers' index list"""
        peers = self.cli_json("getpeerinfo")
        return [peer["id"] for peer in peers if not peer["addr"].startswith("127.0.0.1")]

    def create_a_new_tx(self) -> INV_message:
        """Create a new transaction manually"""
        txid, vout, amount_btc = self.get_utxo()
        final_addr = self.get_own_address(self.wallet_name)
        out_btc = amount_btc - Decimal("0.00010000")

        unsigned_hex = self.cli_raw(
            "createrawtransaction",
            json.dumps([{"txid": txid, "vout": vout}]), 
            json.dumps({final_addr: out_btc}, default=str)
        )
        signed = self.cli_json("signrawtransactionwithwallet", unsigned_hex)
        if not signed.get("complete"):
            raise BitcoinCliError("Create a new tx: Failed to sign the transaction.")
        decoded = self.cli_json("decoderawtransaction", signed["hex"])
        txid_new = decoded["txid"]
        wtxid = decoded["hash"]
        return INV_message(
            hexstr=txid_new,
            wtxid=wtxid
        )

    def send_an_inv_to_all(self, inv: INV_message):
        """Send an INV message to all peers"""
        self.cli_json("sendinv_orphan", inv.hexstr, json.dumps(self.get_peerid_list()))

    def eliminate_cannot_invblock_nodes(self, inv: INV_message):
        """Eliminate peers that send GETDATA message about INV message inv"""
        filepath: str = f"txprobe_{self.id}.log"
        txid_list: list[str] = [inv.hexstr, inv.wtxid]
        peerid_list: list[int] = self.get_peerid_list()
        try:
            with open(filepath) as log_file:
                for line in log_file:
                    match = re.compile(r"received getdata for: \S+ ([0-9a-f]{64}) peer=(\d+)")
                    log_hash = match.group(1)
                    log_peer = int(match.group(2))
                    if log_hash in txid_list and log_peer in peerid_list:
                        addr_peer = self.get_peer_address(log_peer)
                        self.cli_raw("addnode", addr_peer, "remove")
                        self.cli_raw("disconnectnode", addr_peer)
        except Exception as e:
            print(f"Encounter an exception when eliminating cannot invblock nodes: {e}")

    def get_peer_address(self, id: int) -> str:
        peers = self.cli_json("getpeerinfo")
        for peer in peers:
            if peer["id"] == id:
                return peer["addr"]