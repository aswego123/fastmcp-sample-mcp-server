# Building a production-ish MCP server in Python — guardrails, telemetry, and a Streamlit dashboard

*Or: how I turned a 60-line FastMCP demo into a real package on PyPI.*

---

The [Model Context Protocol](https://modelcontextprotocol.io/) is the closest thing the agent ecosystem has to a USB-C port — one spec that lets any LLM client (Copilot, Claude Desktop, Cursor, your own agent) plug into any server-side toolbelt. The protocol is solid. The starter code, though, gets you to "hello world" and stops there. Real questions like *"What happens when an agent passes me `^(a+)+$` as a regex?"* or *"How do I know which tool is slow?"* are left as exercises.

I built [`fastmcp-sample-server`](https://pypi.org/project/fastmcp-sample-server/) — a small open-source MCP server — partly to learn the protocol and partly to answer those questions in code. Twenty tools, five resources, three prompts, SQLite-backed notes, per-call telemetry with a Plotly dashboard, AST-based guardrails, a CLI client, Docker support, and 82 tests. Install it with:

```bash
pip install "fastmcp-sample-server[ui]"
sample-mcp-server          # starts the SSE server on :8000
```

This is the build log. If you're thinking about shipping your own MCP server — or just want a tour of "what does production-ish look like on top of a hobby FastMCP project?" — read on.

---

## Why MCP, briefly

MCP is to LLM tools what Language Server Protocol is to editors. Before LSP, every editor had a custom integration for every language; after LSP, one VS Code extension talks to a hundred language servers and Just Works. MCP does the same for tools, resources, and prompts that an LLM agent can call.

The server side is a JSON-RPC process that exposes:

- **Tools** — functions the model can call (`calculate`, `fetch_url`, `note_add`).
- **Resources** — read-only data the model can subscribe to (`resource://notes/all`).
- **Prompts** — reusable prompt templates the user picks from a menu.

The client (Claude Desktop, VS Code Copilot Chat, your custom agent) is the thing that actually invokes the model and decides when to call your tools.

[FastMCP](https://github.com/jlowin/fastmcp) is a Python framework that hides the JSON-RPC plumbing behind decorators. Here's a complete working server:

```python
from fastmcp import FastMCP

mcp = FastMCP("Hello server")

@mcp.tool()
def echo(message: str) -> str:
    """Echo back a message."""
    return f"echo: {message}"

if __name__ == "__main__":
    mcp.run(transport="sse", port=8000)
```

That's the whole demo. Now let me show what was missing.

---

## Phase 1 — useful tools

I started by adding tools an agent might actually reach for: SHA hashing, base64 encode/decode, UUIDs, secure password generation, JSON pretty-printing, regex matching, unit conversion, an HTTP fetcher, and a weather lookup (Open-Meteo, no API key needed). All single-function, all schema-typed via Python hints. FastMCP generates the JSON Schema automatically:

```python
@mcp.tool()
def password_generate(
    length: int = 20,
    use_uppercase: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
) -> dict:
    """Generate a cryptographically strong random password."""
    # ...uses secrets.choice and secrets.randbelow
```

The agent sees `length: int = 20`, knows to ask the user for an integer, and validates before calling. Zero config.

**Lesson:** Pick tools that benefit from being deterministic, fast, and offline. LLMs are great at fuzzy reasoning and bad at SHA-256 — give them the things they're bad at.

---

## Phase 2 — guardrails

The moment you let an LLM type into your `eval()`, you have a problem. Here's a real prompt I tried:

> "Use the calculate tool to compute 9 ** 9 ** 9 ** 9"

A naive `eval(expression)` would peg one CPU core forever — Python happily computes that tower expression. So `calculate` got a real evaluator:

```python
def safe_eval_math(expression: str) -> float | int:
    """AST walker. Only + - * / // % **, parens, unary +/-, numeric literals.
    Rejects names, calls, attribute access. Exponent capped at 100."""
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)
```

Three more guardrails followed:

1. **SSRF protection on `fetch_url`.** Before any HTTP request, resolve the hostname with `socket.getaddrinfo` and walk the resolved IPs through `ipaddress.ip_address(ip).is_private` (plus loopback, link-local, multicast, reserved). Block them. Otherwise an agent can read `http://169.254.169.254/latest/meta-data/` from a cloud VM and leak your instance credentials.
2. **ReDoS timeout on `regex_match`.** Pattern capped at 1 KB, text at 1 MB, execution wrapped in a 2-second budget via `concurrent.futures.ThreadPoolExecutor`. Catastrophic backtracking is real; one bad pattern can hang the server until you `kill -9`.
3. **Length caps on notes.** Title ≤200, body ≤100 KB. Validated at the DB layer so future code paths can't bypass them.

All three live in [`server/safety.py`](https://github.com/aswego123/fastmcp-sample-mcp-server/blob/main/server/safety.py). The README has a [Guardrails table](https://github.com/aswego123/fastmcp-sample-mcp-server#guardrails) explaining what's covered and — importantly — *what isn't* (no auth, no rate limits, no output-size cap). Being honest about the gaps is the difference between "demo project" and "I'd let a coworker use this."

**Lesson:** Treat every tool input as user input from your worst customer.

---

## Phase 3 — telemetry that survives

A protocol-compliant MCP server can't tell you anything about itself. "Was that call slow?" "Which tool errored?" "How often does the agent actually call `weather`?" — you have no way to know.

I added a one-decorator telemetry layer:

```python
@functools.wraps(fn)
def wrapper(*args, **kwargs):
    if not is_enabled():
        return fn(*args, **kwargs)
    start = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        get_db().record(name, duration_ms, "error",
                        error=f"{type(exc).__name__}: {exc}")
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    get_db().record(name, duration_ms, "ok")
    return result
```

Two design choices worth calling out:

- **No args, no return values.** I deliberately *don't* record what was passed in or what was returned. That keeps secrets — generated passwords, hashed inputs, fetched HTML — out of the telemetry DB. The cost is less debuggability; the win is one less compliance worry.
- **App-level `{"error": ...}` returns count as `ok`.** They're normal Python returns. Only uncaught exceptions count as `error`. That keeps the error rate honest.

The data lives in a separate `data/telemetry.db` (decoupled from notes) and surfaces two MCP resources any client can read:

| URI | Returns |
| --- | --- |
| `resource://telemetry/recent` | Last 100 calls |
| `resource://telemetry/summary` | 60-min KPIs (count, errors, avg, p50/p95/p99), 24-h per-tool counts, slowest 10 calls, last 20 errors |

Percentiles, by the way, are computed in Python because SQLite has no `PERCENTILE_CONT`. The trick is a single `ORDER BY duration_ms` query and one linear-interpolation pass — fast enough up to millions of rows.

**Lesson:** Decide what *not* to log first. Then build the dashboard.

---

## Phase 4 — a Streamlit UI that pulls from MCP

The MCP `Client` class is async; Streamlit is sync. The integration is one helper:

```python
def _run(coro):
    return asyncio.run(coro)

async def _list_tools(url):
    async with Client(url) as c:
        return await c.list_tools()
```

The UI has two tabs:

- **🔧 Tool caller** — auto-generates a form from each tool's `inputSchema`. Strings → `text_input`, ints → `number_input`, booleans → `checkbox`, enums → `selectbox`, arrays/objects → JSON `text_area`. Hit "Call tool", see the result. Under each tool's description, a small badge: *"📈 called 47 times in last 24 h · avg 12.3 ms"*.
- **📊 Telemetry** — Plotly bar chart of calls per tool (colored by error count), latency scatter over time (green = ok, red = error), tables of slowest calls and recent errors. An "Auto-refresh (5 s)" checkbox keeps it live while you hammer the server from the CLI.

The whole dashboard pulls from the two MCP resources above. **Anything an agent can see, the UI can see too.**

---

## Phase 5 — packaging for PyPI

Once the layout was stable, packaging was a single afternoon. The project uses [hatchling](https://hatch.pypa.io/) (lighter than setuptools, recommended by PyPA) and reads the version out of `server/app.py` via regex so there's exactly one source of truth:

```toml
[build-system]
requires = ["hatchling>=1.21"]
build-backend = "hatchling.build"

[project]
name = "fastmcp-sample-server"
dynamic = ["version"]
# ...

[project.scripts]
sample-mcp-server = "server.app:main"
sample-mcp-client = "clients.cli:main"

[tool.hatch.version]
path = "server/app.py"
pattern = "SERVER_VERSION\\s*=\\s*\"(?P<version>[^\"]+)\""
```

The build-test-publish dance:

```bash
python -m build              # writes dist/*.whl and dist/*.tar.gz
twine check dist/*           # validates metadata
twine upload dist/*          # ships to PyPI
```

Two gotchas worth recording:

- **PyPI versions are immutable.** Once `0.4.0` is up, you can't replace it. Bump the version before every upload.
- **TestPyPI is a separate account.** A `pypi.org` token won't work on `test.pypi.org`. Two accounts, two tokens.

---

## What I'd add next

- **Authentication on the SSE/HTTP transports.** Bearer token via env var, checked in ASGI middleware.
- **OpenTelemetry export.** Replace (or augment) the SQLite recorder with OTel spans, wire to Jaeger via docker-compose. The decorator stays; only the recorder swaps.
- **A real "agentic" tool.** `web_search` plus `summarize_url` would turn this from utility belt into something an agent actually reaches for.

---

## Try it

```bash
pip install "fastmcp-sample-server[ui]"

# terminal 1
sample-mcp-server

# terminal 2
sample-mcp-client smoke      # hits 9 tools end-to-end
streamlit run "$(python -c 'import clients.streamlit_app, os; print(os.path.dirname(clients.streamlit_app.__file__))')/streamlit_app.py"
```

Or browse the source on [GitHub](https://github.com/aswego123/fastmcp-sample-mcp-server). PRs welcome — the issues list is a good shopping list of "things a portfolio-grade MCP server probably wants next."

If you're building your own MCP server, the three things I'd steal from this repo are: **the `@traced` decorator** (one file, no deps, instant observability), **the SSRF/eval/ReDoS guardrails** (every tool that touches network or untrusted input needs all three), and **the auto-form Streamlit UI** (because writing a custom client per tool is a tax).

Happy building.

---

*Project: [github.com/aswego123/fastmcp-sample-mcp-server](https://github.com/aswego123/fastmcp-sample-mcp-server) · PyPI: [pypi.org/project/fastmcp-sample-server](https://pypi.org/project/fastmcp-sample-server/)*
