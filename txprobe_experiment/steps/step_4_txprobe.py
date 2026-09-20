from collections import defaultdict
from types import MappingProxyType

from ..dataclasses.GraphSnapshot import GraphSnapshot
from ..dataclasses.NodeIdentity import NodeIdentity
from ..dataclasses.TX_message import TX_message
from ..objects.node_indices import groundtruth_nodes
from ..objects.node_instances import nodes_cli
from ..ui.progress_bar import wait_seconds_with_progressbar

def step_4_txprobe(
    groundtruth_graph: GraphSnapshot,
    parent_tx_list: list[TX_message],
    flooding_tx: TX_message,
    marker_tx_list: list[TX_message]
) -> tuple[GraphSnapshot, list[int], GraphSnapshot]:
    """Perform the TxProbe technique to infer the topology.
        There are two outputs:
            - The inferred topology of the network
            - The order of groundtruth nodes in which the marker transactions was sent: order[i] = the id of the groundtruth nodes who the mtx number i was sent to
    """
    A_FEW_SECONDS = 2
    try:
        source_set, sink_set = extract_source_and_sink(list(groundtruth_graph.nodes))
        if len(set(source_set) & set(sink_set)) > 0:
            raise RuntimeError("[!] There is a node in both source set and sink set!")
        
        source_set_id_list = nodes_cli[0].get_peer_id_from_node_list(source_set)

        send_txprobe_transactions(source_set_id_list, sink_set, parent_tx_list, flooding_tx, marker_tx_list)
        wait_seconds_with_progressbar(A_FEW_SECONDS, "Wait a few seconds after sending transactions", 0.5)

        new_groundtruth_snapshot = filter_nodes_received_wrong_txs(
            groundtruth_graph, 
            source_set_id_list, 
            parent_tx_list, flooding_tx, marker_tx_list)

        marker_ids_requested_by_each_sink_node = request_markers_back(sink_set, marker_tx_list)

        result = infer_topology(sink_set, source_set, source_set_id_list, marker_ids_requested_by_each_sink_node), source_set_id_list
        nodes_cli[0].cli_raw("clearinv_probe", ignore = True)

        return result, source_set_id_list, new_groundtruth_snapshot
    except Exception as e:
        print(f"step_4_txprobe: Encountered an exception when performing TxProbe: {e}")

def extract_source_and_sink(graph_nodes: list[NodeIdentity]) -> tuple[list[NodeIdentity], list[NodeIdentity]]:
    groundtruth_identities = [nodes_cli[index].get_identity() for index in groundtruth_nodes]
    source_set = [node for node in groundtruth_identities if node in graph_nodes]
    sink_set = [node for node in graph_nodes if node not in source_set]
    return source_set, sink_set

def send_txprobe_transactions(
    source_set_id_list: list[int],
    sink_set: list[NodeIdentity],
    parent_tx_list: list[TX_message],
    flooding_tx: TX_message,
    marker_tx_list: list[TX_message]
) -> None:
    """Perform the sending TxProbe transactions steps."""
    WAITING_FOR_INVBLOCK_TIME = 5
    WAITING_FOR_FLOODING_TX_TIME = 1
    WAITING_FOR_PARENT_TX_TIME = 5
    try:
        invblock([*parent_tx_list, flooding_tx])
        wait_seconds_with_progressbar(WAITING_FOR_INVBLOCK_TIME, f"Waiting {WAITING_FOR_INVBLOCK_TIME} seconds for INVBLOCK", 0.5)
        send_flooding_transaction(sink_set, flooding_tx)
        wait_seconds_with_progressbar(WAITING_FOR_FLOODING_TX_TIME, f"Waiting {WAITING_FOR_FLOODING_TX_TIME} seconds for sending flooding tx", 0.1)
        send_transaction_in_order(parent_tx_list, source_set_id_list)
        wait_seconds_with_progressbar(WAITING_FOR_PARENT_TX_TIME, f"Waiting {WAITING_FOR_PARENT_TX_TIME} seconds for sending parent txs", 0.5)
        nodes_cli[0].cli_raw("clearinv_probe", ignore = True)
        send_transaction_in_order(marker_tx_list, source_set_id_list)
    except Exception as e:
        print(f"step_4_txprobe::send_txprobe_transactions: Encountered an exception: {e}")

def invblock(txs: list[TX_message]) -> None:
    for tx in txs:
        nodes_cli[0].send_an_inv_to_all(tx)

def send_flooding_transaction(sink_set: list[NodeIdentity], flooding_tx: TX_message) -> None:
    id_list = nodes_cli[0].get_peer_id_from_node_list(sink_set)
    nodes_cli[0].send_txs_to([flooding_tx], id_list)

