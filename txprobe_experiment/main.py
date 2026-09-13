import json
import sys

from .groundtruth import GroundTruthError, retrieve_phase1_groundtruth
from .classes.BitcoinCli.BitcoinCli import BitcoinCliError
from .phase2_inv_block_filter import Phase2Error, no_invblock_filter
from .phase3_crafting_transactions import crafting_txprobe_transactions

from .steps import step_1_capture_initial_groundtruth

def main():
    step_1_capture_initial_groundtruth()
    # 1. Parse arguments
    # debug = '--debug' in sys.argv

    # if '--validation-test' in sys.argv:
    #     try:
    #         snapshot = retrieve_phase1_groundtruth()
    #         no_invblock_result = no_invblock_filter(snapshot, debug = debug)
    #         # tx_probecommands = crafting_txprobe_transactions(no_invblock_result.snapshot, debug = debug)
    #     except (GroundTruthError, Phase2Error, BitcoinCliError) as error:
    #         print(f"Validation test error: {error}", file=sys.stderr)
    #         raise SystemExit(1)
    #     print(json.dumps(no_invblock_result.as_dict(), indent=2))
    #     return
    
if __name__ == "__main__":
    main()
