from dataclasses import dataclass

@dataclass(frozen=True)
class INV_message:
    """INV message object"""
    hexstr: str
    txid: str
    wtxid: str