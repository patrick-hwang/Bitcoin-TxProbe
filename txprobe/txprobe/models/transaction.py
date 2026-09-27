"""Transaction message data model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TxMessage:
    """A signed transaction not yet broadcast."""
    hexstr: str
    txid: str
    wtxid: str
