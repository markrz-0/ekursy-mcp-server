from config import MCP_TRANSPORT, PORT
from server import mcp
import tools  # noqa: F401 # Ensure all tools are registered via decorators in tools.py
import account_routes  # noqa: F401 # Register browser-based account setup routes

if __name__ == "__main__":
    if MCP_TRANSPORT == "streamable-http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=PORT)
    else:
        mcp.run(transport="stdio")
