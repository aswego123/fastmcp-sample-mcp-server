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

import streamlit as st
from fastmcp import Client

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

tool_names = [t.name for t in st.session_state.tools]
selected_name = st.selectbox("Tool", tool_names, key="tool_picker")
selected_tool = next(t for t in st.session_state.tools if t.name == selected_name)

if selected_tool.description:
    st.markdown(f"**Description:** {selected_tool.description}")

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

# ---------------------------------------------------------------------------
# Result / history
# ---------------------------------------------------------------------------

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
