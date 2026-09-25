from dataclasses import dataclass

@dataclass(frozen=True)
class NodeIdentity:
    """Identity of a node
    """
    addr: str