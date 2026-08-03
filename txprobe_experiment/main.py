import sys

from .node0_manager import node0Manager
from .topology import Topology
from .rounds import generate_rounds, preparing_commands_for_a_round
from .metrics import aggregate_metrics
from .ui import ProgressUI

def main():
    # 1. Parse arguments
    debug = '--debug' in sys.argv
    runs = 1
    if '--runs' in sys.argv:
        idx = sys.argv.index('--runs')
        runs = int(sys.argv[idx + 1])

    # 2. Set up node 0
    vertices = node0Manager.get_peerids_from_node0(debug)

    ui = ProgressUI()
    ui.start()
    ui.start_experiment(runs)

    all_metrics = []
    try:
        for run_idx in range(runs):
            ui.start_run(run_idx + 1, runs)

            topo = Topology(vertices)
            topo.create_groundtruth(debug, ui)
            ui.update_matrices(topo.groundtruth, topo.inference)

            rounds = generate_rounds(vertices)
            round_infos = [preparing_commands_for_a_round(s, k, debug) for s, k in rounds]
            topo.execute_topology_infer(round_infos, debug, ui)

            metrics = topo.inference_result()
            all_metrics.append(metrics)
            ui.finalize_run(metrics)
            ui.countdown('Wait for the transactions to be verified in the blockchain... 5 minutes', 300)
    except Exception:
        ui.stop()
        raise

    ui.stop()

    if runs == 1:
        print(all_metrics[0])
    else:
        avg = aggregate_metrics(all_metrics)
        print(avg)


if __name__ == "__main__":
    main()