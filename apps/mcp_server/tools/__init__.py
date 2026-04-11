"""MCP tool modules.

Each submodule imports the ``tool`` decorator from
``apps.mcp_server.server`` and registers its handlers via ``@tool()``. That
decorator wraps sync Django-ORM bodies with ``sync_to_async`` before
registering them with the shared FastMCP instance, so the registered
callables are true coroutine functions (required — FastMCP calls sync
handlers inline on the event-loop thread, which triggers Django's async-
safety guard on any ORM call). Importing this package (or any submodule)
triggers registration.
"""
