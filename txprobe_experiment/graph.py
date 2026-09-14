from types import MappingProxyType
from .dataclasses.GroundTruthSnapshot import GroundTruthSnapshot

graph: GroundTruthSnapshot = GroundTruthSnapshot(
    nodes = (),
    adj_list = MappingProxyType({})
)