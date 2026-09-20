from decimal import Decimal

from ..dataclasses.GraphSnapshot import GraphSnapshot
from ..dataclasses.NodeIdentity import NodeIdentity
from ..objects.node_indices import groundtruth_nodes
from ..objects.node_instances import nodes_cli

def step_6_calculating_metrics(groundtruth: GraphSnapshot, inference: GraphSnapshot):
    try:
        # Debug
        print_graph_edges(groundtruth, f"Final groundtruth:\n")
        print_graph_edges(inference, f"Final inference:\n")

        # Main
        common_nodes: set[NodeIdentity] = set(groundtruth.nodes) & set(inference.nodes)

        groundtruth_node_list = [nodes_cli[id].get_identity() for id in groundtruth_nodes]
        source_set = set(groundtruth_node_list) & common_nodes
        sink_set = common_nodes - source_set

        edges = generate_edges(source_set, sink_set)

        groundtruth_edge_states = get_edge_states(groundtruth, edges)
        inference_edge_states = get_edge_states(inference, edges)

        precision, recall, accuracy = calculate_metrics(groundtruth_edge_states, inference_edge_states)
        print(
            f"RESULTS:\n"
            f"    Precision = {precision}\n"
            f"    Recall = {recall}\n"
            f"    Accuracy = {accuracy}\n"
        )
    except Exception as e:
        print(f"Step 6: Encounter an exception when calculating metrics {e}!\n")
        raise

def print_graph_edges(graph: GraphSnapshot, title: str) -> None:
    with open("txprobe_debug.log", "a") as f:
        f.write(title)
        for node in graph.adj_list:
            peer_list = graph.adj_list.get(node, ())
            for peer in peer_list:
                f.write(f"{node.addr} {peer.addr}\n")

def generate_edges(a: set[NodeIdentity], b: set[NodeIdentity]) -> list[tuple[NodeIdentity, NodeIdentity]]:
    try:
        result: list[tuple[NodeIdentity, NodeIdentity]] = []
        for node_1 in a:
            for node_2 in b:
                result.append((node_1, node_2))
        return result
    except Exception as e:
        print(f"Generate edges: Encounter an error {e}!\n")
        raise


def get_edge_states(graph: GraphSnapshot, edges: list[tuple[NodeIdentity, NodeIdentity]]) -> list[bool]:
    """Return the state of each edge/connection, True if that edge exists, False otherwise"""
    try:
        adj_list_set: dict[NodeIdentity, set[NodeIdentity]] = {
            node: set(peer_list)
            for node, peer_list in graph.adj_list.items()
        }
        result: list[bool] = []
        for u, v in edges:
            exists = v in adj_list_set.get(u, set())
            result.append(exists)
        return result
    except Exception as e:
        print(f"Get edge states: Encounter an error {e}!\n")
        raise

def calculate_metrics(groundtruth_states: list[bool], inference_states: list[bool]) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    try:
        if len(groundtruth_states) != len(inference_states):
            raise RuntimeError(str(f"calculate_metrics: the two state lists are not the same size."))
        
        n = len(groundtruth_states)
        if n == 0:
            return None, None, None

        tp, tn, fp, fn = 0, 0, 0, 0
        for gt, inf in zip(groundtruth_states, inference_states):
            if gt and inf:
                tp += 1
            elif not gt and not inf:
                tn += 1
            elif not gt and inf:
                fp += 1
            else:
                fn += 1
        precision = Decimal(tp) / Decimal(tp + fp) if (tp + fp) > 0 else None
        recall = Decimal(tp) / Decimal(tp + fn) if (tp + fn) > 0 else None
        accuracy = Decimal(tp + tn) / Decimal(n)
        return precision, recall, accuracy
    except Exception as e:
        print(f"Calculate metrics: Encounter an error {e}!\n")
        raise