"""Django management command that runs the MCP server.

Exposes two transports:

* ``--transport http`` (default): starts a uvicorn process serving the
  Streamable HTTP MCP endpoint with DRF-token authentication middleware.
* ``--transport stdio``: runs the server over stdio, for local development
  and ``claude mcp add --transport stdio`` style connections.

``--as-user <username>`` pins a user into the request context for the
lifetime of the process; it is only allowed when ``DEBUG`` is truthy so it
can't leak into production.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the MCP server (Streamable HTTP or stdio transport)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--transport",
            choices=["http", "stdio"],
            default="http",
            help="Transport to use. 'http' is for Claude remote connectors; "
                 "'stdio' is for local development.",
        )
        parser.add_argument(
            "--host",
            default="0.0.0.0",
            help="HTTP bind host (http transport only).",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8001,
            help="HTTP bind port (http transport only).",
        )
        parser.add_argument(
            "--as-user",
            default=None,
            help="Pin the current user to <username> for stdio transport. "
                 "Only allowed when DEBUG is true.",
        )

    def handle(self, *args, **options) -> None:
        transport = options["transport"]
        as_user = options["as_user"]

        # Import lazily so Django is fully ready before FastMCP touches the ORM.
        from apps.mcp_server import server as mcp_server

        if as_user:
            if not getattr(settings, "MCP_DEV_ALLOW_USER_PIN", False):
                raise CommandError(
                    "--as-user is only allowed when DEBUG is true.",
                )
            from apps.accounts.models import User

            try:
                user = User.objects.get(username=as_user)
            except User.DoesNotExist as exc:
                raise CommandError(f"User '{as_user}' not found.") from exc
            from apps.mcp_server.context import set_current_user

            set_current_user(user)
            self.stdout.write(self.style.WARNING(
                f"[dev] Pinned MCP context to user {user.username} "
                f"(role={user.role})",
            ))

        if transport == "stdio":
            self.stdout.write(self.style.NOTICE(
                "Starting MCP server on stdio transport...",
            ))
            mcp_server.run_stdio()
            return

        host = options["host"]
        port = options["port"]
        self.stdout.write(self.style.NOTICE(
            f"Starting MCP server on http://{host}:{port}/mcp ...",
        ))

        import uvicorn

        uvicorn.run(
            mcp_server.build_http_app(),
            host=host,
            port=port,
            log_level="info",
        )
