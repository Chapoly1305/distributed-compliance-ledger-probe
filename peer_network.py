#!/usr/bin/env python3
"""
DCL Network Peer Discovery and Visualization
Interactive web-based network graph showing peer relationships.
"""

import requests
import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
import socket

# Known seed/entry points
SEED_NODES = [
    ("https://on.dcl.csa-iot.org:26657", "CSA-ON-01"),
    ("http://13.52.115.12:26657", "CSA-Pub-SN-01"),
]

TIMEOUT = 5

# Global state
network = {
    "nodes": {},      # id -> {ip, port, moniker, version, rpc_accessible, ...}
    "edges": [],      # [{source, target}, ...]
    "discovery_log": [],
    "status": "idle",
    "stats": {"total_nodes": 0, "total_edges": 0, "accessible_rpc": 0}
}
visited_rpcs = set()
edge_set = set()  # For deduplication
lock = threading.Lock()


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


def log(msg):
    """Add to discovery log."""
    with lock:
        timestamp = time.strftime("%H:%M:%S")
        network["discovery_log"].append(f"[{timestamp}] {msg}")
        if len(network["discovery_log"]) > 100:
            network["discovery_log"] = network["discovery_log"][-100:]
        print(f"[{timestamp}] {msg}")


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


def get_node_type(moniker):
    """Determine node type from moniker."""
    moniker_lower = moniker.lower()
    if "-vn-" in moniker_lower or moniker_lower.endswith("-vn"):
        return "validator"
    elif "-sn-" in moniker_lower or "sentry" in moniker_lower:
        return "sentry"
    elif "-on-" in moniker_lower or "observer" in moniker_lower:
        return "observer"
    elif "seed" in moniker_lower:
        return "seed"
    else:
        return "unknown"


def get_org(moniker):
    """Extract organization from moniker."""
    if "-" in moniker:
        return moniker.split("-")[0]
    return moniker


def add_node(peer_id, ip, port, moniker, version, rpc_accessible=False, dcl_version=None, height=None):
    """Add or update a node."""
    with lock:
        if peer_id not in network["nodes"]:
            network["nodes"][peer_id] = {
                "id": peer_id,
                "ip": ip,
                "port": port,
                "moniker": moniker,
                "tendermint_version": version,
                "rpc_accessible": rpc_accessible,
                "dcl_version": dcl_version,
                "height": height,
                "type": get_node_type(moniker),
                "org": get_org(moniker),
                "rpc_url": f"http://{ip}:26657",
            }
            network["stats"]["total_nodes"] = len(network["nodes"])
        else:
            # Update existing node with new info
            if rpc_accessible:
                network["nodes"][peer_id]["rpc_accessible"] = True
            if dcl_version:
                network["nodes"][peer_id]["dcl_version"] = dcl_version
            if height:
                network["nodes"][peer_id]["height"] = height


def add_edge(source_id, target_id):
    """Add an edge between two nodes."""
    edge_key = tuple(sorted([source_id, target_id]))
    with lock:
        if edge_key not in edge_set:
            edge_set.add(edge_key)
            network["edges"].append({"source": source_id, "target": target_id})
            network["stats"]["total_edges"] = len(network["edges"])


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

        # Add node
        add_node(
            peer_id=peer_id,
            ip=remote_ip,
            port=26656,
            moniker=node_info.get("moniker", "unknown"),
            version=node_info.get("version", "unknown"),
        )

        # Add edge from source to this peer
        if source_id:
            add_edge(source_id, peer_id)

        if peer_id not in [p for p in network["nodes"] if network["nodes"].get(p, {}).get("_discovered")]:
            new_peers.append(peer_id)

    return new_peers


def crawl_worker(peer_id):
    """Worker function to crawl a single peer."""
    peer_info = network["nodes"].get(peer_id)
    if not peer_info:
        return

    rpc_url = peer_info["rpc_url"]
    log(f"Crawling {peer_info['moniker']} ({peer_info['ip']})")

    # Check RPC accessibility and get details
    status = query_status(rpc_url)
    if status:
        dcl_version = query_abci_info(rpc_url)
        add_node(
            peer_id=peer_id,
            ip=peer_info["ip"],
            port=peer_info["port"],
            moniker=peer_info["moniker"],
            version=peer_info["tendermint_version"],
            rpc_accessible=True,
            dcl_version=dcl_version,
            height=status.get("height"),
        )
        with lock:
            network["stats"]["accessible_rpc"] = sum(
                1 for n in network["nodes"].values() if n.get("rpc_accessible")
            )

    # Discover peers from this node
    discover_from_node(peer_id, rpc_url)

    with lock:
        network["nodes"][peer_id]["_discovered"] = True


