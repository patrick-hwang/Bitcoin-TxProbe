import json
import sys

from .classes.BitcoinCli.BitcoinCli import BitcoinCliError
from .dataclasses.GroundTruthSnapshot import GroundTruthSnapshot

from .steps.step_1_capture_initial_groundtruth import step_1_capture_initial_groundtruth
from .steps.step_2_filter_no_invblock_nodes import step_2_filter_no_invblock_nodes

def main():
    initial_graph: GroundTruthSnapshot = step_1_capture_initial_groundtruth()
    INVBLOCK_graph: GroundTruthSnapshot = step_2_filter_no_invblock_nodes(initial_graph)
    # 1. Parse arguments
    # debug = '--debug' in sys.argv

    # if '--validation-test' in sys.argv:
    #     try:
    #         no_invblock_result = no_invblock_filter(snapshot, debug = debug)
    #         # tx_probecommands = crafting_txprobe_transactions(no_invblock_result.snapshot, debug = debug)
    #     except (GroundTruthError, Phase2Error, BitcoinCliError) as error:
    #         print(f"Validation test error: {error}", file=sys.stderr)
    #         raise SystemExit(1)
    #     print(json.dumps(no_invblock_result.as_dict(), indent=2))
    #     return
    
if __name__ == "__main__":
    main()
