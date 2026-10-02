# Master Pipeline Plan: End-to-End TxProbe Automation

**Date**: 2026-10-02 08:45  
**Target Milestone**: Master Pipeline Runner (Steps 0–6)

---

## 1. Goal
Provide a unified CLI orchestrator (`run_pipeline.py`) that executes the entire TxProbe workflow (Steps 0 through 6) seamlessly with one command:
```bash
python scripts/run_pipeline.py --config config/testnet4.yaml
```

Key features:
- Automatically creates a timestamped run directory: `results/run_YYYYMMDD_HHMMSS/`.
- Pipes data smoothly between Steps 0 -> 6:
  - Step 0 Phase 1: `harvest.json`
  - Step 0 Phase 2: `discovered_nodes.json`
  - Step 1: `initial_groundtruth.json`
  - Step 2: `filtered_groundtruth.json`
  - Step 3: `crafted_rounds.json`
  - Step 4: `txprobe_execution.json`
  - Step 5: `reconciled_topology.json` & `full_inferred_topology.json`
  - Step 6: `topology_evaluation_report.json` & `TOPOLOGY_EVALUATION_REPORT.md`
- Supports `--from-step` (0–6) and `--to-step` (0–6).
- Supports resuming from existing checkpoints in `--run-dir`.
- Displays step-by-step progress and status reports.

---

## 2. Architecture & Design
- Core engine: `txprobe/txprobe/orchestrator.py`
  - `PipelineStep`: enum or integer 0..6
  - `PipelineArtifacts`: dataclass tracking paths to intermediate files
  - `PipelineRunner`: async orchestrator calling step functions
- CLI entry point: `txprobe/scripts/run_pipeline.py`
- Test suite: `txprobe/tests/test_orchestrator.py`
