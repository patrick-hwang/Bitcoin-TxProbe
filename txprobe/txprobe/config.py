"""Configuration loading from YAML files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class NodeConfig:
    """Configuration for a single Bitcoin node."""
    id: int
    role: str                # "probe" or "groundtruth"
    rpcport: int
    rpcuser: str
    rpcpassword: str
    wallet: str = ""
    rpchost: str = "127.0.0.1"
    txprobe_log_file: str = ""


@dataclass
class InvblockConfig:
    """Configuration for the INVBLOCK pre-filtering step."""
    wait_time_sec: float = 5.0


@dataclass
class TxCraftingConfig:
    """Configuration for Step 3 raw transaction crafting and UTXO management."""
    utxo_target_sats: int = 2000
    parent_fee_sats: int = 500
    marker_fee_sats: int = 500
    split_fee_rate_sat_vb: int = 2
    max_outputs_per_split_tx: int = 500
    max_source_size: int = 75
    poll_interval_sec: float = 10.0
    block_propagation_wait_sec: float = 15.0


@dataclass
class TxProbeExecutionConfig:
    """Configuration for Step 4 TxProbe execution loop."""
    invblock_wait_sec: float = 10.0
    flood_wait_sec: float = 1.0
    parent_wait_sec: float = 5.0
    marker_propagation_wait_sec: float = 10.0
    getdata_wait_sec: float = 15.0
    cleanup_wait_sec: float = 2.0


@dataclass
class DiscoveryConfig:
    """Configuration for the node discovery process."""
    target_count: int = 0  # 0 means connect to all collected candidates
    crawling_time_sec: float = 600.0
    poll_interval_sec: float = 5.0
    clearnet_onetry_concurrency: int = 32
    tor_onetry_concurrency: int = 8
    max_addrman_age_days: float = 0.0
    retry_interval_sec: float = 45.0


@dataclass
class ReachabilityConfig:
    """Configuration for the active reachability test."""
    tor_proxy_host: str = "127.0.0.1"
    tor_proxy_port: int = 9050
    clearnet_timeout_sec: float = 5.0
    tor_timeout_sec: float = 30.0
    clearnet_concurrency: int = 50
    tor_concurrency: int = 20


@dataclass
class Config:
    """Top-level experiment configuration."""
    network: str
    default_port: int
    nodes: list[NodeConfig]
    discovery: DiscoveryConfig
    reachability: ReachabilityConfig
    dns_seeds: list[str]
    invblock: InvblockConfig = None  # type: ignore[assignment]
    tx_crafting: TxCraftingConfig = None  # type: ignore[assignment]
    txprobe_execution: TxProbeExecutionConfig = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.invblock is None:
            self.invblock = InvblockConfig()
        if self.tx_crafting is None:
            self.tx_crafting = TxCraftingConfig()
        if self.txprobe_execution is None:
            self.txprobe_execution = TxProbeExecutionConfig()

    @property
    def probe_nodes(self) -> list[NodeConfig]:
        """Return probe node configs (role == 'probe')."""
        return [n for n in self.nodes if n.role == "probe"]

    @property
    def groundtruth_nodes(self) -> list[NodeConfig]:
        """Return groundtruth node configs (role == 'groundtruth')."""
        return [n for n in self.nodes if n.role == "groundtruth"]

    def get_node(self, node_id: int) -> NodeConfig:
        """Look up a node config by id."""
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"No node with id={node_id}")


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML configuration file.

    Args:
        path: Path to the YAML file.

    Returns:
        A populated Config instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        KeyError: If required keys are missing.
    """
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    nodes = [
        NodeConfig(
            id=n["id"],
            role=n["role"],
            rpcport=n["rpcport"],
            rpcuser=n["rpcuser"],
            rpcpassword=n["rpcpassword"],
            wallet=n.get("wallet", ""),
            rpchost=n.get("rpchost", "127.0.0.1"),
            txprobe_log_file=n.get("txprobe_log_file", ""),
        )
        for n in raw["nodes"]
    ]

    disc_raw = raw.get("discovery", {})
    discovery = DiscoveryConfig(
        target_count=int(disc_raw.get("target_count", 0)),
        crawling_time_sec=float(disc_raw.get("crawling_time_sec", 600.0)),
        poll_interval_sec=float(disc_raw.get("poll_interval_sec", 5.0)),
        clearnet_onetry_concurrency=int(
            disc_raw.get("clearnet_onetry_concurrency", 32)
        ),
        tor_onetry_concurrency=int(disc_raw.get("tor_onetry_concurrency", 8)),
        max_addrman_age_days=float(disc_raw.get("max_addrman_age_days", 0.0)),
        retry_interval_sec=float(disc_raw.get("retry_interval_sec", 45.0)),
    )

    reach_raw = raw.get("reachability", {})
    reachability = ReachabilityConfig(
        tor_proxy_host=reach_raw.get("tor_proxy_host", "127.0.0.1"),
        tor_proxy_port=int(reach_raw.get("tor_proxy_port", 9050)),
        clearnet_timeout_sec=float(reach_raw.get("clearnet_timeout_sec", 5.0)),
        tor_timeout_sec=float(reach_raw.get("tor_timeout_sec", 30.0)),
        clearnet_concurrency=int(reach_raw.get("clearnet_concurrency", 50)),
        tor_concurrency=int(reach_raw.get("tor_concurrency", 20)),
    )

    inv_raw = raw.get("invblock", {})
    invblock = InvblockConfig(
        wait_time_sec=float(inv_raw.get("wait_time_sec", 5.0)),
    )

    craft_raw = raw.get("tx_crafting", {})
    tx_crafting = TxCraftingConfig(
        utxo_target_sats=int(craft_raw.get("utxo_target_sats", 2000)),
        parent_fee_sats=int(craft_raw.get("parent_fee_sats", 500)),
        marker_fee_sats=int(craft_raw.get("marker_fee_sats", 500)),
        split_fee_rate_sat_vb=int(craft_raw.get("split_fee_rate_sat_vb", 2)),
        max_outputs_per_split_tx=int(
            craft_raw.get("max_outputs_per_split_tx", 500)
        ),
        max_source_size=int(craft_raw.get("max_source_size", 75)),
        poll_interval_sec=float(craft_raw.get("poll_interval_sec", 10.0)),
        block_propagation_wait_sec=float(
            craft_raw.get("block_propagation_wait_sec", 15.0)
        ),
    )

    exec_raw = raw.get("txprobe_execution", {})
    txprobe_execution = TxProbeExecutionConfig(
        invblock_wait_sec=float(exec_raw.get("invblock_wait_sec", 5.0)),
        flood_wait_sec=float(exec_raw.get("flood_wait_sec", 1.0)),
        parent_wait_sec=float(exec_raw.get("parent_wait_sec", 5.0)),
        marker_propagation_wait_sec=float(
            exec_raw.get("marker_propagation_wait_sec", 10.0)
        ),
        getdata_wait_sec=float(exec_raw.get("getdata_wait_sec", 5.0)),
        cleanup_wait_sec=float(exec_raw.get("cleanup_wait_sec", 2.0)),
    )

    return Config(
        network=raw["network"],
        default_port=int(raw["default_port"]),
        nodes=nodes,
        discovery=discovery,
        reachability=reachability,
        dns_seeds=raw.get("dns_seeds", []),
        invblock=invblock,
        tx_crafting=tx_crafting,
        txprobe_execution=txprobe_execution,
    )
