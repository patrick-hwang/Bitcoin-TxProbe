import json
import sys

from .dataclasses.GroundTruthSnapshot import GroundTruthSnapshot
from .objects.node_indices import groundtruth_nodes

from .steps.step_1_capture_initial_groundtruth import step_1_capture_initial_groundtruth
from .steps.step_2_filter_no_invblock_nodes import step_2_filter_no_invblock_nodes
from .steps.step_3_crafting_txprobe_transactions import step_3_crafting_txprobe_transactions

def main():
    initial_graph: GroundTruthSnapshot = step_1_capture_initial_groundtruth()
    INVBLOCK_graph: GroundTruthSnapshot = step_2_filter_no_invblock_nodes(initial_graph)
    parent_tx_list, flooding_tx, marker_tx_list = step_3_crafting_txprobe_transactions(len(groundtruth_nodes))
    # step_4_TxProbe
    ### INVBLOCK(paretn_tx_list, flooding_tx)
    ### send_flooding_transaction(flooding_tx)
    ### wait(4 seconds)
    ### send_parent_transactions(parent_tx_list)
    ### wait(5 seconds)
    ### send_marker_transactions(marker_tx_list)
    # step_5_filter_malfunction_nodes
    # step_6_calculating_metrics
    
if __name__ == "__main__":
    main()
