from dataclasses import dataclass

@dataclass(frozen=True)
class TX_message:
    """INV message object"""
    hexstr: str
    txid: str
    wtxid: str