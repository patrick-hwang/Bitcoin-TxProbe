import re
import time

from decimal import Decimal
from tqdm import tqdm

from .dataclasses.GroundTruthSnapshot import GroundTruthSnapshot
from .dataclasses.INV_message import INV_message
from .dataclasses.NodeIdentity import NodeIdentity
from .objects.node_indices import groundtruth_nodes, probe_nodes
from .objects.node_instances import nodes_cli
from .steps.step_1_capture_initial_groundtruth import step_1_capture_initial_groundtruth, add_groundtruth_addresses, add_peers_of_groundtruth_nodes, connect_probe_nodes, waiting_probe_nodes_to_connect, retrieve_adj_list, eliminate_not_probe_connected
from .steps.step_2_filter_no_invblock_nodes import step_2_filter_no_invblock_nodes, eliminate_no_invblock_nodes
from .ui.progress_bar import wait_seconds_with_progressbar

initial_graph: GroundTruthSnapshot = step_1_capture_initial_groundtruth()
with open("txprobe_debug.log", "w") as f:
    f.write(f"Done initial graph snapshot.\n")
    f.write(f"{len(initial_graph.nodes)} nodes retrieved. Here is the snapshot:\n")
    for node in initial_graph.nodes:
        f.write(f"Node {node.addr}:\n")
        peers = initial_graph.adj_list.get(node)
        if peers is None:
            continue
        for peer in peers:
            f.write(f"    {peer.addr}\n")

inv: INV_message = nodes_cli[0].create_a_new_tx()
with open("txprobe_debug.log", "a") as f:
    f.write(
        f"Created an INV message:\n"
        f"    hex: {inv.hexstr},\n"
        f"    txid: {inv.txid},\n"
        f"    wtxid: {inv.wtxid},\n"
    )

nodes_cli[0].send_an_inv_to_all(inv)
wait_seconds_with_progressbar(3, f"Node 0 sending INVBLOCK test")

nodes_cli[6].send_an_inv_to_all(inv)
wait_seconds_with_progressbar(3, f"Node 6 sending INVBLOCK test")

with open("txprobe_debug.log", "a") as f:
    for index in probe_nodes:
        f.write(f"Node {index}'s peers BEFORE eliminating:\n")
        peers = nodes_cli[index].get_peer_list()
        for peer in peers:
            f.write(f"    {peer.addr},\n")
        

eliminate_no_invblock_nodes(inv)
wait_seconds_with_progressbar(1, f"Node 0 and 6 eliminating no-invblock peers")

with open("txprobe_debug.log", "a") as f:
    for index in probe_nodes:
        f.write(f"Node {index}'s peers AFTER eliminating:\n")
        peers = nodes_cli[index].get_peer_list()
        for peer in peers:
            f.write(f"    {peer.addr},\n")

    f.write(f"Node list BEFORE eliminating:\n")
    for node in initial_graph.nodes:
        f.write(f"    {node.addr},\n")

result: GroundTruthSnapshot = initial_graph.eliminate_nodes_not_in_both_lists(
    nodes_cli[0].get_peer_list(block_relay_only = False, local_addr = False), 
    nodes_cli[6].get_peer_list(block_relay_only = False, local_addr = False)
)

with open("txprobe_debug.log", "a") as f:
    f.write(f"Node list AFTER eliminating:\n")
    for node in result.nodes:
        f.write(f"    {node.addr},\n")

# INVBLOCK_graph: GroundTruthSnapshot = step_2_filter_no_invblock_nodes(initial_graph)
# with open("txprobe_debug.log", "a") as f:
#     f.write(f"Done INVBLOCK graph snapshot.\n")
#     f.write(f"{len(INVBLOCK_graph.nodes)} nodes retrieved. Here is the snapshot:\n")
#     for node in INVBLOCK_graph.nodes:
#         f.write(f"Node {node.addr}:\n")
#         peers = INVBLOCK_graph.adj_list[node]
#         for peer in peers:
#             f.write(f"    {peer.addr}\n")