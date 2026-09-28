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


@dataclass
class DiscoveryConfig:
    """Configuration for the node discovery process."""
    target_count: int = 1000
    crawling_time_sec: float = 180.0
    poll_interval_sec: float = 5.0
    clearnet_onetry_concurrency: int = 32
    tor_onetry_concurrency: int = 8


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
        )
        for n in raw["nodes"]
    ]

    disc_raw = raw.get("discovery", {})
    discovery = DiscoveryConfig(
        target_count=disc_raw.get("target_count", 1000),
        crawling_time_sec=float(disc_raw.get("crawling_time_sec", 180.0)),
        poll_interval_sec=float(disc_raw.get("poll_interval_sec", 5.0)),
        clearnet_onetry_concurrency=int(
            disc_raw.get("clearnet_onetry_concurrency", 32)
        ),
        tor_onetry_concurrency=int(disc_raw.get("tor_onetry_concurrency", 8)),
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

    return Config(
        network=raw["network"],
        default_port=int(raw["default_port"]),
        nodes=nodes,
        discovery=discovery,
        reachability=reachability,
        dns_seeds=raw.get("dns_seeds", []),
    )
