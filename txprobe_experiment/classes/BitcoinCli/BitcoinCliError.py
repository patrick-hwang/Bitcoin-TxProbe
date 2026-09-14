class BitcoinCliError(RuntimeError):
    """BitcoinCliError cannot proceed as the specification requires."""
    def __init__(self, node_id, code, message, raw_stderr):
        self.node_id = node_id
        self.code = code
        self.message = message
        self.raw_stderr = raw_stderr
        super().__init__(f"bitcoin-cli error (node {node_id}: {raw_stderr})")

class BitcoinCliNoWallet(Exception):
    """BitcoinCliNoWallet did not specified what wallet to use"""