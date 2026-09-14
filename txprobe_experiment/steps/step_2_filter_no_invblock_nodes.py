import time
from ..dataclasses.GroundTruthSnapshot import GroundTruthSnapshot
from ..dataclasses.INV_message import INV_message
from ..nodes import nodes_cli

def step_2_filter_no_invblock_nodes(graph: GroundTruthSnapshot) -> GroundTruthSnapshot:
    """Procedure to filter no-invblock nodes: nodes that we cannot apply INVBLOCK to block INV messages from other nodes."""
    try:
        inv: INV_message = nodes_cli[0].create_a_new_tx()
        nodes_cli[0].send_an_inv_to_all(inv)
        time.sleep(3)
        nodes_cli[6].send_an_inv_to_all(inv)
        time.sleep(3)
        eliminate_no_invblock_nodes(inv)
        result: GroundTruthSnapshot = graph.keep_nodes_in_both_list(nodes_cli[0].get_peer_list(), nodes_cli[6].get_peer_list())
        return result
    except Exception as e:
        print(f"[!] Encounter error when filtering no-invblock nodes!")

def eliminate_no_invblock_nodes(inv):
    """Eliminate no-invblock nodes: nodes that we cannot apply INVBLOCK to block INV messages from other nodes."""
    try:
        nodes_cli[6].eliminate_cannot_invblock_nodes(inv)
        node_6_peer_list = nodes_cli[6].get_peer_list()
        nodes_cli[0].keep_nodes_in_list(node_6_peer_list)
    except:
        print(f"[!] Encounter error when eliminating no-invblock nodes!")