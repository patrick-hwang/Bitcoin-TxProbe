import json
import re
import time

from decimal import Decimal
from tqdm import tqdm

from .dataclasses.GraphSnapshot import GraphSnapshot
from .dataclasses.TX_message import TX_message
from .dataclasses.NodeIdentity import NodeIdentity
from .objects.node_indices import groundtruth_nodes, probe_nodes
from .objects.node_instances import nodes_cli
from .steps.step_1_capture_initial_groundtruth import step_1_capture_initial_groundtruth, add_groundtruth_addresses, add_peers_of_groundtruth_nodes, connect_probe_nodes, waiting_probe_nodes_to_connect, retrieve_adj_list, eliminate_not_probe_connected
from .steps.step_2_filter_no_invblock_nodes import step_2_filter_no_invblock_nodes, eliminate_no_invblock_nodes
from .steps.step_3_crafting_txprobe_transactions import step_3_crafting_txprobe_transactions
from .steps.step_4_txprobe import step_4_txprobe, extract_source_and_sink, send_txprobe_transactions, invblock, send_flooding_transaction, send_transaction_in_order, request_markers_back, infer_topology
from .ui.progress_bar import wait_seconds_with_progressbar

initial_graph = step_1_capture_initial_groundtruth()
with open("txprobe_debug.log", "w") as f:
    f.write(f"Step 1: Done initial graph snapshot.\n")
    f.write(f"{len(initial_graph.nodes)} nodes retrieved. Here is the snapshot:\n")
    for node in initial_graph.nodes:
        f.write(f"Node {node.addr}:\n")
        peers = initial_graph.adj_list.get(node)
        if peers is None:
            continue
        for peer in peers:
            f.write(f"    {peer.addr},\n")

INVBLOCK_graph = step_2_filter_no_invblock_nodes(initial_graph)
with open("txprobe_debug.log", "a") as f:
    f.write(f"\nStep 2: Done INVBLOCK graph snapshot.\n")
    f.write(f"{len(INVBLOCK_graph.nodes)} nodes retrieved. Here is the snapshot:\n")
    for node in INVBLOCK_graph.nodes:
        f.write(f"Node {node.addr}:\n")
        peers = INVBLOCK_graph.adj_list[node]
        for peer in peers:
            f.write(f"    {peer.addr}\n")

parent_tx_list, flooding_tx, marker_tx_list = step_3_crafting_txprobe_transactions(INVBLOCK_graph.nodes)
with open("txprobe_debug.log", "a") as f:
    f.write(f"\nStep 3: Crafted TxProbe transactions.\n")
    f.write(f"{len(parent_tx_list)} parent transactions crafted:\n")
    for tx in parent_tx_list:
        f.write(f"    hex: {tx.hexstr}\n")
        f.write(f"    txid: {tx.txid}\n")
        f.write(f"    wtxid: {tx.wtxid}\n")
    f.write(
        f"Flooding transaction:\n"
        f"    hex: {flooding_tx.hexstr}\n"
        f"    txid: {flooding_tx.txid}\n"
        f"    wtxid: {flooding_tx.wtxid}\n"
    )
    f.write(f"{len(marker_tx_list)} marker transactions crafted:\n")
    for tx in marker_tx_list:
        f.write(f"    hex: {tx.hexstr}\n")
        f.write(f"    txid: {tx.txid}\n")
        f.write(f"    wtxid: {tx.wtxid}\n")

inferred_graph, groundtruth_nodes_order = step_4_txprobe(list(INVBLOCK_graph.nodes), parent_tx_list, flooding_tx, marker_tx_list)
with open("txprobe_debug.log", "a") as f:
    f.write(f"\nStep 4: The inferred topology:\n")
    for node in inferred_graph.nodes:
        f.write(f"Node {node.addr}'s adjacent list:\n")
        peers = inferred_graph.adj_list[node]
        for peer in peers:
            f.write(f"    {peer.addr}\n")