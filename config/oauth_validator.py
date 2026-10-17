"""OAuth grants retain exact MCP resource and scope bindings through refresh."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError, InvalidRequestError
from oauth2_provider.oauth2_validators import OAuth2Validator

from apps.mcp_server.tool_policy import MCP_SCOPES


def _authorized_user(user) -> bool:
    return bool(user and user.is_active and user.role == "parent" and user.is_staff)


def _valid_scopes(scope: str) -> bool:
    scopes = set(scope.split())
    return bool(scopes) and scopes <= MCP_SCOPES


class AbbyOAuth2Validator(OAuth2Validator):
    def validate_response_type(self, client_id, response_type, client, request, *args, **kwargs):
        return response_type == "code" and super().validate_response_type(
            client_id, response_type, client, request, *args, **kwargs,
        )

    def client_authentication_required(self, request, *args, **kwargs):
        client = getattr(request, "client", None)
        if client is not None and client.client_type == "public":
            return False
        return super().client_authentication_required(request, *args, **kwargs)

    def save_authorization_code(self, client_id, code, request, *args, **kwargs):
        from oauth2_provider.models import Grant
        from apps.mcp_server.models import MCPAuthorizationResource

        resource = self._extract_resource(request)
        if not resource or resource != settings.MCP_RESOURCE_URL or not _authorized_user(request.user):
            raise InvalidRequestError(description="An authorized staff parent and exact MCP resource are required.")
        with transaction.atomic():
            super().save_authorization_code(client_id, code, request, *args, **kwargs)
            grant = Grant.objects.get(code=code["code"], application=request.client)
            MCPAuthorizationResource.objects.create(grant=grant, resource=resource)

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        from apps.mcp_server.models import MCPAuthorizationResource

        if not super().validate_code(client_id, code, client, request, *args, **kwargs):
            return False
        binding = MCPAuthorizationResource.objects.filter(
            grant__code=code, grant__application=client,
        ).first()
        requested_resource = self._extract_resource(request)
        if (
            not _authorized_user(request.user)
            or not _valid_scopes(" ".join(request.scopes))
            or binding is None
            or binding.resource != settings.MCP_RESOURCE_URL
            or (requested_resource is not None and requested_resource != binding.resource)
        ):
            return False
        request.abby_mcp_resource = binding.resource
        return True

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        if not super().validate_refresh_token(refresh_token, client, request, *args, **kwargs):
            return False
        previous = request.refresh_token_instance.access_token
        binding = getattr(previous, "mcp_resource", None) if previous else None
        requested_resource = self._extract_resource(request)
        if (
            not _authorized_user(request.user)
            or previous is None
            or not _valid_scopes(previous.scope)
            or binding is None
            or binding.resource != settings.MCP_RESOURCE_URL
            or (requested_resource is not None and requested_resource != binding.resource)
        ):
            return False
        request.abby_mcp_resource = binding.resource
        return True

    def _save_bearer_token(self, token: dict, request: Any, *args, **kwargs) -> None:
        """DOT calls this inside its token transaction; binding failures roll it back."""
        from oauth2_provider.models import AccessToken
        from apps.mcp_server.models import MCPTokenResource

        resource = getattr(request, "abby_mcp_resource", None)
        if (
            not resource or resource != settings.MCP_RESOURCE_URL
            or not _authorized_user(request.user)
            or not _valid_scopes(token.get("scope", ""))
        ):
            raise InvalidGrantError(description="Reconnect to authorize scoped access to this MCP resource.")
        super()._save_bearer_token(token, request, *args, **kwargs)
        access_token = AccessToken.objects.get(token=token["access_token"])
        MCPTokenResource.objects.update_or_create(
            access_token=access_token, defaults={"resource": resource},
        )

    @staticmethod
    def _extract_resource(request: Any) -> str | None:
        """Return one exact indicator; None is absent and empty string is invalid."""
        def scalar(value):
            if value is None or value == []:
                return None
            if isinstance(value, (list, tuple)):
                return value[0] if len(value) == 1 and isinstance(value[0], str) else ""
            return value if isinstance(value, str) else ""

        for value in (
            getattr(request, "resource", None),
            (getattr(request, "extra_credentials", None) or {}).get("resource"),
            (getattr(request, "_params", None) or {}).get("resource"),
        ):
            resource = scalar(value)
            if resource is not None:
                return resource
        return None
