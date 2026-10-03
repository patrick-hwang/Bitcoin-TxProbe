"""End-to-end master pipeline orchestrator for TxProbe on Bitcoin Testnet4."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Callable

from txprobe.config import Config
from txprobe.discovery.harvester import HarvestResult, harvest_addresses
from txprobe.discovery.peer_scanner import ScanResult, scan_and_select_peers
from txprobe.evaluation import (
    EvaluationReport,
    evaluate_reconciled_results,
    generate_markdown_report,
)
from txprobe.groundtruth import GroundtruthResult, capture_initial_groundtruth
from txprobe.invblock import InvblockResult, run_invblock_prefilter
from txprobe.models.graph import GraphSnapshot
from txprobe.models.transaction import TxProbeCraftingResult
from txprobe.probing import TxProbeExecutionResult, run_txprobe_execution
from txprobe.reconciliation import (
    ReconciliationResult,
    capture_final_groundtruth,
    reconcile_topology,
)
from txprobe.rpc.client import AsyncBitcoinRpc
from txprobe.transactions import craft_all_rounds

log = logging.getLogger(__name__)


def _load_snapshot_from_file(path: Path) -> GraphSnapshot:
    """Load GraphSnapshot from InvblockResult, GroundtruthResult, or plain GraphSnapshot JSON."""
    try:
        return InvblockResult.load(path).snapshot
    except Exception:
        pass
    try:
        return GroundtruthResult.load(path).snapshot
    except Exception:
        pass
    return GraphSnapshot.load(path)


@dataclass
class PipelineArtifacts:
    """Paths to all artifacts produced and consumed across pipeline steps."""

    run_dir: Path
    harvest: Path = field(init=False)
    discovered_nodes: Path = field(init=False)
    initial_groundtruth: Path = field(init=False)
    filtered_groundtruth: Path = field(init=False)
    crafted_rounds: Path = field(init=False)
    txprobe_execution: Path = field(init=False)
    final_groundtruth: Path = field(init=False)
    reconciled_topology: Path = field(init=False)
    full_inferred_topology: Path = field(init=False)
    evaluation_report_json: Path = field(init=False)
    evaluation_report_md: Path = field(init=False)

    def __post_init__(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.harvest = self.run_dir / "harvest.json"
        self.discovered_nodes = self.run_dir / "discovered_nodes.json"
        self.initial_groundtruth = self.run_dir / "initial_groundtruth.json"
        self.filtered_groundtruth = self.run_dir / "filtered_groundtruth.json"
        self.crafted_rounds = self.run_dir / "crafted_rounds.json"
        self.txprobe_execution = self.run_dir / "txprobe_execution.json"
        self.final_groundtruth = self.run_dir / "final_groundtruth.json"
        self.reconciled_topology = self.run_dir / "reconciled_topology.json"
        self.full_inferred_topology = self.run_dir / "full_inferred_topology.json"
        self.evaluation_report_json = self.run_dir / "topology_evaluation_report.json"
        self.evaluation_report_md = self.run_dir / "TOPOLOGY_EVALUATION_REPORT.md"


class MasterPipelineOrchestrator:
    """Coordinates and executes TxProbe Steps 0 through 6 end-to-end."""

    def __init__(
        self,
        config: Config,
        run_dir: Path | None = None,
        from_step: int = 0,
        to_step: int = 6,
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config
        if run_dir is None:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.run_dir = Path("results") / f"run_{ts}"
        else:
            self.run_dir = Path(run_dir)

        self.artifacts = PipelineArtifacts(run_dir=self.run_dir)
        self.from_step = max(0, min(6, from_step))
        self.to_step = max(0, min(6, to_step))
        self.progress_callback = progress_callback

    def _notify(self, step_name: str, message: str) -> None:
        log.info("[%s] %s", step_name, message)
        if self.progress_callback:
            self.progress_callback(step_name, message)

    async def run(self) -> PipelineArtifacts:
        """Execute the configured pipeline steps sequentially."""
        self._notify("PIPELINE", f"Starting TxProbe Pipeline: Steps {self.from_step} -> {self.to_step}")
        self._notify("PIPELINE", f"Artifacts Directory: {self.run_dir.resolve()}")

        # Step 0: Discovery & Setup (Phase 1 & 2)
        scan_result = await self._run_step_0()

        # Step 1: Initial Groundtruth Snapshot
        gt_result = await self._run_step_1(scan_result)

        # Step 2: INVBLOCK Pre-filtering
        invblock_result = await self._run_step_2(gt_result)

        # Step 3: Raw Transaction Crafting
        crafting_result = await self._run_step_3(invblock_result)

        # Step 4: Probing Execution
        execution_result = await self._run_step_4(crafting_result)

        # Step 5: Groundtruth Reconciliation
        reconciled_result = await self._run_step_5(execution_result, invblock_result)

        # Step 6: Metric Calculation & Evaluation
        await self._run_step_6(reconciled_result)

        self._notify("PIPELINE", "TxProbe Pipeline completed successfully!")
        return self.artifacts

    async def _run_step_0(self) -> ScanResult | None:
        """Step 0: Address Harvesting and Peer Selection."""
        if self.from_step > 0:
            if self.artifacts.discovered_nodes.is_file():
                self._notify("STEP 0", f"Loading existing discovered peers: {self.artifacts.discovered_nodes}")
                return ScanResult.load(self.artifacts.discovered_nodes)
            return None

        self._notify("STEP 0", "Phase 1: Harvesting peer addresses...")
        if self.artifacts.harvest.is_file():
            self._notify("STEP 0", f"Using existing harvest cache: {self.artifacts.harvest}")
            harvest = HarvestResult.load(self.artifacts.harvest)
        else:
            harvest = await harvest_addresses(self.config)
            harvest.save(self.artifacts.harvest)
            self._notify("STEP 0", f"Phase 1 complete: {harvest.stats.total_unique} addresses harvested.")

        self._notify("STEP 0", "Phase 2: Connecting and selecting mutual peers...")
        scan_result = await scan_and_select_peers(self.config, harvest)
        scan_result.save(self.artifacts.discovered_nodes)
        self._notify(
            "STEP 0",
            f"Phase 2 complete: {scan_result.stats.selected_count} mutual peers selected.",
        )
        return scan_result

    async def _run_step_1(self, scan_result: ScanResult | None) -> GroundtruthResult | None:
        """Step 1: Initial Groundtruth Snapshot Capture."""
        if self.from_step > 1:
            if self.artifacts.initial_groundtruth.is_file():
                self._notify("STEP 1", f"Loading existing initial groundtruth: {self.artifacts.initial_groundtruth}")
                return GroundtruthResult.load(self.artifacts.initial_groundtruth)
            return None

        if self.to_step < 1:
            return None

        if scan_result is None:
            if not self.artifacts.discovered_nodes.is_file():
                raise FileNotFoundError(f"Missing required Step 0 artifact: {self.artifacts.discovered_nodes}")
            scan_result = ScanResult.load(self.artifacts.discovered_nodes)

        self._notify("STEP 1", "Capturing initial groundtruth topology snapshot...")
        target_nodes = (
            scan_result.selected_identities()
            if hasattr(scan_result, "selected_identities")
            else scan_result
        )
        gt_result = await capture_initial_groundtruth(self.config, target_nodes)
        gt_result.save(self.artifacts.initial_groundtruth)
        self._notify(
            "STEP 1",
            f"Step 1 complete: {gt_result.snapshot.num_nodes} nodes, {gt_result.snapshot.num_edges} edges.",
        )
        return gt_result

    async def _run_step_2(self, gt_result: GroundtruthResult | None) -> InvblockResult | GraphSnapshot | None:
        """Step 2: INVBLOCK Pre-filtering."""
        if self.from_step > 2:
            if self.artifacts.filtered_groundtruth.is_file():
                self._notify("STEP 2", f"Loading existing filtered groundtruth: {self.artifacts.filtered_groundtruth}")
                try:
                    return InvblockResult.load(self.artifacts.filtered_groundtruth)
                except Exception:
                    return _load_snapshot_from_file(self.artifacts.filtered_groundtruth)
            return None

        if self.to_step < 2:
            return None

        if gt_result is None:
            if not self.artifacts.initial_groundtruth.is_file():
                raise FileNotFoundError(f"Missing required Step 1 artifact: {self.artifacts.initial_groundtruth}")
            gt_result = GroundtruthResult.load(self.artifacts.initial_groundtruth)

        self._notify("STEP 2", "Running INVBLOCK dual-condition pre-filtering...")
        probe_0_cfg = self.config.get_node(0)
        probe_1_cfg = self.config.get_node(1)
        p0_log = Path(probe_0_cfg.txprobe_log_file or "txprobe_0.log")
        p1_log = Path(probe_1_cfg.txprobe_log_file or "txprobe_1.log")

        async with AsyncBitcoinRpc.from_node_config(probe_0_cfg) as p0, \
                   AsyncBitcoinRpc.from_node_config(probe_1_cfg) as p1:
            res = await run_invblock_prefilter(
                graph=gt_result.snapshot,
                probe_0=p0,
                probe_1=p1,
                probe_0_log_path=p0_log,
                probe_1_log_path=p1_log,
                wait_time_sec=self.config.invblock.wait_time_sec,
                clear_logs=True,
            )
            res.save(self.artifacts.filtered_groundtruth)
            self._notify(
                "STEP 2",
                f"Step 2 complete: {res.stats.remaining_qualified_count} qualified nodes remaining.",
            )
            return res

    async def _run_step_3(self, invblock_result: InvblockResult | GraphSnapshot | None) -> TxProbeCraftingResult | None:
        """Step 3: Raw Transaction Crafting."""
        if self.from_step > 3:
            if self.artifacts.crafted_rounds.is_file():
                self._notify("STEP 3", f"Loading existing pre-crafted transactions: {self.artifacts.crafted_rounds}")
                return TxProbeCraftingResult.load(self.artifacts.crafted_rounds)
            return None

        if self.to_step < 3:
            return None

        snapshot: GraphSnapshot
        if isinstance(invblock_result, InvblockResult):
            snapshot = invblock_result.snapshot
        elif isinstance(invblock_result, GraphSnapshot):
            snapshot = invblock_result
        elif self.artifacts.filtered_groundtruth.is_file():
            snapshot = _load_snapshot_from_file(self.artifacts.filtered_groundtruth)
        else:
            raise FileNotFoundError(f"Missing required Step 2 artifact: {self.artifacts.filtered_groundtruth}")

        self._notify("STEP 3", "Crafting matrix rounds, parent, flood, and marker transactions...")
        probe_0_cfg = self.config.get_node(0)

        async with AsyncBitcoinRpc.from_node_config(probe_0_cfg, use_wallet=False) as root_rpc:
            if probe_0_cfg.wallet:
                loaded = await root_rpc.listwallets()
                if probe_0_cfg.wallet not in loaded:
                    await root_rpc.loadwallet(probe_0_cfg.wallet)

        async with AsyncBitcoinRpc.from_node_config(probe_0_cfg, use_wallet=True) as wallet_rpc:
            res = await craft_all_rounds(
                snapshot=snapshot,
                rpc=wallet_rpc,
                config=self.config.tx_crafting,
            )
            res.save(self.artifacts.crafted_rounds)
            self._notify(
                "STEP 3",
                f"Step 3 complete: {res.stats.total_rounds} rounds pre-crafted ({res.stats.total_marker_txs} markers).",
            )
            return res

    async def _run_step_4(self, crafting_result: TxProbeCraftingResult | None) -> TxProbeExecutionResult | None:
        """Step 4: Multi-Round Probing Execution."""
        if self.from_step > 4:
            if self.artifacts.txprobe_execution.is_file():
                self._notify("STEP 4", f"Loading existing execution results: {self.artifacts.txprobe_execution}")
                return TxProbeExecutionResult.load(self.artifacts.txprobe_execution)
            return None

        if self.to_step < 4:
            return None

        if crafting_result is None:
            if not self.artifacts.crafted_rounds.is_file():
                raise FileNotFoundError(f"Missing required Step 3 artifact: {self.artifacts.crafted_rounds}")
            crafting_result = TxProbeCraftingResult.load(self.artifacts.crafted_rounds)

        self._notify("STEP 4", "Executing multi-round TxProbe topology inference loop...")
        probe_0_cfg = self.config.get_node(0)
        p0_log = Path(probe_0_cfg.txprobe_log_file or "txprobe_0.log")

        async with AsyncBitcoinRpc.from_node_config(probe_0_cfg, use_wallet=False) as p0:
            res = await run_txprobe_execution(
                crafting_result=crafting_result,
                probe_0=p0,
                probe_0_log_path=p0_log,
                config=self.config.txprobe_execution,
                checkpoint_path=self.run_dir / "txprobe_checkpoint.json",
            )
            res.save(self.artifacts.txprobe_execution)
            self._notify(
                "STEP 4",
                f"Step 4 complete: {res.stats.inferred_edges_count} edges inferred across {res.stats.completed_rounds} rounds.",
            )
            return res

    async def _run_step_5(
        self,
        execution_result: TxProbeExecutionResult | None,
        invblock_result: InvblockResult | GraphSnapshot | None,
    ) -> ReconciliationResult | None:
        """Step 5: Post-Probing Groundtruth Reconciliation & Full Inferred Topology."""
        if self.from_step > 5:
            if self.artifacts.reconciled_topology.is_file():
                self._notify("STEP 5", f"Loading existing reconciled topology: {self.artifacts.reconciled_topology}")
                data = json.loads(self.artifacts.reconciled_topology.read_text(encoding="utf-8"))
                return ReconciliationResult.from_dict(data)
            return None

        if self.to_step < 5:
            return None

        if execution_result is None:
            if not self.artifacts.txprobe_execution.is_file():
                raise FileNotFoundError(f"Missing required Step 4 artifact: {self.artifacts.txprobe_execution}")
            execution_result = TxProbeExecutionResult.load(self.artifacts.txprobe_execution)

        pre_gt: GraphSnapshot
        if isinstance(invblock_result, InvblockResult):
            pre_gt = invblock_result.snapshot
        elif isinstance(invblock_result, GraphSnapshot):
            pre_gt = invblock_result
        elif self.artifacts.filtered_groundtruth.is_file():
            pre_gt = _load_snapshot_from_file(self.artifacts.filtered_groundtruth)
        elif self.artifacts.initial_groundtruth.is_file():
            pre_gt = _load_snapshot_from_file(self.artifacts.initial_groundtruth)
        else:
            raise FileNotFoundError(f"Missing Step 2 artifact: {self.artifacts.filtered_groundtruth}")

        self._notify("STEP 5", "Capturing final post-probing groundtruth and reconciling topologies...")
        final_gt = await capture_final_groundtruth(
            self.config, execution_result.inferred_snapshot.nodes
        )
        final_gt.save(self.artifacts.final_groundtruth)

        res = reconcile_topology(
            inferred_snapshot=execution_result.inferred_snapshot,
            groundtruth_before=pre_gt,
            groundtruth_after=final_gt.snapshot,
            malfunctioning_nodes=execution_result.malfunctioning_nodes,
            dropped_nodes=execution_result.dropped_nodes,
        )
        res.save(self.artifacts.reconciled_topology)
        res.full_inferred_topology.save(self.artifacts.full_inferred_topology)

        self._notify(
            "STEP 5",
            f"Step 5 complete: Full inferred topology exported ({res.stats.surviving_full_nodes} nodes, {res.stats.full_inferred_edges_count} edges).",
        )
        return res

    async def _run_step_6(self, reconciled_result: ReconciliationResult | None) -> EvaluationReport | None:
        """Step 6: Metric Calculation & Topology Evaluation."""
        if self.to_step < 6:
            return None

        reconciled_dict: dict
        if reconciled_result is not None:
            reconciled_dict = reconciled_result.to_dict()
        elif self.artifacts.reconciled_topology.is_file():
            self._notify("STEP 6", f"Loading reconciled topology from: {self.artifacts.reconciled_topology}")
            reconciled_dict = json.loads(self.artifacts.reconciled_topology.read_text(encoding="utf-8"))
        else:
            raise FileNotFoundError(f"Missing Step 5 artifact: {self.artifacts.reconciled_topology}")

        self._notify("STEP 6", "Computing network topology metrics and groundtruth validation scores...")
        report = evaluate_reconciled_results(reconciled_dict, compute_paths=True)
        report.save_json(self.artifacts.evaluation_report_json)

        md_text = generate_markdown_report(report)
        self.artifacts.evaluation_report_md.write_text(md_text, encoding="utf-8")

        self._notify(
            "STEP 6",
            f"Step 6 complete: Reports saved to {self.artifacts.evaluation_report_json.name} and {self.artifacts.evaluation_report_md.name}.",
        )
        return report
