"""Allow `python -m server` to start the MCP server."""

from .app import main

raise SystemExit(main())
