"""Tests for config loading."""

import tempfile
from pathlib import Path

import pytest

from txprobe.config import Config, DiscoveryConfig, NodeConfig, ReachabilityConfig, load_config

SAMPLE_YAML = """\
network: testnet4
default_port: 48333

nodes:
  - id: 0
    role: probe
    rpcport: 48347
    rpcuser: user0
    rpcpassword: pass0
    wallet: mywallet
  - id: 1
    role: groundtruth
    rpcport: 48332
    rpcuser: user1
    rpcpassword: pass1

discovery:
  target_count: 500
  crawling_time_sec: 60

reachability:
  tor_proxy_port: 9050
  clearnet_concurrency: 25

dns_seeds:
  - seed.example.com
"""


def test_load_config_basic():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        f.flush()
        cfg = load_config(f.name)

    assert cfg.network == "testnet4"
    assert cfg.default_port == 48333
    assert len(cfg.nodes) == 2
    assert cfg.dns_seeds == ["seed.example.com"]


def test_load_config_nodes():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        f.flush()
        cfg = load_config(f.name)

    assert cfg.nodes[0].id == 0
    assert cfg.nodes[0].role == "probe"
    assert cfg.nodes[0].wallet == "mywallet"
    assert cfg.nodes[1].wallet == ""


def test_probe_and_groundtruth_properties():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        f.flush()
        cfg = load_config(f.name)

    assert len(cfg.probe_nodes) == 1
    assert cfg.probe_nodes[0].id == 0
    assert len(cfg.groundtruth_nodes) == 1
    assert cfg.groundtruth_nodes[0].id == 1


def test_get_node():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        f.flush()
        cfg = load_config(f.name)

    node = cfg.get_node(0)
    assert node.rpcport == 48347
    with pytest.raises(KeyError):
        cfg.get_node(99)


def test_discovery_config():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        f.flush()
        cfg = load_config(f.name)

    assert cfg.discovery.target_count == 500
    assert cfg.discovery.crawling_time_sec == 60.0
    # Default value for poll_interval_sec
    assert cfg.discovery.poll_interval_sec == 10.0


def test_reachability_config():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        f.flush()
        cfg = load_config(f.name)

    assert cfg.reachability.tor_proxy_port == 9050
    assert cfg.reachability.clearnet_concurrency == 25
    # Defaults
    assert cfg.reachability.tor_timeout_sec == 30.0


def test_load_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path.yaml")
