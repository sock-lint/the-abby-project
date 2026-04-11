"""MCP tool modules.

Each submodule imports the shared ``mcp`` FastMCP instance from
``apps.mcp_server.server`` and registers its tools via ``@mcp.tool()``.
Importing this package (or any submodule) triggers registration.
"""
