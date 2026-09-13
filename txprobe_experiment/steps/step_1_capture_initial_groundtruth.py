import time

from collections.abc import Mapping
from tqdm import tqdm
from types import MappingProxyType

from ..dataclasses.GroundTruthSnapshot import GroundTruthSnapshot, NodeIdentity
from ..nodes import groundtruth_nodes, probe_nodes, nodes_cli, groundtruth_dict_identity_into_index

def step_1_capture_initial_groundtruth() -> GroundTruthSnapshot:
    """Collect the initial ground-truth snapshot."""
    nodes_raw: set[NodeIdentity] = set()
    adj_list_raw: dict[NodeIdentity, set[NodeIdentity]] = {}

    try:
        add_groundtruth_addresses(nodes_raw)
        add_peers_of_groundtruth_nodes(nodes_raw)
        connect_probe_nodes(nodes_raw)
        waiting_probe_nodes_to_connect(nodes_raw)
        retrieve_adj_list(nodes_raw, adj_list_raw)
        eliminate_not_probe_connected(nodes_raw, adj_list_raw)
        return GroundTruthSnapshot(
            nodes = tuple(nodes_raw),
            adj_list = MappingProxyType({
                node_id: tuple(neighbors)
                for node_id, neighbors in adj_list_raw.items()
            })
        )
    except Exception as e:
        print(f"Encounter exception when capturing initial groundtruth: {e}")


def add_groundtruth_addresses(nodes: set[NodeIdentity]):
    """Add onion addresses of the groundtruth nodes (1,2,3,4,5)"""
    for node_index in groundtruth_nodes:
        new_identity = nodes_cli[node_index].get_identity()
        nodes.add(new_identity)
        groundtruth_dict_identity_into_index[new_identity] = node_index

def add_peers_of_groundtruth_nodes(nodes: set[NodeIdentity]):
    """Add peers of nodes in a specified list, considering IPv4 and tor connections only"""
    for index in groundtruth_nodes:
        if nodes_cli[index].get_identity() not in nodes:
            continue
        node_peers = nodes_cli[index].get_peer_list()
        for peer in node_peers:
            nodes.add(peer)

def connect_probe_nodes(collected_nodes: set[NodeIdentity]):
    """Connect probe nodes (0,6) to the collected nodes"""
    for probe_index in probe_nodes:
        current_peer_addresses = nodes_cli[probe_index].get_peer_list()
        for node in collected_nodes:
            if node not in current_peer_addresses:
                try:
                    nodes_cli[probe_index].cli_raw("addnode", node.addr, "add")
                except Exception as e:
                    print(f"Encounter an exception when add nodes to probe node {probe_index}: {e}")
        for node in current_peer_addresses:
            if node not in collected_nodes:
                nodes_cli[probe_index].cli_raw("disconnectnode", node.addr)

def waiting_probe_nodes_to_connect(collected_nodes: set[NodeIdentity]):
    """Wait 3 seconds for each collected nodes"""
    elapse_timer = 0
    wait_seconds = 2
    total_nodes = len(collected_nodes)
    seconds_per_node = 3
    num_mini_period = 1
    mini_break_period = total_nodes * seconds_per_node / num_mini_period
    timeout_seconds = total_nodes * seconds_per_node

    with tqdm(total=timeout_seconds, desc="Connecting peers") as pbar:
        while (elapse_timer < timeout_seconds):
            done = True
            status = {}

            for node_index in probe_nodes:
                peer_list = nodes_cli[node_index].get_peer_list()
                connected_peers = [peer for peer in peer_list if peer in collected_nodes]
                status[f"Node_{node_index}"] = f"{len(connected_peers)}/{total_nodes}"

                if len(connected_peers) < total_nodes:
                    done = False

            pbar.set_postfix_str(status)

            if elapse_timer >= mini_break_period:
                pbar.clear()
                inp = input(f"Waited for {mini_break_period} seconds. Do you want to halt? (type \'h\'): ")
                pbar.refresh()
                if inp.lower().startswith('h'):
                    done = True
                else:
                    mini_break_period += total_nodes * seconds_per_node / num_mini_period

            if done:
                pbar.set_postfix_str(f"Halt after {elapse_timer} seconds.")
                break

            time.sleep(wait_seconds)
            pbar.update(wait_seconds)
            elapse_timer += wait_seconds

def retrieve_adj_list(nodes: set[NodeIdentity], adj_list: dict[NodeIdentity, set[NodeIdentity]]):
    """Retrieve adjacent peers of each node in the node list."""
    try:
        for index in groundtruth_nodes:
            node_identity = nodes_cli[index].get_identity()
            if node_identity not in nodes:
                continue
            peer_list = nodes_cli[index].get_peer_list()
            for peer_identity in peer_list:
                if peer_identity not in nodes:
                    continue
                adj_list.setdefault(node_identity, set()).add(peer_identity)
                adj_list.setdefault(peer_identity, set()).add(node_identity)
    except Exception as e:
        print(f"Encounter exception when retrieve raw adjacent list: {e}")

def eliminate_not_probe_connected(nodes: set[NodeIdentity], adj_list: dict[NodeIdentity, set[NodeIdentity]]):
    """Eliminate nodes that cannot be connected by both of probe nodes."""
    peer_of_0: list[NodeIdentity] = nodes_cli[0].get_peer_list()
    peer_of_6: list[NodeIdentity] = nodes_cli[6].get_peer_list()

    nodes_to_remove: set[NodeIdentity] = set()
    for node in nodes:
        if not(node in peer_of_0 and node in peer_of_6):
            nodes_to_remove.add(node)
            adj_nodes = adj_list.pop(node, None)
            for adj_node in adj_nodes:
                if adj_node in adj_list:
                    adj_list[adj_node].discard(node)
            nodes_cli[0].cli_raw("addnode", node.addr, "remove", ignore=True)
            nodes_cli[6].cli_raw("addnode", node.addr, "remove", ignore=True)

    nodes.difference_update(nodes_to_remove)