import unittest

from .groundtruth import GroundTruthError, collect_phase1_groundtruth


def _network_info(node_id):
    return {"localaddresses": [{"address": f"node{node_id}.onion", "port": 18000 + node_id}]}


class Phase1GroundTruthTests(unittest.TestCase):
    def setUp(self):
        self.network_info = {node_id: _network_info(node_id) for node_id in range(7)}

    def test_collects_external_peers_and_directed_edges(self):
        peer_info = {
            1: [
                {"addr": "node2.onion:18002"},
                {"addr": "node0.onion:18000"},
                {"addr": "outside.example:8333"},
            ],
            2: [{"addr": "outside.example:8333"}],
            3: [{"addr": "node4.onion:18004"}],
            4: [{"addr": "node6.onion:18006"}],
            5: [],
        }

        snapshot = collect_phase1_groundtruth(self.network_info, peer_info)

        self.assertEqual(snapshot.nodes, (1, 2, 3, 4, 5, "outside.example:8333"))
        self.assertEqual(snapshot.peers[1], (2, "outside.example:8333"))
        self.assertEqual(snapshot.peers[2], ("outside.example:8333",))
        self.assertEqual(snapshot.peers[3], (4,))
        self.assertEqual(
            snapshot.gt_edges,
            (
                (1, 2),
                (1, "outside.example:8333"),
                (2, 1),
                (2, "outside.example:8333"),
                (3, 4),
                (4, 3),
                ("outside.example:8333", 1),
                ("outside.example:8333", 2),
            ),
        )

    def test_filters_localhost_and_ipv6_external_peers(self):
        peer_info = {
            1: [
                {"addr": "127.0.0.1:18444"},
                {"addr": "[2001:db8::2]:18002"},
                {"addr": "connectable.example:8333"},
            ],
            2: [],
            3: [],
            4: [],
            5: [],
        }

        snapshot = collect_phase1_groundtruth(self.network_info, peer_info)

        self.assertEqual(snapshot.nodes, (1, 2, 3, 4, 5, "connectable.example:8333"))
        self.assertEqual(
            snapshot.gt_edges,
            ((1, "connectable.example:8333"), ("connectable.example:8333", 1)),
        )

    def test_requires_a_peer_response_for_each_tracked_node(self):
        with self.assertRaisesRegex(GroundTruthError, "Missing getpeerinfo"):
            collect_phase1_groundtruth(self.network_info, {1: [], 2: []})

    def test_requires_the_first_local_address_for_each_tracked_node(self):
        self.network_info[4] = {"localaddresses": []}
        peer_info = {node_id: [] for node_id in range(1, 6)}

        with self.assertRaisesRegex(GroundTruthError, r"Node 4: getnetworkinfo\.localaddresses\[0\]"):
            collect_phase1_groundtruth(self.network_info, peer_info)

    def test_allows_missing_primary_local_address_for_excluded_node(self):
        self.network_info[6] = {"localaddresses": []}
        peer_info = {node_id: [] for node_id in range(1, 6)}

        snapshot = collect_phase1_groundtruth(self.network_info, peer_info)

        self.assertEqual(snapshot.nodes, (1, 2, 3, 4, 5))

    def test_uses_only_the_first_local_address(self):
        self.network_info[2]["localaddresses"].append(
            {"address": "secondary.node2.onion", "port": 19002}
        )
        peer_info = {
            1: [{"addr": "secondary.node2.onion:19002"}],
            2: [],
            3: [],
            4: [],
            5: [],
        }

        snapshot = collect_phase1_groundtruth(self.network_info, peer_info)

        self.assertEqual(snapshot.peers[1], ("secondary.node2.onion:19002",))
