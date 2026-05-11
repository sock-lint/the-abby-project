"""Custom DOT OAuth2Validator that enforces the MCP-spec invariants.

Three things this layer adds on top of django-oauth-toolkit's defaults:

1. **Public-clients only** — every client registered through DCR is created
   with ``client_type='public'`` + ``client_secret=''`` and PKCE is required
   (set in ``OAUTH2_PROVIDER`` settings). The validator's
   ``client_authentication_required`` reflects that — public clients don't
   prove identity at the token endpoint, the PKCE ``code_verifier`` does.
2. **response_type=code only** — implicit grant + id_token are rejected.
3. **RFC 8707 resource binding** — the ``resource`` parameter from
   ``/oauth/authorize/`` is propagated into ``Grant.claims`` (auth-code
   leg) and from there into ``AccessToken.claims`` (token-exchange leg).
   The MCP server's auth middleware later refuses tokens whose stored
   ``resource`` claim doesn't match ``settings.MCP_RESOURCE_URL``.

The base ``OAuth2Validator`` is huge — we only override the four hooks we
need and inherit everything else.
"""
from __future__ import annotations

from typing import Any

from oauth2_provider.oauth2_validators import OAuth2Validator


# Only ``code`` is acceptable. Implicit (``token``) is removed in OAuth 2.1
# and ``id_token`` would imply OIDC, which we don't issue.
_ALLOWED_RESPONSE_TYPES = {"code"}


class AbbyOAuth2Validator(OAuth2Validator):
    """MCP-spec invariants on top of DOT's default validator."""

    # ------------------------------------------------------------------
    # Response-type allow-list
    # ------------------------------------------------------------------

    def validate_response_type(
        self,
        client_id: str,
        response_type: str,
        client: Any,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        if response_type not in _ALLOWED_RESPONSE_TYPES:
            return False
        return super().validate_response_type(
            client_id, response_type, client, request, *args, **kwargs
        )

    # ------------------------------------------------------------------
    # Client authentication — public clients only
    # ------------------------------------------------------------------

    def client_authentication_required(self, request: Any, *args: Any, **kwargs: Any) -> bool:
        """Return False for public clients so PKCE alone authenticates them.

        A confidential client (``client_type='confidential'``) would still
        require a secret here — but DCR forces every newly-registered client
        to be public, and we don't ship admin tooling to flip that bit.
        """
        client = getattr(request, "client", None)
        if client is not None and getattr(client, "client_type", None) == "public":
            return False
        return super().client_authentication_required(request, *args, **kwargs)

    # ------------------------------------------------------------------
    # RFC 8707 — resource binding
    # ------------------------------------------------------------------

    def save_bearer_token(
        self,
        token: dict,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Bind a fresh AccessToken to its RFC 8707 ``resource`` indicator.

        Sources, in order:

          1. ``request`` attributes / ``extra_credentials`` — covers any
             future case where oauthlib propagates the param natively.
          2. **Django cache** keyed by ``request.code`` — populated by
             ``AbbyAuthorizationView.form_valid`` during the auth-code leg.
             This is the path that actually fires today; the auth-code
             token exchange comes through here.
          3. **Prior AccessToken's binding** via the inbound refresh token
             — preserves resource binding through refresh rotation.

        Missing = legacy / tooling-issued tokens; the MCP middleware lets
        those through. Auth-code-issued tokens always carry it.
        """
        super().save_bearer_token(token, request, *args, **kwargs)
        resource = self._extract_resource(request)

        if not resource:
            code = getattr(request, "code", None)
            if code:
                try:
                    from django.core.cache import cache
                    cached = cache.get(f"abby:oauth:resource:{code}")
                    if cached:
                        resource = cached
                        cache.delete(f"abby:oauth:resource:{code}")
                except Exception:  # noqa: BLE001 — cache is best-effort
                    pass

        if not resource:
            try:
                from oauth2_provider.models import RefreshToken
                from apps.mcp_server.models import MCPTokenResource
                refresh_token_value = getattr(request, "refresh_token", None)
                if refresh_token_value:
                    rt = RefreshToken.objects.select_related("access_token").filter(
                        token=refresh_token_value,
                    ).first()
                    prior = rt.access_token if rt is not None else None
                    if prior is not None:
                        binding = MCPTokenResource.objects.filter(access_token=prior).first()
                        if binding is not None:
                            resource = binding.resource
            except Exception:  # noqa: BLE001
                resource = None

        if not resource:
            return
        try:
            from oauth2_provider.models import AccessToken
            from apps.mcp_server.models import MCPTokenResource
            at = AccessToken.objects.filter(token=token["access_token"]).order_by("-id").first()
            if at is None:
                return
            MCPTokenResource.objects.update_or_create(
                access_token=at,
                defaults={"resource": resource[:512]},
            )
        except Exception:  # noqa: BLE001 — resource binding is best-effort
            return

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_resource(request: Any) -> str | None:
        """Return the RFC 8707 ``resource`` parameter from an oauthlib Request.

        oauthlib stores unrecognized parameters in a few places depending on
        which endpoint we're in. Check them in order:

          1. ``request.resource`` — attribute access (oauthlib's __getattr__
             falls back to _params for unknown attrs).
          2. ``request.extra_credentials['resource']`` — token endpoint case.
          3. ``request._params['resource']`` — raw form/query dict.
          4. The Django HTTP request stashed at ``request.django_request``
             (DOT attaches this) — last-resort for params that didn't survive
             oauthlib's parsing.
        """
        def _scalar(value):
            if not value:
                return None
            if isinstance(value, (list, tuple)):
                return value[0] if value else None
            return value

        # 1. attribute access
        try:
            resource = getattr(request, "resource", None)
        except (AttributeError, KeyError):
            resource = None
        scalar = _scalar(resource)
        if scalar:
            return scalar

        # 2. extra_credentials (token endpoint)
        extra = getattr(request, "extra_credentials", None) or {}
        scalar = _scalar(extra.get("resource"))
        if scalar:
            return scalar

        # 3. raw _params dict
        params = getattr(request, "_params", None) or getattr(request, "params", None) or {}
        try:
            scalar = _scalar(params.get("resource"))
        except AttributeError:
            scalar = None
        if scalar:
            return scalar

        # 4. Django request fallback
        django_request = getattr(request, "django_request", None)
        if django_request is not None:
            scalar = _scalar(django_request.POST.get("resource") or django_request.GET.get("resource"))
            if scalar:
                return scalar

        return None
