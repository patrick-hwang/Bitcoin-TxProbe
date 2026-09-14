from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from .NodeIdentity import NodeIdentity

@dataclass(frozen=True)
class GroundTruthSnapshot:
    """The snapshot of the groundtruth"""

    nodes: tuple[NodeIdentity, ...]
    adj_list: Mapping[NodeIdentity, tuple[NodeIdentity, ...]]