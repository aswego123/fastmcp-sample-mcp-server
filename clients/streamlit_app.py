"""Streamlit UI for the local MCP server.

Run with:
    streamlit run clients/streamlit_app.py

It connects to the MCP server (default: http://localhost:8000/sse), lists the
available tools, and renders a dynamic form based on each tool's JSON input
schema so you can call any tool without writing code.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import plotly.express as px
import streamlit as st
from fastmcp import Client
from streamlit_autorefresh import st_autorefresh

DEFAULT_URL = "http://localhost:8000/sse"

st.set_page_config(page_title="MCP Client", page_icon="🔧", layout="wide")


# ---------------------------------------------------------------------------
# Async helpers — Streamlit reruns the script on every interaction, so we open
# a fresh Client per action. That's fine for a local dev UI.
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


async def _list_tools(url: str) -> list[Any]:
    async with Client(url) as c:
        return await c.list_tools()


async def _call_tool(url: str, name: str, args: dict) -> Any:
    async with Client(url) as c:
        return await c.call_tool(name, args)


async def _read_resource(url: str, uri: str) -> Any:
    async with Client(url) as c:
        return await c.read_resource(uri)


def _resource_to_dict(result: Any) -> dict | list | None:
    """Parse the first text block of a read_resource result into JSON."""
    items = result if isinstance(result, list) else getattr(result, "contents", None) or [result]
    for block in items:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"raw": text}
    return None


def _result_payload(result) -> Any:
    """Extract a JSON-friendly payload from a FastMCP CallToolResult."""
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content"):
        out = []
        for block in result.content:
            text = getattr(block, "text", None)
            out.append(text if text is not None else repr(block))
        return out[0] if len(out) == 1 else out
    return result


def _is_error(result) -> bool:
    return bool(getattr(result, "is_error", False))


# ---------------------------------------------------------------------------
# Schema → Streamlit form
# ---------------------------------------------------------------------------

def _resolve_ref(schema: dict, root: dict) -> dict:
    """Follow a $ref within the same document. Returns the original schema if not a ref."""
    ref = schema.get("$ref")
    if not ref or not ref.startswith("#/"):
        return schema
    node: Any = root
    for part in ref[2:].split("/"):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return schema
    return node if isinstance(node, dict) else schema


def _input_for(prop_name: str, prop_schema: dict, root_schema: dict, required: bool, key_prefix: str) -> Any:
    """Render a single Streamlit input for one JSON-schema property."""
    schema = _resolve_ref(prop_schema, root_schema)
    title = schema.get("title") or prop_name
    desc = schema.get("description", "")
    label = f"{title}{' *' if required else ''}"
    key = f"{key_prefix}:{prop_name}"
    default = schema.get("default")

    # Enum → selectbox
    if "enum" in schema:
        options = schema["enum"]
        idx = options.index(default) if default in options else 0
        return st.selectbox(label, options, index=idx, help=desc, key=key)

    json_type = schema.get("type")
    if isinstance(json_type, list):
        # e.g. ["string", "null"] — pick the first non-null
        json_type = next((t for t in json_type if t != "null"), json_type[0])

    if json_type == "boolean":
        return st.checkbox(label, value=bool(default) if default is not None else False, help=desc, key=key)

    if json_type == "integer":
        val = st.number_input(
            label,
            value=int(default) if default is not None else 0,
            step=1,
            help=desc,
            key=key,
        )
        return int(val)

    if json_type == "number":
        val = st.number_input(
            label,
            value=float(default) if default is not None else 0.0,
            help=desc,
            key=key,
        )
        return float(val)

    if json_type in ("array", "object"):
        placeholder = json.dumps(default, indent=2) if default is not None else ("[]" if json_type == "array" else "{}")
        raw = st.text_area(
            f"{label} (JSON)",
            value=placeholder,
            help=desc or f"Enter a JSON {json_type}.",
            key=key,
            height=120,
        )
        try:
            return json.loads(raw) if raw.strip() else (default if default is not None else ([] if json_type == "array" else {}))
        except json.JSONDecodeError as e:
            st.error(f"`{prop_name}`: invalid JSON ({e.msg})")
            return None

    # Default: string
    multiline = bool(desc) and len(desc) > 80
    if multiline or schema.get("format") in {"text", "textarea"}:
        return st.text_area(label, value=str(default) if default is not None else "", help=desc, key=key)
    return st.text_input(label, value=str(default) if default is not None else "", help=desc, key=key)


def render_form(tool, key_prefix: str) -> dict | None:
    """Render a form for a tool's inputSchema. Returns the args dict, or None on validation error."""
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", {}) or {}
    if not isinstance(schema, dict):
        schema = {}
    props = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])

    if not props:
        st.caption("This tool takes no arguments.")
        return {}

    args: dict[str, Any] = {}
    error = False
    for name, prop_schema in props.items():
        value = _input_for(name, prop_schema, schema, name in required, key_prefix)
        # Treat empty strings for optional fields as "leave unset"
        if value == "" and name not in required:
            continue
        if value is None and name in required:
            st.error(f"`{name}` is required")
            error = True
            continue
        if value is None:
            continue
        args[name] = value
    return None if error else args


