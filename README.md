# Sample Local MCP Server

A minimal [Model Context Protocol](https://modelcontextprotocol.io/) server built with
[FastMCP](https://github.com/jlowin/fastmcp). It exposes a handful of demo tools (math,
random number, server time, text analysis, echo) over **SSE** on `http://localhost:8000`,
so you can wire it into an MCP-aware client such as VS Code Copilot Chat, Claude
Desktop, or any custom agent.

## Project structure

```
sample-mcp-server-script/
├── server/                  # The MCP server
│   ├── __init__.py
│   ├── __main__.py          # enables `python -m server`
│   ├── app.py               # FastMCP app + tools + resources + prompts
│   └── notes_db.py          # SQLite-backed notes store
├── clients/                 # Ways to talk to the server
│   ├── cli.py               # CLI: list / call / smoke
│   └── streamlit_app.py     # Streamlit UI
├── tests/                   # pytest suite
│   ├── test_notes_db.py
│   └── test_server.py
├── docs/                    # Misc notes
│   ├── instructions.txt
│   └── testing_server.txt
├── data/                    # Local SQLite DB + logs (gitignored)
├── Dockerfile
├── .dockerignore
├── .gitignore
├── README.md
└── requirements.txt
```

## Tools exposed

| Tool                | Description                                                              |
| ------------------- | ------------------------------------------------------------------------ |
| `calculate`         | Evaluate a safe math expression, e.g. `2 + 2 * 10`.                      |
| `get_server_time`   | Return the current server time (UTC).                                    |
| `random_number`     | Random int between `min_val` and `max_val`.                              |
| `analyze_text`      | Word / character / sentence stats for a text blob.                       |
| `echo`              | Echoes a message back — handy for connectivity testing.                  |
| `hash_text`         | MD5/SHA1/SHA256/SHA512 hash of a string.                                 |
| `base64_encode`     | Base64-encode a string (standard or URL-safe alphabet).                  |
| `base64_decode`     | Decode a base64 string back to UTF-8 text.                               |
| `uuid_generate`     | Generate one or more UUIDs (v1 or v4).                                   |
| `password_generate` | Cryptographically strong random password with configurable charset.      |
| `json_format`       | Pretty-print and validate a JSON string.                                 |
| `regex_match`       | Find all matches of a regex pattern in text (first 50, with groups).     |
| `convert_units`     | Convert length / weight / temperature between common units.              |
| `fetch_url`         | HTTP GET/HEAD an http(s) URL and return status, headers, truncated body. |
| `weather`           | Current weather for a lat/lon via the free Open-Meteo API (no key).      |
| `note_add`          | Create a new note (title + body) in the local SQLite store.              |
| `note_list`         | List recent notes, newest first. Optional substring search.              |
| `note_get`          | Fetch a single note by id.                                               |
| `note_update`       | Update a note's title and/or body.                                       |
| `note_delete`       | Delete a note by id.                                                     |

## Resources exposed

| URI                          | Description                                              |
| ---------------------------- | -------------------------------------------------------- |
| `resource://server/info`     | Server metadata: name, version, uptime, notes count.     |
| `resource://notes/all`       | All notes (max 500), newest first.                       |
| `resource://notes/{note_id}` | A single note by id, e.g. `resource://notes/3`.          |

## Prompts exposed

| Prompt           | Description                                                  |
| ---------------- | ------------------------------------------------------------ |
| `summarize_text` | Summarize a text blob in a chosen style.                     |
| `code_review`    | Structured code review (bugs / security / improvements).     |
| `explain_error`  | Plain-language explanation of an error + likely fixes.       |

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
python -m server
```

You should see FastMCP start an SSE server on port `8000`. The SSE endpoint is:

```
http://localhost:8000/sse
```

Leave this terminal running while you use the server from a client.

------------------------------------

  ## To the point commands for testing -

  How to use the tool -

  ## Terminal 1 (server, leave running):

  source .venv/bin/activate
  python -m server
  python -m server --log-level DEBUG --log-file data/mcp.log

  --------------------------

  ## Terminal 2 — Streamlit UI:

  source .venv/bin/activate
  streamlit run clients/streamlit_app.py

  --------------------------------------------


### CLI flags

```bash
python -m server --help

# Examples
python -m server --transport stdio
python -m server --transport sse --host 127.0.0.1 --port 9000
python -m server --log-level DEBUG --log-file data/mcp.log
```

All flags can also be set via environment variables: `MCP_TRANSPORT`, `MCP_HOST`,
`MCP_PORT`, `MCP_LOG_LEVEL`, `MCP_LOG_FILE`, `MCP_NOTES_DB`.

## Verify it's running

In another terminal:

```bash
curl -N http://localhost:8000/sse
```

You should get a streaming response (press `Ctrl+C` to stop). If the connection opens
and stays open, the server is healthy.

## Test from the terminal

Two convenient clients are included.

### 1. CLI harness — `clients/cli.py`

```bash
source .venv/bin/activate

# List every tool the server exposes
python -m clients.cli list

# Call any tool (arguments are a JSON object)
python -m clients.cli call echo --args '{"message": "hello"}'
python -m clients.cli call password_generate --args '{"length": 32, "use_symbols": true}'
python -m clients.cli call weather --args '{"latitude": 28.6139, "longitude": 77.2090}'

# Run a small predefined smoke suite that exercises ~9 tools
python -m clients.cli smoke

# Point at a non-default URL
python -m clients.cli --url http://localhost:9000/sse list
```

### 2. Streamlit UI — `clients/streamlit_app.py`

A zero-config web UI that lists tools, auto-renders a form from each tool's
input schema, and shows results + call history.

```bash
source .venv/bin/activate
streamlit run clients/streamlit_app.py
```

Streamlit opens at <http://localhost:8501>. In the sidebar, click
**Connect / Refresh** to load tools from `http://localhost:8000/sse` (editable),
pick a tool from the dropdown, fill in the form, hit **Call tool**.

### 3. Raw curl flow (advanced)

If you want to test the JSON-RPC wire protocol directly, see
[docs/instructions.txt](docs/instructions.txt) for the manual SSE +
`/messages/?session_id=…` flow.

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

1. Make sure the server is running (`python -m server`).
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

If you prefer running over stdio (no port needed):

```bash
python -m server --transport stdio
```

And update your client config to launch the script directly, e.g.:

```json
{
  "servers": {
    "local-sample-mcp": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/absolute/path/to/sample-mcp-server-script"
    }
  }
}
```

## Run with Docker

```bash
# Build the image
docker build -t sample-mcp-server .

# Run with a persistent notes DB volume
docker run --rm -p 8000:8000 -v "$PWD/data:/data" sample-mcp-server

# Override transport/host/port/log-level via env or CLI args
docker run --rm -p 9000:9000 -e MCP_PORT=9000 sample-mcp-server
docker run --rm sample-mcp-server --transport stdio
```

The image exposes port `8000` and stores the notes DB at `/data/notes.db` (mount a
volume there to persist it across container restarts).

## Run the tests

```bash
source .venv/bin/activate
pytest -q
```

`tests/test_notes_db.py` covers the SQLite store and `tests/test_server.py` covers
every pure tool, resource, and prompt by importing the server module directly.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'fastmcp'`** — activate the venv and rerun
  `pip install -r requirements.txt`.
- **Port 8000 already in use** — change the `port=8000` argument in
  `server/app.py`, and update the `url` in `.vscode/mcp.json` to match.
- **VS Code doesn't see the server** — restart the MCP server from the Copilot Chat
  tools picker, or reload the VS Code window.
- **`calculate` returns an error** — only `0-9`, `+`, `-`, `*`, `/`, `(`, `)`, `.`, and
  spaces are accepted (intentional safety restriction).

  ------------------------------------------------------------------------