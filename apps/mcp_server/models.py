"""Durable RFC 8707 bindings, independent of optional DOT resource fields."""
from __future__ import annotations

from django.db import models
from django.conf import settings

from config.base_models import CreatedAtModel, TimestampedModel


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


class AssetProposal(TimestampedModel):
    """A private production brief, never an artwork publication or grant."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        READY = "ready", "Ready for external production"
        DELIVERED = "delivered", "External delivery recorded"
        CANCELLED = "cancelled", "Cancelled"

    family = models.ForeignKey("families.Family", on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="asset_proposals")
    request_id = models.UUIDField()
    request_digest = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)
    brief = models.JSONField()
    brief_digest = models.CharField(max_length=64)
    delivery = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["family", "request_id"], name="asset_proposal_family_request")]


class AssetProposalEvent(CreatedAtModel):
    """Append-only audit of briefs, reviews and claimed external deliveries."""

    proposal = models.ForeignKey(AssetProposal, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    revision = models.PositiveIntegerField()
    action = models.CharField(max_length=24)
    details = models.JSONField(default=dict)