# ---------------------------------------------------------------------------
# Sidebar — connection + tool list
# ---------------------------------------------------------------------------

st.title("🔧 MCP Client")
st.caption("A tiny Streamlit UI for calling tools on the local FastMCP server.")

if "history" not in st.session_state:
    st.session_state.history = []
if "tools" not in st.session_state:
    st.session_state.tools = []
if "server_url" not in st.session_state:
    st.session_state.server_url = DEFAULT_URL

with st.sidebar:
    st.header("Server")
    url = st.text_input("MCP SSE URL", value=st.session_state.server_url, key="url_input")
    col_a, col_b = st.columns(2)
    if col_a.button("Connect / Refresh", use_container_width=True, type="primary"):
        st.session_state.server_url = url
        with st.spinner(f"Listing tools from {url}…"):
            try:
                tools = _run(_list_tools(url))
                st.session_state.tools = tools
                st.success(f"Connected — {len(tools)} tool(s)")
            except Exception as e:  # noqa: BLE001
                st.session_state.tools = []
                st.error(f"Failed: {e}")
    if col_b.button("Clear history", use_container_width=True):
        st.session_state.history = []

    if st.session_state.tools:
        st.subheader("Available tools")
        for t in st.session_state.tools:
            st.write(f"• `{t.name}`")

# ---------------------------------------------------------------------------
# Main area — tool picker + form + result
# ---------------------------------------------------------------------------

if not st.session_state.tools:
    st.info("Click **Connect / Refresh** in the sidebar to load tools from the server.")
    st.stop()


# Shared helper used by both tabs to load (and cache) the telemetry snapshot.
def _fetch_telemetry(url: str) -> dict | None:
    try:
        summary_raw = _run(_read_resource(url, "resource://telemetry/summary"))
        recent_raw = _run(_read_resource(url, "resource://telemetry/recent"))
        return {
            "summary": _resource_to_dict(summary_raw) or {},
            "recent": (_resource_to_dict(recent_raw) or {}).get("calls", []),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }
    except Exception:  # noqa: BLE001
        return None


def _per_tool_stats(data: dict | None, tool: str) -> dict | None:
    if not data:
        return None
    for row in data.get("summary", {}).get("per_tool_24h", []) or []:
        if row.get("tool") == tool:
            return row
    return None


tab_tools, tab_telemetry = st.tabs(["🔧 Tool caller", "📊 Telemetry"])

with tab_tools:
    tool_names = [t.name for t in st.session_state.tools]
    selected_name = st.selectbox("Tool", tool_names, key="tool_picker")
    selected_tool = next(t for t in st.session_state.tools if t.name == selected_name)

    if selected_tool.description:
        st.markdown(f"**Description:** {selected_tool.description}")

    # Per-tool telemetry badge (best-effort; silently skips if telemetry unreachable)
    stats = _per_tool_stats(st.session_state.get("telemetry_data"), selected_name)
    if stats:
        err = stats.get("errors", 0)
        avg = stats.get("avg_ms", 0.0) or 0.0
        badge = f"📈 called **{stats['calls']}** times in last 24 h · avg **{avg:.1f} ms**"
        if err:
            badge += f" · ❌ **{err}** error(s)"
        st.caption(badge)

    with st.expander("Input schema", expanded=False):
        st.json(getattr(selected_tool, "inputSchema", {}) or {})

    st.subheader("Arguments")
    args = render_form(selected_tool, key_prefix=selected_name)

    call_clicked = st.button("Call tool", type="primary", disabled=args is None)

    if call_clicked and args is not None:
        with st.spinner(f"Calling `{selected_name}`…"):
            try:
                result = _run(_call_tool(st.session_state.server_url, selected_name, args))
                payload = _result_payload(result)
                entry = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "tool": selected_name,
                    "args": args,
                    "ok": not _is_error(result),
                    "result": payload,
                }
            except Exception as e:  # noqa: BLE001
                entry = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "tool": selected_name,
                    "args": args,
                    "ok": False,
                    "result": f"Error: {e}",
                }
            st.session_state.history.insert(0, entry)

    if st.session_state.history:
        latest = st.session_state.history[0]
        st.subheader("Result")
        if latest["ok"]:
            st.success(f"`{latest['tool']}` succeeded at {latest['ts']}")
        else:
            st.error(f"`{latest['tool']}` failed at {latest['ts']}")
        if isinstance(latest["result"], (dict, list)):
            st.json(latest["result"])
        else:
            st.code(str(latest["result"]))

        with st.expander(f"History ({len(st.session_state.history)})", expanded=False):
            for entry in st.session_state.history:
                status = "✅" if entry["ok"] else "❌"
                st.markdown(f"{status} **{entry['tool']}** — {entry['ts']}")
                st.caption("args:")
                st.json(entry["args"])
                st.caption("result:")
                if isinstance(entry["result"], (dict, list)):
                    st.json(entry["result"])
                else:
                    st.code(str(entry["result"]))
                st.divider()


