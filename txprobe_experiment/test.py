from decimal import Decimal

from .dataclasses.GroundTruthSnapshot import GroundTruthSnapshot
from .dataclasses.INV_message import INV_message
from .dataclasses.NodeIdentity import NodeIdentity
from .nodes import groundtruth_nodes, probe_nodes, nodes_cli
from .steps.step_1_capture_initial_groundtruth import step_1_capture_initial_groundtruth, add_groundtruth_addresses, add_peers_of_groundtruth_nodes, connect_probe_nodes, waiting_probe_nodes_to_connect, retrieve_adj_list, eliminate_not_probe_connected

# snapshot: GroundTruthSnapshot = step_1_capture_initial_groundtruth()
# print(f"{len(snapshot.nodes)} nodes retrieved. Here is the adjacent list:")
# for node in snapshot.nodes:
#     print(f"Node {node.addr}: {snapshot.adj_list[node]}")

inv: INV_message = nodes_cli[0].create_a_new_tx()
print(inv)