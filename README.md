# Sample Local MCP Server

A minimal [Model Context Protocol](https://modelcontextprotocol.io/) server built with
[FastMCP](https://github.com/jlowin/fastmcp). It exposes a handful of demo tools (math,
random number, server time, text analysis, echo) over **SSE** on `http://localhost:8000`,
so you can wire it into an MCP-aware client such as VS Code Copilot Chat, Claude
Desktop, or any custom agent.

## Project structure

```
sample-mcp-server-script/
├── .gitignore
├── .vscode/
│   └── mcp.json            # Example VS Code MCP client config
├── README.md
├── requirements.txt        # Python dependencies (fastmcp)
└── sample-mcp-server.py    # The MCP server entrypoint
```

## Tools exposed

| Tool             | Description                                              |
| ---------------- | -------------------------------------------------------- |
| `calculate`      | Evaluate a safe math expression, e.g. `2 + 2 * 10`.      |
| `get_server_time`| Return the current server time (UTC).                    |
| `random_number`  | Random int between `min_val` and `max_val`.              |
| `analyze_text`   | Word / character / sentence stats for a text blob.       |
| `echo`           | Echoes a message back — handy for connectivity testing.  |

## Prerequisites

- Python 3.10+ (3.11 recommended)
- `pip` and `venv` available

## Setup

From the project root:

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

## Run the server

```bash
# With the venv activated:
python sample-mcp-server.py
```

You should see FastMCP start an SSE server on port `8000`. The SSE endpoint is:

```
http://localhost:8000/sse
```

Leave this terminal running while you use the server from a client.

## Verify it's running

In another terminal:

```bash
curl -N http://localhost:8000/sse
```

You should get a streaming response (press `Ctrl+C` to stop). If the connection opens
and stays open, the server is healthy.

## Use it from VS Code Copilot Chat

A ready-to-use config is included at [.vscode/mcp.json](.vscode/mcp.json):

```json
{
  "servers": {
    "local-sample-mcp": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

Steps:

1. Make sure the server is running (`python sample-mcp-server.py`).
2. Open this folder in VS Code.
3. Open Copilot Chat and switch to **Agent** mode.
4. Click the tools picker — the `local-sample-mcp` server and its tools should appear.
5. Ask something like: *"Use the calculate tool to compute 12 * (3 + 4)"* or
   *"Call analyze_text on this paragraph."*

## Use it from Claude Desktop

Claude Desktop currently launches MCP servers via stdio, so the easiest path is to use
[`mcp-proxy`](https://github.com/sparfenyuk/mcp-proxy) to bridge stdio → SSE. Add an
entry like this to your Claude Desktop config:

```json
{
  "mcpServers": {
    "local-sample-mcp": {
      "command": "mcp-proxy",
      "args": ["http://localhost:8000/sse"]
    }
  }
}
```

Then start the Python server in a terminal as shown above.

## Switching to stdio transport (optional)

If you prefer running over stdio (no port needed), change the last line of
[sample-mcp-server.py](sample-mcp-server.py) from:

```python
mcp.run(transport="sse", host="0.0.0.0", port=8000)
```

to:

```python
mcp.run(transport="stdio")
```

And update your client config to launch the script directly, e.g.:

```json
{
  "servers": {
    "local-sample-mcp": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/sample-mcp-server.py"]
    }
  }
}
```

## Troubleshooting

- **`ModuleNotFoundError: No module named 'fastmcp'`** — activate the venv and rerun
  `pip install -r requirements.txt`.
- **Port 8000 already in use** — change the `port=8000` argument in
  `sample-mcp-server.py`, and update the `url` in `.vscode/mcp.json` to match.
- **VS Code doesn't see the server** — restart the MCP server from the Copilot Chat
  tools picker, or reload the VS Code window.
- **`calculate` returns an error** — only `0-9`, `+`, `-`, `*`, `/`, `(`, `)`, `.`, and
  spaces are accepted (intentional safety restriction).

## License

Sample / demo code — use freely.
