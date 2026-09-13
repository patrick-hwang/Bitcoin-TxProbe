import sys
import time

from .classes.BitcoinCli.BitcoinCli import nodes_cli
from .utils import _addr_host

class node0Manager:
    @staticmethod
    def __poll_node0_connect(missing_nodes, tor_info, debug):
        timeout = 30
        interval = 2
        elapsed = 0

        while True:
            while elapsed < timeout:
                peers = nodes_cli[0].win_cli_json("getpeerinfo")
                connected = {_addr_host(p.get("addr", "")) for p in peers}
                still_missing = [nid for nid in missing_nodes if tor_info[nid][0] not in connected]
                if not still_missing:
                    return
                time.sleep(interval)
                elapsed += interval
            print(f"Still missing nodes: {still_missing}", file=sys.stderr)
            ans = input("Wait 30s (Enter) / Halt (h): ").strip().lower()
            if ans == "h":
                sys.exit(1)
            elapsed = 0

    @staticmethod
    # def get_vertices_from_node0(debug=False):
    def get_peerids_from_node0(debug=False):
        groundtruth_addresses = {}
        for node_id in range(1, 6):
            info = nodes_cli[node_id].win_cli_json("getnetworkinfo")
            la = info.get("localaddresses")
            if not la or len(la) == 0:
                print(f"Error: node {node_id} has no localaddresses", file=sys.stderr)
                sys.exit(1)
            host = la[0]["address"]
            port = la[0]["port"]
            groundtruth_addresses[node_id] = (host, port)
            if debug:
                print(f"Node {node_id} tor address: {host}:{port}", file=sys.stderr)

        peers = nodes_cli[0].wsl_cli_json("getpeerinfo")
        connected_hosts = {_addr_host(p.get("addr", "")) for p in peers}

        missing_nodes = []
        for node_id in range(1, 6):
            host, port = groundtruth_addresses[node_id]
            if host not in connected_hosts:
                missing_nodes.append(node_id)
                nodes_cli[0].wsl_cli_raw("addnode", f"{host}:{port}", "add", ignore=True)

        if missing_nodes:
            if debug:
                print(f"Connecting node 0 to missing nodes: {missing_nodes}", file=sys.stderr)
            node0Manager.__poll_node0_connect(missing_nodes, groundtruth_addresses, debug)

        peers = nodes_cli[0].wsl_cli_json("getpeerinfo")
        host_to_node = {host: groundtruth_node_id for groundtruth_node_id, (host, _) in groundtruth_addresses.items()}
        result = [None] * 5
        for p in peers:
            host = _addr_host(p.get("addr", ""))
            if host in host_to_node:
                node_id = host_to_node[host]
                result[node_id - 1] = p["id"]

        missing = [i + 1 for i, v in enumerate(result) if v is None]
        if missing:
            print(f"Error: cannot find peer IDs for nodes {missing} in node 0's peer list", file=sys.stderr)
            sys.exit(1)
            
        if debug:
            print(f"Vertices (peer IDs): {result}", file=sys.stderr)

        return result