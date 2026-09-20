import json
import sys

from .dataclasses.GraphSnapshot import GraphSnapshot
from .objects.node_indices import groundtruth_nodes

from .steps.step_1_capture_initial_groundtruth import step_1_capture_initial_groundtruth
from .steps.step_2_filter_no_invblock_nodes import step_2_filter_no_invblock_nodes
from .steps.step_3_crafting_txprobe_transactions import step_3_crafting_txprobe_transactions
from .steps.step_4_txprobe import step_4_txprobe
from .steps.step_5_filter_malfunction_nodes import step_5_filter_malfunction_nodes


def main():
    initial_graph = step_1_capture_initial_groundtruth()
    INVBLOCK_graph = step_2_filter_no_invblock_nodes(initial_graph)
    parent_tx_list, flooding_tx, marker_tx_list = step_3_crafting_txprobe_transactions(INVBLOCK_graph.nodes)
    inferred_graph, node_received_mtx, filtered_groundtruth_graph = step_4_txprobe(INVBLOCK_graph, parent_tx_list, flooding_tx, marker_tx_list)
    filtered_groundtruth_graph = step_5_filter_malfunction_nodes(filtered_groundtruth_graph, node_received_mtx, marker_tx_list)
    step_6_calculating_metrics()
    
if __name__ == "__main__":
    main()
