import os
import tempfile
import unittest

from .groundtruth import GroundTruthSnapshot
from .phase2_inv_block_filter import (
    Phase2Error,
    _endpoint_to_string,
    _match_connected,
    build_target_addresses,
    collect_no_invblock_peers,
    plan_cleanup,
)


def _network_info(node_id):
    return {"localaddresses": [{"address": f"node{node_id}.onion", "port": 18000 + node_id}]}


class TargetAddressesTests(unittest.TestCase):
    def test_maps_config_nodes_and_external_peers(self):
        snapshot = GroundTruthSnapshot(
            nodes=(1, 2, 3, 4, 5, "outside.example:8333"),
            peers={1: (2, "outside.example:8333"), 2: ("outside.example:8333",), 3: (4,), 4: (), 5: ()},
            gt_edges=(),
        )
        network_info = {node_id: _network_info(node_id) for node_id in range(1, 6)}

        target_addrs = build_target_addresses(snapshot, network_info)

        self.assertEqual(target_addrs[1], "node1.onion:18001")
        self.assertEqual(target_addrs[5], "node5.onion:18005")
        self.assertEqual(target_addrs["outside.example:8333"], "outside.example:8333")

    def test_requires_advertised_address_for_config_node(self):
        snapshot = GroundTruthSnapshot(
            nodes=(1, 2, 3, 4, 5),
            peers={1: (), 2: (), 3: (), 4: (), 5: ()},
            gt_edges=(),
        )
        network_info = {node_id: _network_info(node_id) for node_id in range(1, 5)}
        network_info[5] = {"localaddresses": []}

        with self.assertRaisesRegex(Phase2Error, "Node 5"):
            build_target_addresses(snapshot, network_info)


class PlanCleanupTests(unittest.TestCase):
    def setUp(self):
        self.target_addrs = {1: "node1.onion:18001", "ext.example:8333": "ext.example:8333"}

    def test_removes_stale_and_connects_missing(self):
        added = ["node1.onion:18001", "stale.example:9999"]
        active = ["node1.onion:18001", "node2.onion:18002", "junk.example:1234"]

        to_remove, to_disconnect, to_add = plan_cleanup(self.target_addrs, added, active)

        self.assertEqual(to_remove, ["stale.example:9999"])
        self.assertEqual(to_disconnect, ["junk.example:1234", "node2.onion:18002"])
        self.assertEqual(to_add, ["ext.example:8333"])

    def test_keeps_existing_connections_untouched(self):
        added = ["node1.onion:18001", "ext.example:8333"]
        active = ["node1.onion:18001"]

        to_remove, to_disconnect, to_add = plan_cleanup(self.target_addrs, added, active)

        self.assertEqual(to_remove, [])
        self.assertEqual(to_disconnect, [])
        self.assertEqual(to_add, [])


class MatchConnectedTests(unittest.TestCase):
    def test_matches_by_endpoint_and_skips_non_full_relay(self):
        target_by_endpoint = {("node1.onion", 18001): 1, ("ext.example", 8333): "ext.example:8333"}
        peers = [
            {"addr": "node1.onion:18001", "connection_type": "outbound-full-relay", "id": 100},
            {"addr": "node1.onion:18001", "connection_type": "block-relay-only", "id": 101},
            {"addr": "ext.example:8333", "connection_type": "outbound-full-relay", "id": 102},
            {"addr": "unrelated.example:8333", "connection_type": "outbound-full-relay", "id": 103},
        ]

        connected = _match_connected(target_by_endpoint, peers)

        self.assertEqual(connected, {1: 100, "ext.example:8333": 102})


class CollectNoinvblockTests(unittest.TestCase):
    def test_returns_targets_that_sent_getdata_for_probe(self):
        hash_one = "1" * 64
        hash_two = "2" * 64
        hash_other = "3" * 64
        peer_map = {100: 1, 101: "ext.example:8333", 102: 2}
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".log") as tmp:
            tmp.write(f"received getdata for: tx {hash_one} peer=100\n")
            tmp.write(f"received getdata for: tx {hash_other} peer=102\n")
            tmp.write(f"received getdata for: tx {hash_two} peer=999\n")
            log_path = tmp.name
        try:
            failures = collect_no_invblock_peers(log_path, {hash_one, hash_two}, peer_map)
            self.assertEqual(failures, (1,))
        finally:
            os.remove(log_path)

    def test_handles_missing_log(self):
        self.assertEqual(collect_no_invblock_peers("no-such-file.log", {"aa"}, {1: 1}), ())


class EndpointToStringTests(unittest.TestCase):
    def test_formats_ipv6_with_brackets(self):
        self.assertEqual(_endpoint_to_string(("2001:db8::1", 8333)), "[2001:db8::1]:8333")

    def test_formats_host_with_port(self):
        self.assertEqual(_endpoint_to_string(("ext.example", 8333)), "ext.example:8333")


if __name__ == "__main__":
    unittest.main()
