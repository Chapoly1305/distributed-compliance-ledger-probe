#!/usr/bin/env python3
"""
DCL Network Peer Discovery Script
Discovers all peers in the DCL network by crawling node RPC endpoints.
Outputs network.json for visualization in index.html
"""

import requests
import json
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Known seed/entry points
SEED_NODES = [
    "https://on.dcl.csa-iot.org:26657",
    "http://13.52.115.12:26657",  # CSA-Pub-SN-01
    "http://54.183.6.67:26657",   # Seed node
]

TIMEOUT = 5
discovered_peers = {}  # id -> {ip, port, moniker, version, ...}
edges = []  # [{source, target}, ...]
edge_set = set()  # For deduplication
visited_rpcs = set()


def is_private_ip(ip):
    """Check if IP is private/internal."""
    return (
        ip.startswith("10.") or
        ip.startswith("172.16.") or ip.startswith("172.17.") or
        ip.startswith("172.18.") or ip.startswith("172.19.") or
        ip.startswith("172.2") or ip.startswith("172.30.") or ip.startswith("172.31.") or
        ip.startswith("192.168.") or
        ip.startswith("127.")
    )


def get_node_type(moniker):
    """Determine node type from moniker."""
    m = moniker.lower()
    if "-vn-" in m or m.endswith("-vn"):
        return "validator"
    elif "-sn-" in m or "sentry" in m:
        return "sentry"
    elif "-on-" in m or "observer" in m:
        return "observer"
    elif "seed" in m:
        return "seed"
    return "unknown"


def get_org(moniker):
    """Extract organization from moniker."""
    if "-" in moniker:
        return moniker.split("-")[0]
    return moniker


