"""MCP server package.

Exposes the FastMCP app and CLI entrypoint. Run with::

    python -m server               # default (SSE on 0.0.0.0:8000)
    python -m server --help        # list CLI flags
"""

from .app import mcp, main, SERVER_NAME, SERVER_VERSION

__all__ = ["mcp", "main", "SERVER_NAME", "SERVER_VERSION"]
