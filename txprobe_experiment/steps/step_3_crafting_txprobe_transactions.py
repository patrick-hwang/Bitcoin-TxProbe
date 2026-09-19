from ..dataclasses.TX_message import TX_message
from ..objects.node_instances import nodes_cli

def step_3_crafting_txprobe_transactions(
        num_vertices: int    
    ) -> tuple[
        list[TX_message], TX_message, list[TX_message]
    ]:
    if num_vertices < 2:
        raise RuntimeError(f"Step 3: Only {num_vertices} vertex. Too few vertices!")
    *parent_transaction_list, flooding_trasaction = nodes_cli[0].create_many_new_txs(num_vertices)
    marker_transaction_list = nodes_cli[0].create_child_transactions(parent_transaction_list)
    return parent_transaction_list, flooding_trasaction, marker_transaction_list