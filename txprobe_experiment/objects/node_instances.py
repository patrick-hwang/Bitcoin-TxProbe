from ..classes.BitcoinCli.BitcoinCli import BitcoinCli

nodes_cli: list[BitcoinCli] = [
    BitcoinCli(0, 48347, "expuser0", "strongpassword0", wsl = True, wallet_name = "mywallet"),
    BitcoinCli(1, 48332, "expuser1", "strongpassword1", wsl = False),
    BitcoinCli(2, 48335, "expuser2", "strongpassword2", wsl = False),
    BitcoinCli(3, 48338, "expuser3", "strongpassword3", wsl = False),
    BitcoinCli(4, 48341, "expuser4", "strongpassword4", wsl = False),
    BitcoinCli(5, 48344, "expuser5", "strongpassword5", wsl = False),
    BitcoinCli(6, 48350, "expuser6", "strongpassword6", wsl = True),
]