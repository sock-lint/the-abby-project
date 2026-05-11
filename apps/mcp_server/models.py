"""Models owned by the MCP server app.

Today there is exactly one: the side-table that holds the RFC 8707
resource-indicator binding for OAuth access tokens. django-oauth-toolkit
3.0.1's ``AccessToken`` doesn't have a generic ``claims`` JSON field
(only ``Grant`` does), so we hold the resource on a separate row indexed
by AccessToken.

Why not subclass ``AbstractAccessToken``? Swapping DOT's access-token
model is a one-time, project-wide migration that ripples through every
``oauth2_provider.AccessToken`` reference; a side-table costs one extra
SELECT per request and is reversible.
"""
from __future__ import annotations

from django.db import models


class MCPTokenResource(models.Model):
    """Resource-indicator (RFC 8707) binding for an OAuth ``AccessToken``.

    Populated by ``config.oauth_validator.AbbyOAuth2Validator.save_bearer_token``
    when an auth-code request carried a ``resource`` parameter. Read by
    ``apps.mcp_server.auth._resolve_user`` to refuse tokens whose binding
    doesn't match ``settings.MCP_RESOURCE_URL``.

    The cascade on AccessToken delete is intentional — a revoked /
    expired-and-purged token can never be replayed, so its resource
    binding row is dead weight.
    """

    access_token = models.OneToOneField(
        "oauth2_provider.AccessToken",
        on_delete=models.CASCADE,
        related_name="mcp_resource",
    )
    resource = models.CharField(max_length=512, db_index=True)

    class Meta:
        verbose_name = "MCP token resource binding"
        verbose_name_plural = "MCP token resource bindings"

    def __str__(self) -> str:  # pragma: no cover - admin display only
        return f"MCPTokenResource(access_token_id={self.access_token_id}, resource={self.resource!r})"