def query_net_info(rpc_url):
    """Query /net_info endpoint and return peers."""
    try:
        resp = requests.get(f"{rpc_url}/net_info", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("peers", [])
    except:
        return []


def query_status(rpc_url):
    """Query /status endpoint for node info."""
    try:
        resp = requests.get(f"{rpc_url}/status", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        node_info = result.get("node_info", {})
        sync_info = result.get("sync_info", {})
        return {
            "id": node_info.get("id"),
            "moniker": node_info.get("moniker"),
            "version": node_info.get("version"),
            "height": sync_info.get("latest_block_height"),
        }
    except:
        return None


def query_abci_info(rpc_url):
    """Query /abci_info for app version."""
    try:
        resp = requests.get(f"{rpc_url}/abci_info", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("response", {}).get("version")
    except:
        return None


def add_edge(source_id, target_id):
    """Add an edge between two nodes."""
    edge_key = tuple(sorted([source_id, target_id]))
    if edge_key not in edge_set:
        edge_set.add(edge_key)
        edges.append({"source": source_id, "target": target_id})


def discover_from_node(source_id, rpc_url):
    """Discover peers from a single node and create edges."""
    if rpc_url in visited_rpcs:
        return []
    visited_rpcs.add(rpc_url)

    peers = query_net_info(rpc_url)
    new_peers = []

    for peer in peers:
        node_info = peer.get("node_info", {})
        peer_id = node_info.get("id")
        remote_ip = peer.get("remote_ip")

        if not peer_id or not remote_ip:
            continue
        if is_private_ip(remote_ip):
            continue

        # Add node if new
        if peer_id not in discovered_peers:
            moniker = node_info.get("moniker", "unknown")
            discovered_peers[peer_id] = {
                "id": peer_id,
                "ip": remote_ip,
                "port": 26656,
                "moniker": moniker,
                "tendermint_version": node_info.get("version", "unknown"),
                "type": get_node_type(moniker),
                "org": get_org(moniker),
                "rpc_url": f"http://{remote_ip}:26657",
                "rpc_accessible": False,
                "dcl_version": None,
                "height": None,
            }
            new_peers.append(peer_id)

        # Add edge
        if source_id:
            add_edge(source_id, peer_id)

    return new_peers


def crawl_network():
    """Crawl the network starting from seed nodes until no new peers."""
    print("Starting peer discovery...")

    # Start with seed nodes
    for seed in SEED_NODES:
        print(f"  Querying seed: {seed}")
        status = query_status(seed)
        if status and status.get("id"):
            seed_id = status["id"]
            ip = seed.replace("https://", "").replace("http://", "").split(":")[0]
            moniker = status.get("moniker", "unknown")
            dcl_version = query_abci_info(seed)

            discovered_peers[seed_id] = {
                "id": seed_id,
                "ip": ip,
                "port": 26656,
                "moniker": moniker,
                "tendermint_version": status.get("version", "unknown"),
                "type": get_node_type(moniker),
                "org": get_org(moniker),
                "rpc_url": seed,
                "rpc_accessible": True,
                "dcl_version": dcl_version,
                "height": status.get("height"),
            }
            discover_from_node(seed_id, seed)

    print(f"  Found {len(discovered_peers)} peers from seeds")

    # Crawl until no new peers
    iteration = 1
    while True:
        peers_to_query = [
            (pid, p["rpc_url"]) for pid, p in discovered_peers.items()
            if p["rpc_url"] not in visited_rpcs
        ]

        if not peers_to_query:
            print(f"  Iteration {iteration}: No new peers to query")
            break

        print(f"  Iteration {iteration}: Querying {len(peers_to_query)} peers...")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(discover_from_node, pid, url): pid
                for pid, url in peers_to_query
            }
            for future in as_completed(futures):
                pass

        print(f"  Total peers: {len(discovered_peers)}, edges: {len(edges)}")
        iteration += 1

    return discovered_peers


def check_rpc_accessibility():
    """Check which peers have accessible RPC."""
    print("\nChecking RPC accessibility...")

    accessible = []

    def check_peer(peer_id, peer_info):
        if peer_info.get("rpc_accessible"):
            return peer_id  # Already checked (seed nodes)

        status = query_status(peer_info["rpc_url"])
        if status:
            peer_info["rpc_accessible"] = True
            peer_info["dcl_version"] = query_abci_info(peer_info["rpc_url"])
            peer_info["height"] = status.get("height")
            return peer_id
        return None

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(check_peer, pid, pinfo): pid
            for pid, pinfo in discovered_peers.items()
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                accessible.append(result)

    print(f"  {len(accessible)} peers have accessible RPC")
    return accessible


def print_results(accessible_peers):
    """Print discovery results."""
    print("\n" + "=" * 80)
    print("DISCOVERY RESULTS")
    print("=" * 80)

    print(f"\nTotal peers discovered: {len(discovered_peers)}")
    print(f"Total connections: {len(edges)}")
    print(f"Peers with accessible RPC: {len(accessible_peers)}")

    # Group by organization
    orgs = {}
    for pid, pinfo in discovered_peers.items():
        org = pinfo["org"]
        if org not in orgs:
            orgs[org] = []
        orgs[org].append(pinfo)

    print(f"\nOrganizations ({len(orgs)}):")
    for org in sorted(orgs.keys()):
        print(f"  {org}: {len(orgs[org])} nodes")

    # Print accessible nodes
    print("\n" + "-" * 80)
    print("ACCESSIBLE RPC NODES")
    print("-" * 80)
    print(f"{'Moniker':<40} {'IP':<18} {'DCL Ver':<10} {'Height':<10}")
    print("-" * 80)

    for pid in sorted(accessible_peers, key=lambda x: discovered_peers[x]["moniker"]):
        p = discovered_peers[pid]
        print(f"{p['moniker']:<40} {p['ip']:<18} {p.get('dcl_version', 'N/A') or 'N/A':<10} {p.get('height', 'N/A') or 'N/A':<10}")

    # Print persistent_peers format
    print("\n" + "-" * 80)
    print("PERSISTENT PEERS (for config.toml)")
    print("-" * 80)
    peers_str = ",".join([
        f"{pid}@{discovered_peers[pid]['ip']}:26656"
        for pid in accessible_peers[:10]
    ])
    print(f"persistent_peers = \"{peers_str}\"")

    # Save network.json for HTML visualization
    output = {
        "nodes": discovered_peers,
        "edges": edges,
        "exported_at": datetime.now().isoformat(),
    }
    with open("network.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n" + "-" * 80)
    print("Network data saved to: network.json")
    print("Open index.html and click 'Load JSON' to visualize")


def main():
    crawl_network()
    accessible = check_rpc_accessibility()
    print_results(accessible)


if __name__ == "__main__":
    main()
