from ..dataclasses.GroundTruthSnapshot import GroundTruthSnapshot
from ..dataclasses.INV_message import INV_message
from ..objects.node_instances import nodes_cli
from ..ui.progress_bar import wait_seconds_with_progressbar

def step_2_filter_no_invblock_nodes(graph: GroundTruthSnapshot) -> GroundTruthSnapshot:
    """Procedure to filter no-invblock nodes: nodes that we cannot apply INVBLOCK to block INV messages from other nodes."""
    try:
        inv: INV_message = nodes_cli[0].create_a_new_tx()
        nodes_cli[0].send_an_inv_to_all(inv)
        wait_seconds_with_progressbar(3, f"Node 0 sending INVBLOCK test")
        nodes_cli[6].send_an_inv_to_all(inv)
        wait_seconds_with_progressbar(3, f"Node 6 sending INVBLOCK test")
        eliminate_no_invblock_nodes(inv)
        wait_seconds_with_progressbar(1, f"Node 0 and 6 eliminating no-invblock peers")
        result: GroundTruthSnapshot = graph.eliminate_nodes_not_in_both_lists(
            nodes_cli[0].get_peer_list(block_relay_only = False, local_addr = False), 
            nodes_cli[6].get_peer_list(block_relay_only = False, local_addr = False)
        )
        return result
    except Exception as e:
        print(f"[!] Encounter error when filtering no-invblock nodes: {e}!")

def eliminate_no_invblock_nodes(inv):
    """Eliminate no-invblock nodes: nodes that we cannot apply INVBLOCK to block INV messages from other nodes."""
    try:
        nodes_cli[6].eliminate_cannot_invblock_nodes(inv)
        node_6_peer_list = nodes_cli[6].get_peer_list(block_relay_only = False, local_addr = False)
        nodes_cli[0].eliminate_nodes_not_in_list(node_6_peer_list)
    except:
        print(f"[!] Encounter error when eliminating no-invblock nodes!")