import os
import re
import random
import subprocess
import sys
import time

from .cli import nodes_cli
from .utils import _addr_host
from .utils import _matrix_to_string
from .rounds import generate_rounds, preparing_commands_for_a_round
from .metrics import InferenceMetrics

class Topology:
    def __init__(self, vertices):
        self.vertices = vertices
        self.n = len(vertices)
        self.groundtruth = None
        self.inference = [[1] * self.n for _ in range(self.n)]
        for i in range(self.n):
            self.inference[i][i] = 0
        self._tor_cache = {}

    ### Retrieve address information of the node number node_id
    def _address_info(self, node_id):
        if node_id not in self._tor_cache:
            info = nodes_cli[node_id].win_cli_json("getnetworkinfo")
            la = info.get("localaddresses")
            if not la or len(la) == 0:
                print(f"Error: node {node_id} has no localaddresses", file=sys.stderr)
                sys.exit(1)
            host = la[0]["address"]
            port = la[0]["port"]
            self._tor_cache[node_id] = (host, port)
        return self._tor_cache[node_id]

    def create_groundtruth(self, debug=False, ui=None):
        n = self.n
        gt = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                if random.random() < 0.6:
                    gt[i][j] = gt[j][i] = 1
        self.groundtruth = gt

        if ui:
            ui.update_setup("Random graph generated:\n" + _matrix_to_string(gt) + "\nChecking tor addresses...")

        adj_lines = ["Groundtruth adjacency list:"]
        for i in range(n):
            neighbors = [j + 1 for j in range(n) if gt[i][j]]
            adj_lines.append(f"  Node {i+1}: {neighbors}")
        adj_text = "\n".join(adj_lines)
        if ui:
            ui.show_adjacency(adj_text)

        for node_id in range(1, n + 1):
            host, port = self._address_info(node_id)

        disconnect_pairs = []
        for node_i in range(1, n + 1):
            if ui:
                ui.update_setup(f"Disconnecting non-GT edges on node {node_i}...")
            peers = nodes_cli[node_i].win_cli_json("getpeerinfo")
            peer_hosts = {_addr_host(p.get("addr", "")) for p in peers}
            for node_j in range(1, n + 1):
                if node_i == node_j:
                    continue
                idx_i, idx_j = node_i - 1, node_j - 1
                if gt[idx_i][idx_j] == 0:
                    j_host, j_port = self._address_info(node_j)
                    if j_host in peer_hosts:
                        nodes_cli[node_i].win_cli_raw("addnode", f"{j_host}:{j_port}", "remove", ignore=True)
                        nodes_cli[node_i].win_cli_raw("disconnectnode", f"{j_host}:{j_port}")
                        disconnect_pairs.append((node_i, node_j))

        if disconnect_pairs:
            if ui:
                ui.update_setup("Waiting for disconnects...")
            self._poll_disconnects(disconnect_pairs, debug)

        connect_pairs = []
        for node_i in range(1, n + 1):
            if ui:
                ui.update_setup(f"Connecting GT edges on node {node_i}...")
            peers = nodes_cli[node_i].win_cli_json("getpeerinfo")
            peer_hosts = {_addr_host(p.get("addr", "")) for p in peers}
            for node_j in range(node_i + 1, n + 1):
                idx_i, idx_j = node_i - 1, node_j - 1
                if gt[idx_i][idx_j] == 1:
                    j_host, j_port = self._address_info(node_j)
                    if j_host not in peer_hosts:
                        nodes_cli[node_i].win_cli_raw("addnode", f"{j_host}:{j_port}", "onetry", ignore=True)
                    connect_pairs.append((node_i, node_j))

        if connect_pairs:
            if ui:
                ui.update_setup("Waiting for connections...")
            self._poll_connects(connect_pairs, debug)

        if ui:
            ui.update_setup("Groundtruth setup complete.")

    def _poll_disconnects(self, pairs, debug):
        timeout = 30
        interval = 2
        elapsed = 0
        while True:
            while elapsed < timeout:
                remaining = []
                for node_i, node_j in pairs:
                    peers = nodes_cli[node_i].win_cli_json("getpeerinfo")
                    j_host, _ = self._address_info(node_j)
                    if any(_addr_host(p.get("addr", "")) == j_host for p in peers):
                        remaining.append((node_i, node_j))
                if not remaining:
                    return
                time.sleep(interval)
                elapsed += interval
            print(f"Disconnect timeout. Remaining connections: {remaining}", file=sys.stderr)

            ans = input("Wait 10s (Enter) / Halt (h): ").strip().lower()
            if ans == "h":
                sys.exit(1)

            timeout = 10
            elapsed = 0

    def _poll_connects(self, pairs, debug):
        timeout = 30
        interval = 2
        elapsed = 0

        while True:
            while elapsed < timeout:
                missing = []
                for node_i, node_j in pairs:
                    peers = nodes_cli[node_i].win_cli_json("getpeerinfo")
                    j_host, _ = self._address_info(node_j)
                    if not any(_addr_host(p.get("addr", "")) == j_host for p in peers):
                        missing.append((node_i, node_j))
                if not missing:
                    return
                time.sleep(interval)
                elapsed += interval
            print(f"Connect timeout. Missing connections: {missing}", file=sys.stderr)
            ans = input("Wait 10s (Enter) / Halt (h): ").strip().lower()
            if ans == "h":
                sys.exit(1)

            elapsed = 0
            timeout = 10

    def execute_topology_infer(self, round_infos, debug=False, ui=None):
        log_path = "./txprobe.log"
        if os.path.exists(log_path):
            os.remove(log_path)

        round_id = 0
        tot_rounds = len(round_infos)
        for ri in round_infos:
            if ui:
                ui.start_round(round_id, tot_rounds, ri.source_set, ri.sink_set)
            if ui:
                ui.update_phase(1, "running")
            subprocess.run(f"wsl {ri.phase_1_command}", shell=True, capture_output=not debug)
            if ui:
                ui.update_phase(1, "done")

            if ui:
                ui.update_phase(2, "running")
            subprocess.run(f"wsl {ri.phase_2_command}", shell=True, capture_output=not debug)
            if ui:
                ui.update_phase(2, "done")

            if ui:
                ui.update_phase(3, "running")
            subprocess.run(f"wsl {ri.phase_3_command}", shell=True, capture_output=not debug)
            if ui:
                ui.update_phase(3, "done")
                ui.finalize_round()

            round_infos += 1

        wait_seconds = 15
        if ui:
            ui.countdown("Propagation wait", wait_seconds)
        else:
            time.sleep(wait_seconds)

        peer_to_idx = {pid: idx for idx, pid in enumerate(self.vertices)}
        pattern = re.compile(r"received getdata for: \S+ ([0-9a-f]{64}) peer=(\d+)")

        with open(log_path) as f:
            log_lines = f.readlines()

        for ri_idx, ri in enumerate(round_infos):
            for j, marker in enumerate(ri.marker_txs):
                txid = marker["txid"]
                wtxid = marker["wtxid"]
                source_peer = ri.source_set[j]
                if source_peer not in peer_to_idx:
                    print(f'Did not found the peer {source_peer} in the list vertices!')
                    sys.exit(1)
                    continue
                idx_j = peer_to_idx[source_peer]

                for line in log_lines:
                    m = pattern.search(line)
                    if not m:
                        continue
                    log_hash = m.group(1)
                    log_peer = int(m.group(2))
                    if log_hash == txid or log_hash == wtxid:
                        if log_peer in peer_to_idx:
                            idx_k = peer_to_idx[log_peer]
                            self.inference[idx_j][idx_k] = 0
                            self.inference[idx_k][idx_j] = 0

    def inference_result(self):
        gt = self.groundtruth
        inf = self.inference
        n = self.n
        tp = tn = fp = fn = 0
        for i in range(n):
            for j in range(i + 1, n):
                if gt[i][j] == 1 and inf[i][j] == 1:
                    tp += 1
                elif gt[i][j] == 0 and inf[i][j] == 0:
                    tn += 1
                elif gt[i][j] == 0 and inf[i][j] == 1:
                    fp += 1
                elif gt[i][j] == 1 and inf[i][j] == 0:
                    fn += 1
        total = tp + tn + fp + fn
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        accuracy = (tp + tn) / total if total > 0 else 0.0
        return InferenceMetrics(
            groundtruth=gt, inference=inf,
            tp=tp, tn=tn, fp=fp, fn=fn,
            precision=precision, recall=recall, accuracy=accuracy,
        )
