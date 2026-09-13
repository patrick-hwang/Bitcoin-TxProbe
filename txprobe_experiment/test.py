from .dataclasses.GroundTruthSnapshot import GroundTruthSnapshot
from .dataclasses.NodeIdentity import NodeIdentity
from .nodes import groundtruth_nodes, probe_nodes, nodes_cli
from .steps.step_1_capture_initial_groundtruth import step_1_capture_initial_groundtruth, add_groundtruth_addresses, add_peers_of_groundtruth_nodes, connect_probe_nodes, waiting_probe_nodes_to_connect, retrieve_adj_list, eliminate_not_probe_connected

# for node in groundtruth_nodes:
#     addresses = [peer.addr for peer in nodes_cli[node].get_peer_list()]
#     print(f"Node {node}: {addresses}")

snapshot: GroundTruthSnapshot = step_1_capture_initial_groundtruth()
print(f"{len(snapshot.nodes)} nodes retrieved. Here is the adjacent list:")
for node in snapshot.nodes:
    print(f"Node {node.addr}: {snapshot.adj_list[node]}")