def send_transaction_in_order(tx_list: list[TX_message], id_list: list[int]) -> None:
    """Send transaction in specified order, i.e.,
        tx_list[i] to id_list[i] for all i from 0..len(tx_list)
    """
    if len(tx_list) != len(id_list):
        raise RuntimeError("step_4_txprobe:send_transaction_in_order: the length of tx_list does not match id_list")
    for i in range(len(tx_list)):
        nodes_cli[0].send_txs_to([tx_list[i]], [id_list[i]])

def filter_nodes_received_wrong_txs(
        old_graph: GraphSnapshot,
        groundtruth_nodes_sending_order: list[int],
        parent_tx_list: list[TX_message],
        flooding_tx: TX_message,
        marker_tx_list: list[TX_message]
) -> GraphSnapshot:
    try:
        malfunction_node_list: list[NodeIdentity] = list()
        for index in groundtruth_nodes:
            node = nodes_cli[index].get_identity()
            if node in old_graph.nodes:
                received_tx_list = nodes_cli[index].get_mempool_txids()
                properly_function: bool = (flooding_tx.txid not in received_tx_list)
                for i in range(len(parent_tx_list)):
                    if groundtruth_nodes_sending_order[i] == index:
                        properly_function &= (parent_tx_list[i].txid in received_tx_list)
                        properly_function &= (marker_tx_list[i].txid in received_tx_list)
                    else:
                        properly_function &= (parent_tx_list[i].txid not in received_tx_list)
                if not properly_function:
                    malfunction_node_list.append(node)

        new_nodes = {node for node in old_graph.nodes if node not in malfunction_node_list}
        new_adj_list: dict[NodeIdentity, set[NodeIdentity]] = defaultdict(set)
        for node in new_nodes:
            old_peers = old_graph.adj_list.get(node, tuple())
            new_peers = {peer for peer in old_peers if peer not in malfunction_node_list}
            new_adj_list[node].update(new_peers)
            for peer in new_peers:
                new_adj_list[peer].add(node)
        
        return GraphSnapshot(
            nodes = tuple(new_nodes),
            adj_list = MappingProxyType({
                node: tuple(peer_list)
                for node, peer_list in new_adj_list.items()
            })
        )
    except Exception as e:
        print(f"Filter nodes received wrong transactions: Encounter an error {e}")
        raise

def request_markers_back(
        sink_set: list[NodeIdentity], 
        marker_tx_list: list[TX_message]
) -> dict[NodeIdentity, list[int]]:
    """Infer the topology"""
    WAITING_FOR_GETDATA_MESSAGES = 5

    nodes_cli[0].clear_log_file() # Erase old records
    invblock(marker_tx_list) # Sending all the marker inventories to all peers
    wait_seconds_with_progressbar(WAITING_FOR_GETDATA_MESSAGES, "Waiting for getdata message about marker transactions.", 0.25)
    return collect_peer_request(sink_set, marker_tx_list)

def collect_peer_request(
        peer_list: list[NodeIdentity], tx_list: list[TX_message]
    ) -> dict[NodeIdentity, list[int]]:
    """For each peer, record the transactions in the specified list and also requested by that peer"""
    try:
        result = {peer: list() for peer in peer_list}
        requests: dict[str, set[int]] = nodes_cli[0].retrieve_getdata_requests()
        for i in range(len(tx_list)):
            tx = tx_list[i]
            peer_requested_id_list: list[int] = requests.get(tx.txid, set()) | requests.get(tx.wtxid, set())
            for id in peer_requested_id_list:
                peer = nodes_cli[0].get_peer_identity(id, ignore=True)
                if peer and peer in result:
                    result[peer].append(i)
        return result
    except Exception as e:
        raise RuntimeError(f"collect_peer_request: Encountered an exception: {e}")

def infer_topology(
    source_set: list[NodeIdentity],
    sink_set: list[NodeIdentity],
    source_set_id_list: list[int],
    marker_requests_by_each_sink_node: dict[NodeIdentity, list[int]]
) -> GraphSnapshot:
    try:
        nodes = list(set(source_set) | set(sink_set))
        adj_list: dict[NodeIdentity, set[NodeIdentity]] = { node: set() for node in nodes }
        for source_node in source_set:
            for sink_node in sink_set:
                adj_list[source_node].add(sink_node)
                adj_list[sink_node].add(source_node)
        for sink_node, mtx_ids in marker_requests_by_each_sink_node.items():
            for id in mtx_ids:
                source_node = nodes_cli[0].get_peer_identity(source_set_id_list[id], ignore = True)
                if not source_node:
                    with open("txprobe_debug.log", "a") as f:
                        f.write(f"[!] Warning: cannot get_peer_identity for a source node with id = {source_set_id_list[id]}\n")
                    continue
                adj_list[sink_node].discard(source_node)
                adj_list[source_node].discard(sink_node)
        return GraphSnapshot(
            nodes = tuple(nodes),
            adj_list = MappingProxyType({
                node: tuple(peers)
                for node, peers in adj_list.items()
            })
        )
    except Exception as e:
        print(f"infer_topology: encounter an exception {e}")
        raise