def start_discovery():
    """Start the discovery process."""
    with lock:
        network["status"] = "discovering"
        network["nodes"] = {}
        network["edges"] = []
        network["discovery_log"] = []
        network["stats"] = {"total_nodes": 0, "total_edges": 0, "accessible_rpc": 0}
        visited_rpcs.clear()
        edge_set.clear()

    log("Starting peer discovery...")

    # Add seed nodes first
    for rpc_url, moniker in SEED_NODES:
        log(f"Querying seed: {moniker}")
        status = query_status(rpc_url)
        if status:
            seed_id = status.get("id")
            if seed_id:
                dcl_version = query_abci_info(rpc_url)
                add_node(
                    peer_id=seed_id,
                    ip=rpc_url.split("//")[1].split(":")[0],
                    port=26656,
                    moniker=moniker,
                    version=status.get("version", "unknown"),
                    rpc_accessible=True,
                    dcl_version=dcl_version,
                    height=status.get("height"),
                )
                discover_from_node(seed_id, rpc_url)
                network["nodes"][seed_id]["_discovered"] = True

    log(f"Found {len(network['nodes'])} peers from seeds")

    # Continuous crawling until no new peers
    while True:
        with lock:
            peers_to_crawl = [
                pid for pid, pinfo in network["nodes"].items()
                if not pinfo.get("_discovered") and pinfo["rpc_url"] not in visited_rpcs
            ]

        if not peers_to_crawl:
            break

        log(f"Crawling {len(peers_to_crawl)} new peers...")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(crawl_worker, pid) for pid in peers_to_crawl]
            for future in as_completed(futures):
                pass

    with lock:
        network["status"] = "complete"
    log(f"Discovery complete. {len(network['nodes'])} nodes, {len(network['edges'])} connections")


class RequestHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for API and static files."""

    def do_GET(self):
        if self.path == "/api/network":
            self.send_json(network)
        elif self.path == "/api/start":
            if network["status"] != "discovering":
                threading.Thread(target=start_discovery, daemon=True).start()
                self.send_json({"status": "started"})
            else:
                self.send_json({"status": "already_running"})
        elif self.path == "/api/status":
            self.send_json({
                "status": network["status"],
                "stats": network["stats"],
                "log": network["discovery_log"][-20:],
            })
        elif self.path == "/" or self.path == "/index.html":
            self.send_html()
        else:
            self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        # Clean data for JSON serialization (remove internal fields)
        clean_data = json.loads(json.dumps(data, default=str))
        self.wfile.write(json.dumps(clean_data).encode())

    def send_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode())

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


HTML_PAGE = '''<!DOCTYPE html>
<html>
<head>
    <title>DCL Network Explorer</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
            background: #0d1117;
            color: #c9d1d9;
            overflow: hidden;
        }
        #container { display: flex; height: 100vh; }
        #sidebar {
            width: 350px;
            background: #161b22;
            border-right: 1px solid #30363d;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        #graph { flex: 1; position: relative; }
        h1 {
            padding: 16px;
            font-size: 18px;
            border-bottom: 1px solid #30363d;
            background: #0d1117;
        }
        .section { padding: 12px 16px; border-bottom: 1px solid #30363d; }
        .section h2 { font-size: 12px; color: #8b949e; margin-bottom: 8px; text-transform: uppercase; }
        button {
            background: #238636;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            width: 100%;
        }
        button:hover { background: #2ea043; }
        button:disabled { background: #30363d; cursor: not-allowed; }
        .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .stat {
            background: #0d1117;
            padding: 12px;
            border-radius: 6px;
            text-align: center;
        }
        .stat-value { font-size: 24px; font-weight: bold; color: #58a6ff; }
        .stat-label { font-size: 11px; color: #8b949e; margin-top: 4px; }
        #log {
            flex: 1;
            overflow-y: auto;
            padding: 12px 16px;
            font-size: 11px;
            font-family: monospace;
            background: #0d1117;
        }
        .log-entry { padding: 2px 0; color: #8b949e; }
        #node-info {
            position: absolute;
            top: 16px;
            right: 16px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px;
            min-width: 280px;
            display: none;
            font-size: 13px;
        }
        #node-info h3 { margin-bottom: 12px; color: #58a6ff; }
        #node-info .row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #21262d;
        }
        #node-info .label { color: #8b949e; }
        #node-info .value { color: #c9d1d9; }
        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
        }
        .legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }
        svg { width: 100%; height: 100%; }
        .node { cursor: pointer; }
        .node circle { stroke: #30363d; stroke-width: 1.5px; }
        .node text { font-size: 10px; fill: #8b949e; pointer-events: none; }
        .node.highlighted circle { stroke: #f0883e; stroke-width: 3px; }
        .link { stroke: #30363d; stroke-opacity: 0.6; }
        .link.highlighted { stroke: #f0883e; stroke-opacity: 1; stroke-width: 2px; }
        #controls {
            position: absolute;
            bottom: 16px;
            left: 16px;
            display: flex;
            gap: 8px;
        }
        #controls button {
            width: auto;
            padding: 6px 12px;
            font-size: 12px;
            background: #21262d;
        }
        #controls button:hover { background: #30363d; }
    </style>
</head>
<body>
    <div id="container">
        <div id="sidebar">
            <h1>DCL Network Explorer</h1>
            <div class="section">
                <button id="startBtn" onclick="startDiscovery()">Start Discovery</button>
            </div>
            <div class="section">
                <h2>Statistics</h2>
                <div class="stats">
                    <div class="stat">
                        <div class="stat-value" id="nodeCount">0</div>
                        <div class="stat-label">Nodes</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="edgeCount">0</div>
                        <div class="stat-label">Connections</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="rpcCount">0</div>
                        <div class="stat-label">RPC Accessible</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="orgCount">0</div>
                        <div class="stat-label">Organizations</div>
                    </div>
                </div>
            </div>
            <div class="section">
                <h2>Legend</h2>
                <div class="legend">
                    <div class="legend-item"><div class="legend-dot" style="background:#f97583"></div> Validator</div>
                    <div class="legend-item"><div class="legend-dot" style="background:#56d364"></div> Sentry</div>
                    <div class="legend-item"><div class="legend-dot" style="background:#58a6ff"></div> Observer</div>
                    <div class="legend-item"><div class="legend-dot" style="background:#d29922"></div> Seed</div>
                    <div class="legend-item"><div class="legend-dot" style="background:#8b949e"></div> Unknown</div>
                </div>
            </div>
            <div class="section" style="flex-shrink: 0;">
                <h2>Discovery Log</h2>
            </div>
            <div id="log"></div>
        </div>
        <div id="graph">
            <svg></svg>
            <div id="node-info"></div>
            <div id="controls">
                <button onclick="zoomIn()">Zoom +</button>
                <button onclick="zoomOut()">Zoom -</button>
                <button onclick="resetZoom()">Reset</button>
            </div>
        </div>
    </div>

    <script>
        const typeColors = {
            validator: "#f97583",
            sentry: "#56d364",
            observer: "#58a6ff",
            seed: "#d29922",
            unknown: "#8b949e"
        };

        let simulation, svg, g, link, node, zoom;
        let networkData = { nodes: {}, edges: [] };

        function initGraph() {
            svg = d3.select("svg");
            const width = svg.node().parentElement.clientWidth;
            const height = svg.node().parentElement.clientHeight;

            zoom = d3.zoom()
                .scaleExtent([0.1, 4])
                .on("zoom", (event) => g.attr("transform", event.transform));

            svg.call(zoom);
            g = svg.append("g");

            link = g.append("g").attr("class", "links").selectAll("line");
            node = g.append("g").attr("class", "nodes").selectAll("g");

            simulation = d3.forceSimulation()
                .force("link", d3.forceLink().id(d => d.id).distance(80))
                .force("charge", d3.forceManyBody().strength(-200))
                .force("center", d3.forceCenter(width / 2, height / 2))
                .force("collision", d3.forceCollide().radius(30));

            simulation.on("tick", () => {
                link.attr("x1", d => d.source.x)
                    .attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x)
                    .attr("y2", d => d.target.y);

                node.attr("transform", d => `translate(${d.x},${d.y})`);
            });
        }

        function updateGraph(data) {
            const nodes = Object.values(data.nodes);
            const edges = data.edges.filter(e =>
                data.nodes[e.source] && data.nodes[e.target]
            );

            // Update links
            link = link.data(edges, d => `${d.source}-${d.target}`);
            link.exit().remove();
            link = link.enter().append("line")
                .attr("class", "link")
                .merge(link);

            // Update nodes
            node = node.data(nodes, d => d.id);
            node.exit().remove();

            const nodeEnter = node.enter().append("g")
                .attr("class", "node")
                .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended))
                .on("click", showNodeInfo)
                .on("mouseover", highlightConnections)
                .on("mouseout", clearHighlight);

            nodeEnter.append("circle")
                .attr("r", d => d.rpc_accessible ? 12 : 8)
                .attr("fill", d => typeColors[d.type] || typeColors.unknown);

            nodeEnter.append("text")
                .attr("dy", 20)
                .attr("text-anchor", "middle")
                .text(d => d.moniker.length > 15 ? d.moniker.slice(0, 15) + "..." : d.moniker);

            node = nodeEnter.merge(node);

            // Update simulation
            simulation.nodes(nodes);
            simulation.force("link").links(edges);
            simulation.alpha(0.3).restart();

            // Update stats
            const orgs = new Set(nodes.map(n => n.org));
            document.getElementById("nodeCount").textContent = nodes.length;
            document.getElementById("edgeCount").textContent = edges.length;
            document.getElementById("rpcCount").textContent = nodes.filter(n => n.rpc_accessible).length;
            document.getElementById("orgCount").textContent = orgs.size;
        }

        function showNodeInfo(event, d) {
            const info = document.getElementById("node-info");
            info.style.display = "block";
            info.innerHTML = `
                <h3>${d.moniker}</h3>
                <div class="row"><span class="label">Type</span><span class="value">${d.type}</span></div>
                <div class="row"><span class="label">Organization</span><span class="value">${d.org}</span></div>
                <div class="row"><span class="label">IP</span><span class="value">${d.ip}</span></div>
                <div class="row"><span class="label">ID</span><span class="value" style="font-size:10px">${d.id}</span></div>
                <div class="row"><span class="label">RPC Accessible</span><span class="value">${d.rpc_accessible ? "Yes" : "No"}</span></div>
                <div class="row"><span class="label">DCL Version</span><span class="value">${d.dcl_version || "N/A"}</span></div>
                <div class="row"><span class="label">Height</span><span class="value">${d.height || "N/A"}</span></div>
                <div class="row"><span class="label">Tendermint</span><span class="value">${d.tendermint_version}</span></div>
            `;
        }

        function highlightConnections(event, d) {
            const connectedIds = new Set();
            connectedIds.add(d.id);

            link.classed("highlighted", l => {
                if (l.source.id === d.id || l.target.id === d.id) {
                    connectedIds.add(l.source.id);
                    connectedIds.add(l.target.id);
                    return true;
                }
                return false;
            });

            node.classed("highlighted", n => connectedIds.has(n.id));
        }

        function clearHighlight() {
            link.classed("highlighted", false);
            node.classed("highlighted", false);
        }

        function dragstarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragended(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }

        function zoomIn() { svg.transition().call(zoom.scaleBy, 1.3); }
        function zoomOut() { svg.transition().call(zoom.scaleBy, 0.7); }
        function resetZoom() {
            svg.transition().call(zoom.transform, d3.zoomIdentity);
        }

        async function startDiscovery() {
            document.getElementById("startBtn").disabled = true;
            document.getElementById("startBtn").textContent = "Discovering...";
            await fetch("/api/start");
            pollStatus();
        }

        async function pollStatus() {
            try {
                const resp = await fetch("/api/status");
                const data = await resp.json();

                // Update log
                const logEl = document.getElementById("log");
                logEl.innerHTML = data.log.map(l => `<div class="log-entry">${l}</div>`).join("");
                logEl.scrollTop = logEl.scrollHeight;

                if (data.status === "discovering" || data.stats.total_nodes > Object.keys(networkData.nodes).length) {
                    // Fetch full network data
                    const netResp = await fetch("/api/network");
                    networkData = await netResp.json();
                    updateGraph(networkData);
                }

                if (data.status === "discovering") {
                    setTimeout(pollStatus, 1000);
                } else {
                    document.getElementById("startBtn").disabled = false;
                    document.getElementById("startBtn").textContent = "Restart Discovery";
                }
            } catch (e) {
                setTimeout(pollStatus, 2000);
            }
        }

        // Initialize
        initGraph();

        // Check if there's existing data
        fetch("/api/network").then(r => r.json()).then(data => {
            if (Object.keys(data.nodes).length > 0) {
                networkData = data;
                updateGraph(data);
            }
        });

        // Handle resize
        window.addEventListener("resize", () => {
            const width = svg.node().parentElement.clientWidth;
            const height = svg.node().parentElement.clientHeight;
            simulation.force("center", d3.forceCenter(width / 2, height / 2));
            simulation.alpha(0.1).restart();
        });
    </script>
</body>
</html>
'''


def main():
    port = 8080

    # Find available port
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('', port))
            sock.close()
            break
        except OSError:
            port += 1

    server = HTTPServer(('0.0.0.0', port), RequestHandler)
    print(f"=" * 60)
    print(f"DCL Network Explorer")
    print(f"=" * 60)
    print(f"Open in browser: http://localhost:{port}")
    print(f"Press Ctrl+C to stop")
    print(f"=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
