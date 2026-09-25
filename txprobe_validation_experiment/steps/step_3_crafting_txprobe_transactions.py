from ..dataclasses.NodeIdentity import NodeIdentity
from ..dataclasses.TX_message import TX_message
from ..objects.node_indices import groundtruth_nodes
from ..objects.node_instances import nodes_cli

def step_3_crafting_txprobe_transactions(
        nodes: list[NodeIdentity]
    ) -> tuple[
        list[TX_message], TX_message, list[TX_message]
    ]:
    source_nodes = extract_source_nodes(nodes)
    num_vertices = len(source_nodes)
    if num_vertices == 0:
        raise RuntimeError(str(f"Step 3: There is no source node in the source set.\n"))
    *parent_transaction_list, flooding_trasaction = nodes_cli[0].create_many_new_txs(num_vertices + 1)
    marker_transaction_list = nodes_cli[0].create_child_transactions(parent_transaction_list)
    return parent_transaction_list, flooding_trasaction, marker_transaction_list

def extract_source_nodes(nodes: list[NodeIdentity]) -> list[NodeIdentity]:
    groundtruth_identities = [nodes_cli[index].get_identity() for index in groundtruth_nodes]
    result = [node for node in groundtruth_identities if node in nodes]
    return result