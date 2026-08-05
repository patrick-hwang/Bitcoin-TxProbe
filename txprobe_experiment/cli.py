import subprocess
import json
import sys
import shlex

class BitcoinCli:
    def __init__(self, id: int, rpcport: int, rpcuser: str, rpcpassword: str):
        self.id = id
        self.RPCARGS = [f"-rpcport={rpcport}", f"-rpcuser={rpcuser}", f"-rpcpassword={rpcpassword}"]

    def wsl_cli(self, *args, ignore: bool = False):
        quoted = [shlex.quote(a) for a in ["build/bin/bitcoin-cli", "-rpcwallet=mywallet"] + self.RPCARGS + list(args)]
        cmd = "wsl " + " ".join(quoted)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if ignore == False and result.returncode != 0:
            print(f"bitcoin-cli error (node 0): {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        return result

    def wsl_cli_raw(self, *args, ignore: bool = False):
        return self.wsl_cli(*args, ignore=ignore).stdout.strip()

    def wsl_cli_json(self, *args):
        return json.loads(self.wsl_cli(*args).stdout)

    def win_cli(self, *args, ignore: bool = False):
        cmd = ["bitcoin-cli"] + self.RPCARGS + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if ignore == False and result.returncode != 0:
            print(f"bitcoin-cli error (node {self.id}): {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        return result

    def win_cli_raw(self, *args, ignore: bool = False):
        return self.win_cli(*args, ignore=ignore).stdout.strip()

    def win_cli_json(self, *args):
        return json.loads(self.win_cli(*args).stdout)

nodes_cli = [
    BitcoinCli(0, 48347, "expuser0", "strongpassword0"),
    BitcoinCli(1, 48332, "expuser1", "strongpassword1"),
    BitcoinCli(2, 48335, "expuser2", "strongpassword2"),
    BitcoinCli(3, 48338, "expuser3", "strongpassword3"),
    BitcoinCli(4, 48341, "expuser4", "strongpassword4"),
    BitcoinCli(5, 48344, "expuser5", "strongpassword5"),
    BitcoinCli(6, 48350, "expuser6", "strongpassword6"),
]