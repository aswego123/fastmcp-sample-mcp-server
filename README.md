# Sample Local MCP Server

[![PyPI version](https://img.shields.io/pypi/v/fastmcp-sample-server.svg)](https://pypi.org/project/fastmcp-sample-server/)
[![Python versions](https://img.shields.io/pypi/pyversions/fastmcp-sample-server.svg)](https://pypi.org/project/fastmcp-sample-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-82%20passing-brightgreen.svg)](#run-the-tests)

A demo [Model Context Protocol](https://modelcontextprotocol.io/) server built on
[FastMCP](https://github.com/jlowin/fastmcp). It ships **20 tools, 5 resources, 3 prompts**,
a SQLite-backed notes store, per-call telemetry with a Plotly Streamlit dashboard,
and a CLI client. It exposes itself over **SSE** on `http://localhost:8000` by default
(also stdio and HTTP), so you can wire it into any MCP-aware client such as VS Code
Copilot Chat, Claude Desktop, or a custom agent.

## Install

```bash
# From PyPI (recommended)
pip install fastmcp-sample-server          # server + CLI
pip install "fastmcp-sample-server[ui]"    # + Streamlit dashboard

sample-mcp-server                          # start the SSE server on :8000
sample-mcp-client smoke                    # run a built-in smoke suite
```

Or clone the repo if you want to hack on it — see [Setup](#setup) below.

## Project structure

```
sample-mcp-server-script/
├── server/                  # The MCP server
│   ├── __init__.py
│   ├── __main__.py          # enables `python -m server`
│   ├── app.py               # FastMCP app + tools + resources + prompts + CLI
│   ├── notes_db.py          # SQLite-backed notes store
│   ├── safety.py            # SSRF / ReDoS / safe-eval guardrails
│   └── telemetry.py         # @traced decorator + telemetry SQLite store
├── clients/                 # Ways to talk to the server
│   ├── cli.py               # CLI: list / call / smoke
│   └── streamlit_app.py     # Streamlit UI with Telemetry tab
├── tests/                   # pytest suite (82 tests)
│   ├── test_notes_db.py
│   ├── test_safety.py
│   ├── test_server.py
│   └── test_telemetry.py
├── docs/                    # Misc notes
├── data/                    # Local SQLite DB + logs (gitignored)
├── Dockerfile
├── pyproject.toml           # PEP 621 metadata, hatchling backend
├── LICENSE                  # MIT
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

| URI                            | Description                                              |
| ------------------------------ | -------------------------------------------------------- |
| `resource://server/info`       | Server metadata: name, version, uptime, notes count.     |
| `resource://notes/all`         | All notes (max 500), newest first.                       |
| `resource://notes/{note_id}`   | A single note by id, e.g. `resource://notes/3`.          |
| `resource://telemetry/recent`  | Last 100 tool calls (tool, ts, duration_ms, status).     |
| `resource://telemetry/summary` | Aggregates: 60-min KPIs + 24-h per-tool counts.          |

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

### Install from a built wheel

The repo ships a [pyproject.toml](pyproject.toml) so you can `pip install` it
like any other package. Two console scripts get registered:

| Command              | Equivalent to                          |
| -------------------- | -------------------------------------- |
| `sample-mcp-server`  | `python -m server`                     |
| `sample-mcp-client`  | `python -m clients.cli`                |

```bash
# Build sdist + wheel into ./dist/
pip install build twine
python -m build

# Install the wheel locally
pip install dist/fastmcp_sample_server-*.whl

# Or install with the Streamlit UI extras
pip install "dist/fastmcp_sample_server-*.whl[ui]"

# Or with dev tools (pytest, build, twine)
pip install -e ".[ui,dev]"
```

### Publish to PyPI

Once you're happy with a release:

```bash
# Sanity-check the artifacts
twine check dist/*

# Upload to TestPyPI first (recommended)
twine upload --repository testpypi dist/*

# Then the real index
twine upload dist/*
```

Use an [API token](https://pypi.org/help/#apitoken) (`__token__` as the
username, the `pypi-...` token as the password). The version is read from
`SERVER_VERSION` in [server/app.py](server/app.py) — bump it before each
upload (PyPI doesn't allow re-uploading the same version).

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

---

## Quick-start cheat sheet

Three terminals, all from the project root after `source .venv/bin/activate`.

**Terminal 1 — start the server**
```bash
python -m server
# or with debug logging to a file
python -m server --log-level DEBUG --log-file data/mcp.log
```

**Terminal 2 — Streamlit UI**
```bash
streamlit run clients/streamlit_app.py
# opens http://localhost:8501
```

**Terminal 3 — CLI client**
```bash
python -m clients.cli list                    # discover tools
python -m clients.cli smoke                   # run the built-in smoke suite
python -m clients.cli call echo --args '{"message":"hi"}'
```

---

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

## Telemetry

Every tool call is recorded to a local SQLite file (`data/telemetry.db` by
default) via the `@traced` decorator in [server/telemetry.py](server/telemetry.py).
Per call we store: **timestamp, tool name, duration in ms, and status (`ok`
or `error`)** — and the exception message when something raises. We deliberately
**do not** record arguments or return values to keep secrets, tokens, hashed
inputs, password outputs, etc. out of the telemetry DB.

Tool-level failures returned as `{"error": "..."}` count as `ok` (they are a
normal Python return); only uncaught exceptions are recorded as `error`.

Toggle via env vars:

| Variable             | Default              | Meaning                                  |
| -------------------- | -------------------- | ---------------------------------------- |
| `MCP_TELEMETRY`      | `1`                  | Set to `0` to disable recording.         |
| `MCP_TELEMETRY_DB`   | `data/telemetry.db`  | Path to the telemetry SQLite file.       |

The Streamlit UI has a **📊 Telemetry** tab that pulls
`resource://telemetry/summary` and `resource://telemetry/recent` and renders:
KPI cards (calls, error rate, avg + **p50 / p95 / p99** latency), a Plotly
bar chart of calls per tool (last 24 h), **slowest-calls** and **recent-errors**
tables side-by-side, a latency scatter over time, and a filterable
recent-calls table. An **auto-refresh (5 s)** checkbox keeps it live, and the
Tool caller tab shows a per-tool "called N times, avg X ms" badge under the
description.

## Guardrails

The server applies a small set of defensive checks so a careless (or malicious)
agent can't trivially hang the process, escape the network sandbox, or fill up
the database. They live in [server/safety.py](server/safety.py) and are wired
into the relevant tools.

| Tool | Guardrail | Why |
| --- | --- | --- |
| `calculate` | AST-based evaluator instead of `eval()`. Only `+ - * / // % **`, parens, unary +/-, numeric literals. Exponent capped at 100; expression capped at 200 chars. | `eval()` is dangerous even with a charset filter — `9**9**9**9` would peg a CPU core forever. |
| `fetch_url` | Resolves the hostname and rejects loopback, private (10/8, 172.16/12, 192.168/16), link-local (incl. 169.254/16 cloud metadata), multicast, and reserved IPs. Streams the response and stops after `max_bytes`. | Blocks SSRF and prevents downloading huge files just to truncate them. |
| `regex_match` | Pattern capped at 1 KB, text at 1 MB, execution wrapped in a 2-second timeout via a worker thread. | Stops catastrophic backtracking (ReDoS) from blocking the server. |
| `note_add` / `note_update` | Title required, ≤200 chars; body ≤100 KB; both validated at the DB layer. | Prevents one bad call from bloating the SQLite file. |

What's **not** included (yet, by design — this is a local demo):

- No per-tool rate limiting
- No authentication on the SSE/HTTP transports
- No output-size cap on tool return values
- No prompt-injection sanitization on fetched HTML

If you ever expose this beyond `localhost`, add at least auth and rate limits
before doing so.

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

The suite (82 tests) covers:

- [test_notes_db.py](tests/test_notes_db.py) — SQLite notes CRUD + validation.
- [test_server.py](tests/test_server.py) — every pure tool, resource, and prompt
  by importing the server module directly.
- [test_safety.py](tests/test_safety.py) — the guardrails: `safe_eval_math`,
  SSRF blocklist, timeout helper, and input-cap behaviour.
- [test_telemetry.py](tests/test_telemetry.py) — `TelemetryDB`, percentiles,
  slowest/recent-errors queries, and the `@traced` decorator.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'fastmcp'`** — activate the venv and rerun
  `pip install -r requirements.txt` (or `pip install fastmcp-sample-server`).
- **Port 8000 already in use** — pass `--port 9000` to `sample-mcp-server`
  (or set `MCP_PORT=9000`), and update the `url` in `.vscode/mcp.json` to match.
- **VS Code doesn't see the server** — restart the MCP server from the Copilot Chat
  tools picker, or reload the VS Code window.
- **`calculate` returns an error** — only arithmetic is allowed (`+ - * / // % **`,
  parentheses, unary `+/-`, numeric literals). Names, function calls, and attribute
  access are rejected by the AST evaluator. Exponent must be ≤100, expression ≤200
  chars. See [Guardrails](#guardrails).
- **`fetch_url` rejects my URL** — the SSRF guard refuses any host that resolves to
  a loopback / private / link-local / multicast / reserved IP. Only `http(s)://`
  public hosts are allowed.

  ------------------------------------------------------------------------

  ## Demo Video

  https://github.com/user-attachments/assets/3dacf24b-3717-4b82-a036-e5ff4131bd09

## License

[MIT](LICENSE) © 2026 anjalikakkar
