"""MCP server package.

Exposes the FastMCP app and CLI entrypoint. Run with::

    python -m server               # default (SSE on 0.0.0.0:8000)
    python -m server --help        # list CLI flags
    sample-mcp-server              # same thing, after `pip install`
"""

from .app import mcp, main, SERVER_NAME, SERVER_VERSION

__version__ = SERVER_VERSION

__all__ = ["mcp", "main", "SERVER_NAME", "SERVER_VERSION", "__version__"]
