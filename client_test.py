"""Tiny CLI test harness for the local MCP server.

Examples:

    # List all tools the server exposes
    python client_test.py list

    # Call a tool with JSON-encoded arguments
    python client_test.py call echo --args '{"message": "hi"}'
    python client_test.py call password_generate --args '{"length": 32}'
    python client_test.py call weather --args '{"latitude": 28.6139, "longitude": 77.2090}'

    # Run a quick smoke test that exercises a handful of tools
    python client_test.py smoke
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from fastmcp import Client

DEFAULT_URL = "http://localhost:8000/sse"


def _pretty(obj) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except TypeError:
        return str(obj)


def _result_payload(result) -> object:
    """Extract a JSON-friendly payload from a FastMCP call_tool result."""
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content"):
        out = []
        for block in result.content:
            text = getattr(block, "text", None)
            out.append(text if text is not None else repr(block))
        return out if len(out) != 1 else out[0]
    return result


async def cmd_list(url: str) -> int:
    async with Client(url) as c:
        tools = await c.list_tools()
        print(f"Connected to {url} — {len(tools)} tool(s):\n")
        for t in tools:
            print(f"  • {t.name}")
            if t.description:
                first_line = t.description.strip().splitlines()[0]
                print(f"      {first_line}")
        return 0


async def cmd_call(url: str, name: str, args_json: str) -> int:
    try:
        args = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        print(f"Invalid JSON for --args: {e}", file=sys.stderr)
        return 2
    if not isinstance(args, dict):
        print("--args must be a JSON object", file=sys.stderr)
        return 2

    async with Client(url) as c:
        result = await c.call_tool(name, args)
        print(_pretty(_result_payload(result)))
    return 0


async def cmd_smoke(url: str) -> int:
    cases = [
        ("echo", {"message": "smoke test"}),
        ("get_server_time", {}),
        ("random_number", {"min_val": 1, "max_val": 10}),
        ("hash_text", {"text": "hello", "algorithm": "sha256"}),
        ("base64_encode", {"text": "hello"}),
        ("uuid_generate", {"count": 2}),
        ("password_generate", {"length": 24}),
        ("json_format", {"data": '{"b":2,"a":1}', "sort_keys": True}),
        ("convert_units", {"value": 10, "from_unit": "mi", "to_unit": "km"}),
    ]
    failures = 0
    async with Client(url) as c:
        for name, args in cases:
            try:
                result = await c.call_tool(name, args)
                print(f"OK  {name}")
                print(f"    -> {_pretty(_result_payload(result))}\n")
            except Exception as e:  # noqa: BLE001 - smoke test wants to keep going
                failures += 1
                print(f"FAIL {name}: {e}\n")
    print(f"{len(cases) - failures}/{len(cases)} tools succeeded")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI client for the local MCP server")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"MCP SSE URL (default: {DEFAULT_URL})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all tools exposed by the server")

    call_p = sub.add_parser("call", help="Call a tool by name")
    call_p.add_argument("tool", help="Tool name (e.g. echo, hash_text, weather)")
    call_p.add_argument("--args", default="{}", help='JSON object of arguments, e.g. \'{"text":"hi"}\'')

    sub.add_parser("smoke", help="Run a small predefined test suite")

    args = parser.parse_args()

    if args.command == "list":
        return asyncio.run(cmd_list(args.url))
    if args.command == "call":
        return asyncio.run(cmd_call(args.url, args.tool, args.args))
    if args.command == "smoke":
        return asyncio.run(cmd_smoke(args.url))
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())