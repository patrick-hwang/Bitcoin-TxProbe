import json
import re
import subprocess
import sys
import shlex
import time

from collections.abc import Mapping, Iterable, Sequence
from decimal import Decimal

from .BitcoinCliError import BitcoinCliError
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

    def get_localaddress(self) -> str:
        network_info = self.cli_json("getnetworkinfo")
        if not isinstance(network_info, Mapping):
            raise BitcoinCliError(f"Node {id}: getnetworkinfo response is unavailable.")
        local_addresses = network_info.get("localaddresses")
        if not isinstance(local_addresses, Sequence):
            raise BitcoinCliError(f"Node {id}: getnetworkinfo.localaddresses is unavailable.")
        if not local_addresses or not isinstance(local_addresses[0], Mapping):
            raise BitcoinCliError(f"Node {id}: getnetworkinfo.localaddresses[0] is unavailable.")
        host = local_addresses[0].get("address")
        port = local_addresses[0].get("port")
        if not isinstance(host, str) or not host:
            raise BitcoinCliError(f"Node {id}: getnetworkinfo.localaddresses[0].address is unavailable.")
        if not isinstance(port, int):
            port = None
        return endpoint_tuple_to_str((host.lower(), port))

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
        peers = self.cli_json("getpeerinfo")
        return [NodeIdentity(peer["addr"]) for peer in peers if not peer["addr"].startswith("127.0.0.1")]