# ---------------------------------------------------------------------------
# Telemetry tab — server-side stats pulled from resource://telemetry/*
# ---------------------------------------------------------------------------

with tab_telemetry:
    st.subheader("Server telemetry")
    st.caption(
        "Live data from `resource://telemetry/summary` and `resource://telemetry/recent`. "
        "Records tool name, duration, and ok/error status — no arguments or results are stored."
    )

    top_l, top_m, top_r = st.columns([1, 1, 1])
    refresh = top_l.button("🔄 Refresh telemetry", type="primary")
    auto_refresh = top_m.checkbox("Auto-refresh (5 s)", value=False, key="tel_autorefresh")
    window_min = top_r.selectbox(
        "Summary window",
        options=[15, 60, 360, 1440],
        index=1,
        format_func=lambda m: f"last {m} min" if m < 1440 else "last 24 h",
        key="tel_window",
    )

    if auto_refresh:
        st_autorefresh(interval=5000, key="telemetry_autorefresh")

    if refresh or auto_refresh or "telemetry_data" not in st.session_state:
        snap = _fetch_telemetry(st.session_state.server_url)
        if snap is None:
            st.error("Could not load telemetry — is the server running?")
        st.session_state.telemetry_data = snap

    data = st.session_state.get("telemetry_data")
    if not data:
        st.info("No telemetry loaded yet. Click **Refresh telemetry** above.")
    else:
        st.caption(f"Last refreshed at {data['fetched_at']}")
        summary = data["summary"].get("summary_60m", {}) or {}
        per_tool = data["summary"].get("per_tool_24h", []) or []
        slowest = data["summary"].get("slowest_24h", []) or []
        errors_list = data["summary"].get("recent_errors", []) or []
        recent = data["recent"]

        # Top-line KPIs
        total = summary.get("total", 0)
        errors = summary.get("errors", 0)
        avg_ms = summary.get("avg_ms", 0.0)
        err_rate = (errors / total * 100) if total else 0.0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Calls (last 60 min)", f"{total}")
        c2.metric("Errors", f"{errors}", delta=f"{err_rate:.1f}% rate", delta_color="inverse")
        c3.metric("Avg duration", f"{avg_ms:.1f} ms")
        c4.metric("Total recorded", f"{data['summary'].get('total_recorded', 0):,}")

        # Latency percentiles
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("p50 latency", f"{summary.get('p50_ms', 0.0):.1f} ms")
        p2.metric("p95 latency", f"{summary.get('p95_ms', 0.0):.1f} ms")
        p3.metric("p99 latency", f"{summary.get('p99_ms', 0.0):.1f} ms")
        p4.metric("max", f"{summary.get('max_ms', 0.0):.1f} ms")

        st.divider()

        # Per-tool bar chart (last 24 h)
        if per_tool:
            st.markdown("**Calls per tool — last 24 h**")
            fig = px.bar(
                per_tool,
                x="tool",
                y="calls",
                color="errors",
                color_continuous_scale="Reds",
                hover_data=["avg_ms"],
                labels={"tool": "Tool", "calls": "Calls", "errors": "Errors"},
            )
            fig.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No tool calls recorded yet.")

        # Slowest calls + recent errors side-by-side (hidden when both empty)
        if slowest or errors_list:
            sl_col, err_col = st.columns(2)
            with sl_col:
                if slowest:
                    st.markdown("**🐢 Slowest calls — last 24 h**")
                    st.dataframe(
                        [
                            {"ts": r["ts"], "tool": r["tool"], "ms": round(r["duration_ms"], 1), "status": r["status"]}
                            for r in slowest
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
            with err_col:
                if errors_list:
                    st.markdown("**❌ Recent errors**")
                    st.dataframe(
                        [
                            {"ts": r["ts"], "tool": r["tool"], "ms": round(r["duration_ms"], 1), "error": r["error"]}
                            for r in errors_list
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

        # Latency over time
        if recent:
            st.markdown(f"**Recent calls — latency over time (last {len(recent)})**")
            fig2 = px.scatter(
                recent,
                x="ts",
                y="duration_ms",
                color="status",
                hover_data=["tool", "error"],
                color_discrete_map={"ok": "#10b981", "error": "#ef4444"},
                labels={"ts": "Timestamp", "duration_ms": "Duration (ms)"},
            )
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

            # Filterable table
            st.markdown("**Recent calls**")
            f_l, f_r = st.columns([1, 1])
            tools_in_data = sorted({r["tool"] for r in recent})
            tool_filter = f_l.selectbox("Filter tool", ["(all)"] + tools_in_data, key="tel_tool")
            status_filter = f_r.selectbox("Filter status", ["(all)", "ok", "error"], key="tel_status")
            filtered = [
                r for r in recent
                if (tool_filter == "(all)" or r["tool"] == tool_filter)
                and (status_filter == "(all)" or r["status"] == status_filter)
            ]
            st.dataframe(filtered, use_container_width=True, hide_index=True)
