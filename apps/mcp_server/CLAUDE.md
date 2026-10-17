# apps/mcp_server/

MCP (Model Context Protocol) server with OAuth 2.1 + PKCE auth. The `/mcp/*` endpoint is OAuth-only and separate from the SPA's `/api/*` Token-auth path. HTTP access requires an active staff parent. Tool handlers retain their role, family, ownership and private-journal checks; local synthetic tests also exercise child-scoped behavior.

## Auth — surface ladder

`/mcp/*` authenticates via `Authorization: Bearer <access_token>` resolved against `oauth2_provider.AccessToken` (django-oauth-toolkit). The DRF `Authorization: Token <key>` path that used to work against `/mcp/*` is gone — the SPA's `/api/*` calls still use Token auth, but MCP is OAuth-only and the auth middleware emits a discovery-URL hint when it sees a legacy `Token` scheme.

- **Discovery** — `GET /.well-known/oauth-protected-resource` (RFC 9728) returns `{resource, authorization_servers, scopes_supported}`; `GET /.well-known/oauth-authorization-server` (RFC 8414) returns the endpoint map. Both are public + cacheable for an hour. Probed by Cowork / mcp-remote / Claude Desktop on connect.
- **DCR** — `POST /oauth/register/` (RFC 7591) is public + throttled at `10/hour` per IP via `ScopedRateThrottle scope="oauth_register"`. Forces `client_type='public'` + `client_secret=''` + `authorization_grant_type='authorization-code'` regardless of body; returns `client_id` only.
- **Authorize** — `GET/POST /oauth/authorize/` is [`AbbyAuthorizationView`](/config/oauth_views.py), DOT's `AuthorizationView` with a **staff-parent-only gate** at dispatch (`is_staff=True` + `role='parent'`). Unauthenticated callers bounce to `/oauth/login/` (a tiny username/password form). Non-staff users render the [`forbidden.html`](/templates/oauth2_provider/forbidden.html) page. Consent screen is the project-level template at [`templates/oauth2_provider/authorize.html`](/templates/oauth2_provider/authorize.html) — `TEMPLATES['DIRS']` includes `BASE_DIR / 'templates'` so it wins over DOT's app-shipped default.
- **Token + revoke + introspect** — `POST /oauth/token/`, `POST /oauth/revoke_token/`, etc., from the `oauth2_provider.urls` include. PKCE S256 is required (`PKCE_REQUIRED=True` in `OAUTH2_PROVIDER` settings); refresh tokens rotate.
- **Resource binding (RFC 8707)** — authorization requests must specify exactly `settings.MCP_RESOURCE_URL`. `MCPAuthorizationResource` durably binds the authorization code to that resource; `MCPTokenResource` binds the issued token. Issuance is transactional: binding failure cannot produce an accepted unbound token. Code exchange and refresh preserve the approved resource and recheck current staff-parent privileges. Missing, empty and wrong resource bindings are rejected; there is no legacy fallback.
- **Scopes and consent** — `mcp:read`, `mcp:write` and `mcp:author` are independent grants. New consent defaults to read only and always shows the requested permissions. Discovery and invocation enforce `tool_policy.py`; unknown tool names fail registration. All tools publish read-only/destructive/idempotency/open-world annotations. Destructive operations additionally require top-level `arguments.confirmation: true` after the client obtains user confirmation; annotations and flags do not establish human or Google-data consent by themselves.
- **Existing connections** — broad `mcp` tokens and unbound tokens must reconnect. Do not upgrade old grants or infer write permission. Losing staff status, being deactivated or changing away from parent also blocks existing access and refresh. Migrate the new grant-binding table before serving the changed OAuth endpoints.
- **Login throttle** — `/oauth/login/` has an IP-based `oauth_login` throttle, sharing the configured Django cache. Rejected attempts receive HTTP 429 before password authentication once the configured limit is reached.
- **Admin surface** — `/manage → Admin → OAuth clients` (the [`OAuthClientsCard`](/frontend/src/pages/Manage.jsx) sub-section) lists registered Applications + active AccessTokens and offers revoke buttons; gated by the existing `adminPing()` probe (no second ping needed). Backed by `/api/admin/oauth/applications/` + `/api/admin/oauth/tokens/` (and matching DELETE endpoints), all on `IsStaffParent` semantics.
- **Test factory** — [`make_oauth_token(user, *, application=None, resource=None, scope='mcp:read', expires_in_seconds=3600)`](/config/tests/factories.py) mints an `AccessToken` row directly so MCP tests don't have to do the PKCE round-trip. Returns `(access_token, "Bearer <token>")`. The end-to-end PKCE flow (DCR → authorize → token → refresh) is covered exactly once in [`config/tests/test_oauth.py::EndToEndPKCEFlowTests`](/config/tests/test_oauth.py).
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

`list_timecards` accepts `status="closed"` for approved zero-dollar weeks that
a parent closed without a payout. Existing child-self and parent-family scoping
also apply to this history filter.

`record_payout` confirms a transfer already completed in Greenlight; it never sends money. It requires `transferred_on` and a stable `idempotency_key` alongside child `user_id` and positive cent-precision `amount`. Retry with identical details and the same key. Optional `reference`, `description` (memo), and `timecard_id` use the same family-scoped, approved-payable, duplicate-safe service as the REST workflow. A timecard must be approved and paid in full. Payment balances describe money still owed, separately from externally observed Greenlight balance snapshots; see [payments guidance](/apps/payments/CLAUDE.md).

Prepared-art tools are `register_sprite`, `register_sprite_batch`, `list_sprites`, `get_sprite`, `delete_sprite`, `update_sprite_metadata`, plus filesystem pack registration through `register_sprite_assets`. Writes require staff parent and `mcp:author`. AI image/sprite generation, rerolling and prompt/playbook tools are retired. Historical sprite images and stored metadata remain readable.

The complete [tool inventory](../../docs/mcp-tools.md) records the enforced scope and confirmation requirement for all 203 tools. Names do not determine permission: `get_daily_challenge` and `list_cosmetics` can create records and require `mcp:write`.

MCP transfers permitted results to an external client. See the [Google/AI disclosure inventory](../../docs/operations/google-ai-disclosure.md) for Google-derived data, external-provider controls and evidence required before any compliance claim.

## Gotchas

See [the multi-family scoping rule in root CLAUDE.md](/CLAUDE.md) — the 7 chokepoints include MCP's `resolve_target_user` and `get_in_family`. Cross-family probes return `MCPNotFoundError` (404 semantics), never permission-denied. Chronicle services in MCP tools must use `timezone.localdate()` (Phoenix-local), not naive UTC dates, so chapter-year + birthday-event boundaries don't drift around midnight.

## Key entry points
- `auth.py` — staff-parent Bearer authentication with exact scopes and resource bindings.
- `tool_policy.py` — explicit default-deny scope/annotation/confirmation policy.
- `models.py` — durable authorization-code and token resource bindings.
- `context.py` — `get_current_user`, `require_parent`, `require_staff_parent`, `resolve_target_user`, `get_in_family`, `MCPNotFoundError`, `MCPValidationError`.
- `tools/` — per-feature tool modules.
- `tests/test_family_scoping.py` — cross-family probe tests.
- `/config/oauth_views.py`, `/config/oauth_validator.py` — DOT integration + resource binding.
- `/config/tests/test_oauth.py::EndToEndPKCEFlowTests` — end-to-end PKCE coverage.
