import os
from config import PORT
from server import mcp
import tools  # noqa: F401 # Ensure all tools are registered via decorators in tools.py

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.environ.get("HOST", "0.0.0.0")
        mcp.run(transport="streamable-http", host=host, port=PORT)
    else:
        mcp.run(transport="stdio")
