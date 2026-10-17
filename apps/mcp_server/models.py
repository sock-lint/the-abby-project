"""Durable RFC 8707 bindings, independent of optional DOT resource fields."""
from __future__ import annotations

from django.db import models


class MCPTokenResource(models.Model):
    """Resource-indicator (RFC 8707) binding for an OAuth ``AccessToken``.

    Populated by ``config.oauth_validator.AbbyOAuth2Validator.save_bearer_token``
    for every valid auth-code or refresh exchange. Read by
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


class MCPAuthorizationResource(models.Model):
    """Exact resource accepted at consent, retained until the code is consumed."""

    grant = models.OneToOneField(
        "oauth2_provider.Grant", on_delete=models.CASCADE,
        related_name="mcp_resource",
    )
    resource = models.CharField(max_length=512)
