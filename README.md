# Unofficial DCL Network Probe

Interactive visualization tool for exploring the [Distributed Compliance Ledger (DCL)](https://github.com/zigbee-alliance/distributed-compliance-ledger) peer-to-peer network.

> **Note:** This is an unofficial community tool and is not affiliated with the Connectivity Standards Alliance (CSA).

## Live Demo

**https://dcl-probe.vercel.app**

## Features

- **Interactive Network Graph** - Force-directed D3.js visualization of all nodes and connections
- **Real-time Discovery** - Crawls the network starting from configurable seed nodes
- **Node Details** - Click any node to see IP, moniker, version, block height, DCL version, and connection count
- **Node Types** - Color-coded by role (Validator, Sentry, Observer, Seed, Unknown)
- **Organization Grouping** - Nodes grouped by organization prefix in their monikers
- **Multiple Layout Modes** - Force-directed, radial, or cluster-by-organization layouts
- **Export Options** - Save network data as JSON or export the graph as PDF
- **Import/Continue** - Load previously exported JSON and continue discovery from known nodes
- **Customizable Display** - Theme (dark/light), link opacity/width, node size, label visibility
- **Auto-refresh** - Optional periodic re-discovery (1/5/10/30 minutes)

## How It Works

1. Starts with seed node URLs (configurable in the UI)
2. Queries each node's `/status` endpoint to get node info
3. Fetches `/net_info` to discover connected peers
4. Queries `/abci_info` for DCL application version
5. Recursively crawls all discovered peers
6. Displays the network as an interactive graph with D3.js

The app uses a Vercel serverless proxy (`/api/proxy`) to handle CORS for HTTP endpoints. HTTPS endpoints (like `on.dcl.csa-iot.org`) are queried directly.

## Project Structure

```
├── public/
│   └── index.html      # Single-page web application (HTML + CSS + JS)
├── api/
│   └── proxy.js        # Vercel serverless CORS proxy function
└── vercel.json         # Vercel deployment configuration
```

## Local Development

Requires [Vercel CLI](https://vercel.com/cli) for the serverless proxy:

```bash
npm i -g vercel
vercel dev
```

Then open http://localhost:3000

## Deployment

Deployed on [Vercel](https://vercel.com). Auto-deploys on push to `main`.

## Network Info

The DCL mainnet is a permissioned Cosmos SDK blockchain for Matter/IoT device certification. Nodes are operated by:

- CSA (Connectivity Standards Alliance)
- Amazon, Google, Samsung, Tuya, Lumi, and other member companies

Typical network size: ~60 nodes, ~200 connections

## License

MIT
