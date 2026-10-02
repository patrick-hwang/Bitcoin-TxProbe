"""Unit tests for MasterPipelineOrchestrator and run_pipeline CLI."""

from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest

from txprobe.config import (
    Config,
    DiscoveryConfig,
    InvblockConfig,
    NodeConfig,
    ReachabilityConfig,
    TxCraftingConfig,
    TxProbeExecutionConfig,
)
from txprobe.groundtruth import GroundtruthResult, GroundtruthStats
from txprobe.models.graph import GraphSnapshot
from txprobe.models.node import NodeIdentity
from txprobe.models.transaction import TxProbeCraftingResult
from txprobe.orchestrator import MasterPipelineOrchestrator, PipelineArtifacts
from txprobe.probing import TxProbeExecutionResult, TxProbeExecutionStats


def _make_dummy_config() -> Config:
    return Config(
        network="testnet4",
        default_port=48333,
        nodes=[
            NodeConfig(id=0, role="probe", rpcport=18332, rpcuser="u", rpcpassword="p"),
            NodeConfig(id=1, role="probe", rpcport=18333, rpcuser="u", rpcpassword="p"),
            NodeConfig(id=2, role="groundtruth", rpcport=18334, rpcuser="u", rpcpassword="p"),
        ],
        discovery=DiscoveryConfig(),
        reachability=ReachabilityConfig(),
        dns_seeds=[],
        invblock=InvblockConfig(),
        tx_crafting=TxCraftingConfig(),
        txprobe_execution=TxProbeExecutionConfig(),
    )


def test_pipeline_artifacts_initialization(tmp_path: Path):
    """Verify PipelineArtifacts generates proper paths within run_dir."""
    artifacts = PipelineArtifacts(run_dir=tmp_path / "test_run")
    assert artifacts.run_dir.is_dir()
    assert artifacts.harvest.name == "harvest.json"
    assert artifacts.discovered_nodes.name == "discovered_nodes.json"
    assert artifacts.initial_groundtruth.name == "initial_groundtruth.json"
    assert artifacts.filtered_groundtruth.name == "filtered_groundtruth.json"
    assert artifacts.crafted_rounds.name == "crafted_rounds.json"
    assert artifacts.txprobe_execution.name == "txprobe_execution.json"
    assert artifacts.reconciled_topology.name == "reconciled_topology.json"
    assert artifacts.full_inferred_topology.name == "full_inferred_topology.json"
    assert artifacts.evaluation_report_json.name == "topology_evaluation_report.json"
    assert artifacts.evaluation_report_md.name == "TOPOLOGY_EVALUATION_REPORT.md"


@pytest.mark.asyncio
async def test_orchestrator_step_6_standalone(tmp_path: Path):
    """Test running Step 6 directly when Step 5 reconciled_topology.json exists."""
    config = _make_dummy_config()
    run_dir = tmp_path / "run_step6"
    artifacts = PipelineArtifacts(run_dir=run_dir)

    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(1, 4))
    triangle_adj = {
        nodes[0]: (nodes[1], nodes[2]),
        nodes[1]: (nodes[0], nodes[2]),
        nodes[2]: (nodes[0], nodes[1]),
    }
    graph = GraphSnapshot(nodes=nodes, adj_list=triangle_adj)

    payload = {
        "full_inferred_topology": graph.to_dict(),
        "reconciled_groundtruth": graph.to_dict(),
        "evaluation_inferred_topology": graph.to_dict(),
        "stats": {"surviving_full_nodes": 3, "full_inferred_edges_count": 3},
    }
    artifacts.reconciled_topology.write_text(json.dumps(payload), encoding="utf-8")

    orchestrator = MasterPipelineOrchestrator(
        config=config,
        run_dir=run_dir,
        from_step=6,
        to_step=6,
    )
    result_artifacts = await orchestrator.run()

    assert result_artifacts.evaluation_report_json.is_file()
    assert result_artifacts.evaluation_report_md.is_file()

    eval_data = json.loads(result_artifacts.evaluation_report_json.read_text(encoding="utf-8"))
    assert eval_data["global_topology"]["num_nodes"] == 3
    assert eval_data["validation"]["accuracy"] == 1.0


@pytest.mark.asyncio
async def test_orchestrator_step_5_to_6(tmp_path: Path):
    """Test running Step 5 through 6 with mocked final groundtruth and Step 4 artifacts."""
    config = _make_dummy_config()
    run_dir = tmp_path / "run_step5_6"
    artifacts = PipelineArtifacts(run_dir=run_dir)

    nodes = tuple(NodeIdentity(addr=f"10.0.0.{i}:48333") for i in range(1, 4))
    triangle_adj = {
        nodes[0]: (nodes[1], nodes[2]),
        nodes[1]: (nodes[0], nodes[2]),
        nodes[2]: (nodes[0], nodes[1]),
    }
    graph = GraphSnapshot(nodes=nodes, adj_list=triangle_adj)

    # Save Step 2 pre-groundtruth
    graph.save(artifacts.filtered_groundtruth)

    # Save Step 4 execution result
    step4_res = TxProbeExecutionResult(
        inferred_snapshot=graph,
        filtered_groundtruth_snapshot=graph,
        stats=TxProbeExecutionStats(
            total_rounds=1,
            completed_rounds=1,
            initial_nodes_count=3,
            surviving_nodes_count=3,
            malfunctioning_nodes_count=0,
            dropped_nodes_count=0,
            total_tested_pairs=3,
            inferred_edges_count=3,
            filtered_groundtruth_edges_count=3,
        ),
        round_results=(),
        malfunctioning_nodes=(),
        dropped_nodes=(),
    )
    step4_res.save(artifacts.txprobe_execution)

    dummy_gt_result = GroundtruthResult(
        snapshot=graph,
        groundtruth_identities={2: nodes[0]},
        stats=GroundtruthStats(),
    )

    with patch(
        "txprobe.orchestrator.capture_final_groundtruth",
        new=AsyncMock(return_value=dummy_gt_result),
    ):
        orchestrator = MasterPipelineOrchestrator(
            config=config,
            run_dir=run_dir,
            from_step=5,
            to_step=6,
        )
        res_artifacts = await orchestrator.run()

    assert res_artifacts.reconciled_topology.is_file()
    assert res_artifacts.full_inferred_topology.is_file()
    assert res_artifacts.evaluation_report_json.is_file()
    assert res_artifacts.evaluation_report_md.is_file()


def test_run_pipeline_cli_help(monkeypatch):
    """Test CLI entry point runs --help without error."""
    script_path = str(
        Path(__file__).resolve().parent.parent / "scripts" / "run_pipeline.py"
    )
    monkeypatch.setattr(sys, "argv", [script_path, "--help"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(script_path, run_name="__main__")
    assert exc_info.value.code == 0
