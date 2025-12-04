# DCL Network Explorer

Interactive visualization tool for exploring the [Distributed Compliance Ledger (DCL)](https://github.com/zigbee-alliance/distributed-compliance-ledger) peer-to-peer network.

## Live Demo

**https://dcl-probe.vercel.app**

## Features

- **Interactive Network Graph** - Visualize all nodes and their connections
- **Real-time Discovery** - Crawls the network starting from seed nodes
- **Node Details** - Click any node to see IP, version, block height, etc.
- **Node Types** - Color-coded by role (Validator, Sentry, Observer, Seed)
- **Organization Grouping** - See which companies run which nodes
- **Export/Import** - Save network data as JSON

## How It Works

1. Queries seed nodes via the `/api/proxy` endpoint (CORS proxy)
2. For each node, fetches `/net_info` to discover connected peers
3. Recursively crawls until no new peers are found
4. Displays the network as an interactive force-directed graph

## Project Structure

```
├── public/
│   └── index.html      # Main web UI
├── api/
│   └── proxy.js        # Vercel serverless CORS proxy
├── discover_peers.py   # Python CLI for offline discovery
└── vercel.json         # Vercel configuration
```

## Local Development

### Web UI (requires Vercel CLI)

```bash
npm i -g vercel
vercel dev
```

### Python Script (no server needed)

```bash
python3 discover_peers.py
# Outputs network.json - can be loaded in web UI via "Load JSON" button
```

## Deployment

Deployed on [Vercel](https://vercel.com). Auto-deploys on push to `main`.

## Network Info

The DCL mainnet is a permissioned Cosmos SDK blockchain for Matter/IoT device certification. Nodes are operated by:

- CSA (Connectivity Standards Alliance)
- Amazon, Google, Samsung, Tuya, Lumi, and other member companies

Typical network size: ~60 nodes, ~200 connections

## License

MIT
