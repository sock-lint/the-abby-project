"""Test factories for family-aware setUp blocks.

Use ``make_family(parents=[...], children=[...])`` instead of inlining
``User.objects.create_user(...)`` per test, so every user winds up in
exactly one family and family-scoping assertions work without ceremony.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable, Mapping


def make_family(
    name: str = "Test Family",
    *,
    parents: Iterable[Mapping] = (),
    children: Iterable[Mapping] = (),
):
    """Create a Family with attached parents and children.

    Each ``parents`` / ``children`` entry is a dict with at least
    ``username`` (other keys flow through as ``create_user`` kwargs —
    ``display_name``, ``hourly_rate``, ``date_of_birth`` etc.). The first
    parent (if any) is set as ``primary_parent``.

    Returns ``SimpleNamespace(family=Family, parents=[User], children=[User])``.
    """
    from django.contrib.auth import get_user_model
    from apps.families.models import Family

    User = get_user_model()
    family = Family.objects.create(name=name)
    parent_objs = []
    for p in parents:
        kwargs = {"password": "pw", "role": "parent", "family": family, **dict(p)}
        parent_objs.append(User.objects.create_user(**kwargs))
    if parent_objs and family.primary_parent_id is None:
        family.primary_parent = parent_objs[0]
        family.save(update_fields=["primary_parent"])
    child_objs = []
    for c in children:
        kwargs = {"password": "pw", "role": "child", "family": family, **dict(c)}
        child_objs.append(User.objects.create_user(**kwargs))
    return SimpleNamespace(family=family, parents=parent_objs, children=child_objs)


def make_oauth_token(
    user,
    *,
    application=None,
    resource: str | None = None,
    scope: str = "mcp",
    expires_in_seconds: int = 3600,
):
    """Mint an OAuth ``AccessToken`` row directly (skip the PKCE round-trip).

    Tests against ``/mcp/*`` that need a Bearer token just want a working
    one — the auth-code flow round-trip is exercised end-to-end in
    ``config/tests/test_oauth.py`` and doesn't need to repeat in every
    MCP tool test.

    Returns ``(access_token, header_value)`` where ``header_value`` is the
    pre-formatted ``"Bearer <token>"`` string callers can pass directly to
    ``client.get(..., HTTP_AUTHORIZATION=header_value)`` or to the MCP
    Starlette middleware.

    ``resource`` defaults to ``settings.MCP_RESOURCE_URL`` so the token
    passes the auth middleware's RFC 8707 binding check. Pass an explicit
    different value (or ``""``) to exercise the rejection path.
    """
    import secrets
    from django.conf import settings as _settings
    from django.utils import timezone
    from datetime import timedelta
    from oauth2_provider.models import AccessToken, Application
    from apps.mcp_server.models import MCPTokenResource

    if application is None:
        application, _ = Application.objects.get_or_create(
            name="Test MCP client",
            defaults={
                "user": None,
                "client_type": Application.CLIENT_PUBLIC,
                "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
                "redirect_uris": "http://localhost:9999/callback",
                "client_secret": "",
                "skip_authorization": False,
            },
        )

    if resource is None:
        resource = getattr(_settings, "MCP_RESOURCE_URL", "") or ""

    token_value = secrets.token_urlsafe(32)
    access = AccessToken.objects.create(
        user=user,
        application=application,
        token=token_value,
        expires=timezone.now() + timedelta(seconds=expires_in_seconds),
        scope=scope,
    )
    if resource:
        MCPTokenResource.objects.create(access_token=access, resource=resource[:512])
    return access, f"Bearer {token_value}"
