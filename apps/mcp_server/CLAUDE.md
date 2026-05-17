# apps/mcp_server/

MCP (Model Context Protocol) server with OAuth 2.1 + PKCE auth. The `/mcp/*` endpoint is OAuth-only and separate from the SPA's `/api/*` Token-auth path. Parent-only tools mutate state; child-allowed tools read.

## Auth — surface ladder

`/mcp/*` authenticates via `Authorization: Bearer <access_token>` resolved against `oauth2_provider.AccessToken` (django-oauth-toolkit). The DRF `Authorization: Token <key>` path that used to work against `/mcp/*` is gone — the SPA's `/api/*` calls still use Token auth, but MCP is OAuth-only and the auth middleware emits a discovery-URL hint when it sees a legacy `Token` scheme.

- **Discovery** — `GET /.well-known/oauth-protected-resource` (RFC 9728) returns `{resource, authorization_servers, scopes_supported}`; `GET /.well-known/oauth-authorization-server` (RFC 8414) returns the endpoint map. Both are public + cacheable for an hour. Probed by Cowork / mcp-remote / Claude Desktop on connect.
- **DCR** — `POST /oauth/register/` (RFC 7591) is public + throttled at `10/hour` per IP via `ScopedRateThrottle scope="oauth_register"`. Forces `client_type='public'` + `client_secret=''` + `authorization_grant_type='authorization-code'` regardless of body; returns `client_id` only.
- **Authorize** — `GET/POST /oauth/authorize/` is [`AbbyAuthorizationView`](/config/oauth_views.py), DOT's `AuthorizationView` with a **staff-parent-only gate** at dispatch (`is_staff=True` + `role='parent'`). Unauthenticated callers bounce to `/oauth/login/` (a tiny username/password form). Non-staff users render the [`forbidden.html`](/templates/oauth2_provider/forbidden.html) page. Consent screen is the project-level template at [`templates/oauth2_provider/authorize.html`](/templates/oauth2_provider/authorize.html) — `TEMPLATES['DIRS']` includes `BASE_DIR / 'templates'` so it wins over DOT's app-shipped default.
- **Token + revoke + introspect** — `POST /oauth/token/`, `POST /oauth/revoke_token/`, etc., from the `oauth2_provider.urls` include. PKCE S256 is required (`PKCE_REQUIRED=True` in `OAUTH2_PROVIDER` settings); refresh tokens rotate.
- **Resource binding (RFC 8707)** — every token carries a `claims['resource']` JSON field set to the value the auth-code request carried in `?resource=...`. The MCP middleware refuses tokens whose claim doesn't match `settings.MCP_RESOURCE_URL` — a missing claim is treated as legacy (test fixtures, admin-created tokens) and accepted. Stamping happens in [`AbbyOAuth2Validator.save_authorization_code`](/config/oauth_validator.py) → Grant.claims → AccessToken.claims.
- **Admin surface** — `/manage → Admin → OAuth clients` (the [`OAuthClientsCard`](/frontend/src/pages/Manage.jsx) sub-section) lists registered Applications + active AccessTokens and offers revoke buttons; gated by the existing `adminPing()` probe (no second ping needed). Backed by `/api/admin/oauth/applications/` + `/api/admin/oauth/tokens/` (and matching DELETE endpoints), all on `IsStaffParent` semantics.
- **Test factory** — [`make_oauth_token(user, *, application=None, resource=None, scope='mcp', expires_in_seconds=3600)`](/config/tests/factories.py) mints an `AccessToken` row directly so MCP tests don't have to do the PKCE round-trip. Returns `(access_token, "Bearer <token>")`. The end-to-end PKCE flow (DCR → authorize → token → refresh) is covered exactly once in [`config/tests/test_oauth.py::EndToEndPKCEFlowTests`](/config/tests/test_oauth.py).
- **Env vars** — `MCP_PUBLIC_BASE_URL` is the single switch (e.g. `https://abby.bos.lol/mcp`). [`config/settings.py`](/config/settings.py) derives `SITE_URL` (origin stripped from it → OAuth issuer + endpoint URLs) and `MCP_RESOURCE_URL` (the RFC 8707 resource indicator, equals `MCP_PUBLIC_BASE_URL` verbatim) from that one value. When `MCP_PUBLIC_BASE_URL` is empty, both fall back to `http://localhost:8000` for local dev. Production deployments MUST set it — otherwise the discovery JSON advertises `localhost` endpoints that Cowork / mcp-remote can't reach. Other settings: `OAUTH2_PROVIDER` dict + `LOGIN_URL='/oauth/login/'` in [`config/settings.py`](/config/settings.py).

## Context helpers (`apps/mcp_server/context.py`)

- `get_current_user` — resolves the requesting user from the Bearer token.
- `require_parent` — guard for parent-only tools.
- `require_staff_parent` — gates global-content authoring inside MCP, mirroring the DRF `IsStaffParent` permission.
- `resolve_target_user(user, requested_id)` — child→self + same-family scoping for MCP tools that accept an optional `user_id`. Cross-family requests raise `MCPNotFoundError` (NOT permission-denied — never leak existence of a sibling family's user).
- `get_in_family(model, pk, family)` — replaces bare `Model.objects.get(pk=...)` calls in MCP tools, raising `MCPNotFoundError` on cross-family probes (existence-leak preventing).

`get_in_family` + `require_staff_parent` were added in commit `cbd5182` as part of the 7-chokepoint multi-family scoping contract. The 7 ARE the contract — adding new MCP tools just calls them.

## Tools

Tools are grouped under `apps/mcp_server/tools/`. Parent-only tools must call `require_parent()` (or `require_staff_parent()` for global content). Tools that accept an optional `user_id` must run it through `resolve_target_user`. Tools that look up objects by pk must use `get_in_family`.

Sprite authoring tools (see `apps/rpg/CLAUDE.md` for the full surface): `register_sprite`, `register_sprite_batch`, `list_sprites`, `get_sprite`, `delete_sprite`, `update_sprite_metadata`, `generate_sprite_sheet`, `propose_sprite_reroll`, `reroll_sprite`, `get_sprite_prompting_playbook`.

## Gotchas

See [the multi-family scoping rule in root CLAUDE.md](/CLAUDE.md) — the 7 chokepoints include MCP's `resolve_target_user` and `get_in_family`. Cross-family probes return `MCPNotFoundError` (404 semantics), never permission-denied. Chronicle services in MCP tools must use `timezone.localdate()` (Phoenix-local), not naive UTC dates, so chapter-year + birthday-event boundaries don't drift around midnight.

## Key entry points
- `auth.py` — MCP Bearer auth middleware.
- `context.py` — `get_current_user`, `require_parent`, `require_staff_parent`, `resolve_target_user`, `get_in_family`, `MCPNotFoundError`, `MCPValidationError`.
- `tools/` — per-feature tool modules.
- `tests/test_family_scoping.py` — cross-family probe tests.
- `/config/oauth_views.py`, `/config/oauth_validator.py` — DOT integration + resource binding.
- `/config/tests/test_oauth.py::EndToEndPKCEFlowTests` — end-to-end PKCE coverage.
