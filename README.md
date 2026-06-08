# Signal

AI-Powered Virtual Display Platform

## Quick Start

```bash
npm install
npm start
```

Open http://localhost:4888

## Environment

Copy `.env.example` to `.env` and fill in your MySQL credentials:

```
DB_HOST=your-rds-host.amazonaws.com
DB_USER=admin
DB_PASSWORD=your-password
DB_NAME=signal
PORT=4888
```

## Commands

| Command | What it does |
|---------|-------------|
| `npm start` | Start the server (web + MCP, single process) |

## How It Works

1. Visit the landing page and click **Get Started**
2. You get a unique URL like `/s/a7f3x9k2`
3. The home page shows your **MCP Endpoint** — copy it
4. Add that URL as a custom MCP connector in **Claude.ai → Settings → Connectors**
5. Tell Claude to push content to your displays

## MCP Tools

| Tool | Description |
|------|-------------|
| `create_device` | Register a new virtual display |
| `list_devices` | Show all displays |
| `push_content` | Send content (text, markdown, html, url, image, list, dashboard) |
| `clear_device` | Clear a display |
| `delete_device` | Remove a display |

## Content Types

| Type | Body | Example |
|------|------|---------|
| `text` | Plain string | `"Hello world"` |
| `markdown` | Markdown string | `"# Title\n\nSome text"` |
| `html` | HTML string | `"<h1>Hello</h1>"` |
| `url` | URL (rendered in iframe) | `"https://example.com"` |
| `image` | Image URL | `"https://example.com/photo.jpg"` |
| `list` | JSON array | `'["item1", {"text":"item2","checked":true}]'` |
| `dashboard` | JSON array of cards | `'[{"title":"Users","value":"1.2k"}]'` |

## URL Structure

```
/                              Landing page
/s/:namespace                  Home (device grid + MCP endpoint)
/s/:namespace/display/:device  Full display view
/s/:namespace/mcp              MCP endpoint (for Claude.ai connector)
/s/:namespace/api/devices      REST API
/health                        Health check
```

## Logs

The server logs WebSocket connections, broadcasts, and API calls to stdout:

```
[WS] Connected: abc123:_global (1 clients)
[WS] Broadcast abc123:_global: device_created → 1 clients
[WS] Broadcast abc123:_global: device_updated → 1 clients
[API] POST /s/abc123/api/devices
[API] PATCH /s/abc123/api/devices/thPRR7kb
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full architecture writeup.
