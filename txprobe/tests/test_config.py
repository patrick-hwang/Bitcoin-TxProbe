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
    # Default value for poll_interval_sec, clearnet_onetry_concurrency, tor_onetry_concurrency
    assert cfg.discovery.poll_interval_sec == 5.0
    assert cfg.discovery.clearnet_onetry_concurrency == 32
    assert cfg.discovery.tor_onetry_concurrency == 8


def test_testnet4_yaml_probes_are_0_and_1():
    yaml_path = Path(__file__).resolve().parent.parent / "config" / "testnet4.yaml"
    cfg = load_config(yaml_path)
    assert [n.id for n in cfg.probe_nodes] == [0, 1]
    assert [n.id for n in cfg.groundtruth_nodes] == [2, 3, 4, 5, 6]
    assert cfg.discovery.target_count == 0
    assert cfg.discovery.crawling_time_sec == 600.0
    assert cfg.discovery.poll_interval_sec == 5.0
    assert cfg.discovery.retry_interval_sec == 45.0
    assert cfg.discovery.clearnet_onetry_concurrency == 32
    assert cfg.discovery.tor_onetry_concurrency == 8


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


def test_txprobe_execution_config_defaults_and_custom():
    # Defaults when section is omitted
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        f.flush()
        cfg_default = load_config(f.name)

    assert cfg_default.txprobe_execution.invblock_wait_sec == 5.0
    assert cfg_default.txprobe_execution.flood_wait_sec == 1.0
    assert cfg_default.txprobe_execution.parent_wait_sec == 5.0
    assert cfg_default.txprobe_execution.marker_propagation_wait_sec == 10.0
    assert cfg_default.txprobe_execution.getdata_wait_sec == 5.0
    assert cfg_default.txprobe_execution.cleanup_wait_sec == 2.0

    # Custom values when section is present
    custom_yaml = SAMPLE_YAML + """\
txprobe_execution:
  invblock_wait_sec: 3.5
  flood_wait_sec: 0.5
  parent_wait_sec: 4.0
  marker_propagation_wait_sec: 8.0
  getdata_wait_sec: 6.0
  cleanup_wait_sec: 1.5
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(custom_yaml)
        f.flush()
        cfg_custom = load_config(f.name)

    assert cfg_custom.txprobe_execution.invblock_wait_sec == 3.5
    assert cfg_custom.txprobe_execution.flood_wait_sec == 0.5
    assert cfg_custom.txprobe_execution.parent_wait_sec == 4.0
    assert cfg_custom.txprobe_execution.marker_propagation_wait_sec == 8.0
    assert cfg_custom.txprobe_execution.getdata_wait_sec == 6.0
    assert cfg_custom.txprobe_execution.cleanup_wait_sec == 1.5


