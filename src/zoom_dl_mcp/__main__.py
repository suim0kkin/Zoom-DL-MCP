"""Entrypoint allowing module invocation via `python -m zoom_dl_mcp`."""

import sys

from zoom_dl_mcp.cli import main
from zoom_dl_mcp.server import run_server

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        # Remove 'mcp' argument and start MCP server
        sys.argv.pop(1)
        run_server()
    else:
        sys.exit(main())
