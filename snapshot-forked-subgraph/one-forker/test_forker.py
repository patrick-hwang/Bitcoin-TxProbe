"""Unit tests for Forker Actuator sequence and convergence barriers."""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

# Add project root and module to path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
TXPROBE_DIR = PROJECT_ROOT / "txprobe"
for p in (TXPROBE_DIR, CURRENT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest
from block_builder import ConflictingTransactions, CraftedBlock, ForkPackage
from config import ExperimentConfig
from forker import (
    ForkerExecutionTimings,
    check_nodes_best_block,
    execute_forker_sequence,
    submit_block_to_node,
    wait_for_convergence_barrier,
)
from funding import ParentUtxo
from prober import SubgraphTracker


def test_forker_timings_serialization() -> None:
    """Verify ForkerExecutionTimings model serialization."""
    timings = ForkerExecutionTimings(
        b1_published_at=100.0,
        b1_converged_at=102.5,
        b1_propagation_duration_ms=2500.0,
        b2_published_at=103.0,
        b3_published_at=103.01,
        reorg_converged_at=105.8,
        reorg_propagation_duration_ms=2790.0,
    )
    d = timings.to_dict()
    assert d["b1_published_at"] == 100.0
    assert d["b1_propagation_duration_ms"] == 2500.0
    assert d["reorg_propagation_duration_ms"] == 2790.0


@pytest.mark.asyncio
async def test_check_nodes_best_block_mock_rpc() -> None:
    """Verify checking best block hashes across target nodes."""
    target_hash = "mock_target_hash"
    with patch("forker.make_rpc_client") as mock_make_rpc:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        # Node 1 matches, Node 2 does not match
        mock_client.call.side_effect = [target_hash, "different_hash"]
        mock_make_rpc.return_value = mock_client

        converged, total = await check_nodes_best_block([10, 11], target_hash)
        assert total == 2
        assert converged == 1


@pytest.mark.asyncio
async def test_wait_for_convergence_barrier_immediate_success() -> None:
    """Verify convergence barrier exits promptly when all nodes converge."""
    with patch("forker.check_nodes_best_block", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = (5, 5)  # 5 of 5 converged

        t_conv = await wait_for_convergence_barrier(
            target_block_hash="target_hash",
            peripheral_node_ids=[1, 2, 3, 4, 5],
            timeout_sec=1.0,
        )
        assert t_conv > 0
        mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_execute_forker_sequence_mocked() -> None:
    """Verify the full execution flow: B1 submit -> wait -> B2/B3 submit -> wait."""
    parent_hash = "parent_mock"
    tx0 = ParentUtxo("tx0_mock", 0, 100_000, "addr", "spk")
    conflicts = ConflictingTransactions(tx0, "tx1_hex", "tx1_id", "addr1", "tx2_hex", "tx2_id", "addr2", 10_000, 1_000)
    b1 = CraftedBlock("B1", 101, "b1_mock_hash", parent_hash, "hex_b1", ["tx1_id"], 1000)
    b2 = CraftedBlock("B2", 101, "b2_mock_hash", parent_hash, "hex_b2", ["tx2_id"], 1001)
    b3 = CraftedBlock("B3", 102, "b3_mock_hash", b2.block_hash, "hex_b3", [], 1002)

    fork_pkg = ForkPackage(parent_hash, 100, conflicts, b1, b2, b3)
    tracker = SubgraphTracker(101, parent_hash, {"B1": b1.block_hash, "B2": b2.block_hash, "B3": b3.block_hash})

    with patch("forker.submit_block_to_node", new_callable=AsyncMock) as mock_submit, \
         patch("forker.wait_for_convergence_barrier", new_callable=AsyncMock) as mock_wait:

        mock_submit.return_value = None  # Success
        mock_wait.side_effect = [1001.0, 1003.0]  # B1 converged, then reorg converged

        timings = await execute_forker_sequence(
            fork_pkg=fork_pkg,
            config=ExperimentConfig(),
            tracker=tracker,
            peripheral_nodes=[500, 501],
        )

        assert mock_submit.call_count == 3
        assert mock_wait.call_count == 2
        assert timings.b1_converged_at == 1001.0
        assert timings.reorg_converged_at == 1003.0

        # Check tracker recorded all submit events
        assert len(tracker.event_log) == 3
        hashes_in_events = [e.block_hash for e in tracker.event_log]
        assert b1.block_hash in hashes_in_events
        assert b2.block_hash in hashes_in_events
        assert b3.block_hash in hashes_in_events
