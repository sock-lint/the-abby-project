# apps/mcp_server/

MCP (Model Context Protocol) server with OAuth 2.1 + PKCE auth. The `/mcp/*` endpoint is OAuth-only and separate from the SPA's `/api/*` Token-auth path. HTTP access requires an active staff parent. Tool handlers retain their role, family, ownership and private-journal checks; local synthetic tests also exercise child-scoped behavior.

## Auth — surface ladder

`/mcp/*` authenticates via `Authorization: Bearer <access_token>` resolved against `oauth2_provider.AccessToken` (django-oauth-toolkit). The DRF `Authorization: Token <key>` path that used to work against `/mcp/*` is gone — the SPA's `/api/*` calls still use Token auth, but MCP is OAuth-only and the auth middleware emits a discovery-URL hint when it sees a legacy `Token` scheme.

- **Discovery** — `GET /.well-known/oauth-protected-resource` (RFC 9728) returns `{resource, authorization_servers, scopes_supported}`; `GET /.well-known/oauth-authorization-server` (RFC 8414) returns the endpoint map. Both are public + cacheable for an hour. Probed by Cowork / mcp-remote / Claude Desktop on connect.
- **DCR** — `POST /oauth/register/` (RFC 7591) is public + throttled at `10/hour` per IP via `ScopedRateThrottle scope="oauth_register"`. Forces `client_type='public'` + `client_secret=''` + `authorization_grant_type='authorization-code'` regardless of body; returns `client_id` only.
- **Authorize** — `GET/POST /oauth/authorize/` is [`AbbyAuthorizationView`](/config/oauth_views.py), DOT's `AuthorizationView` with a **staff-parent-only gate** at dispatch (`is_staff=True` + `role='parent'`). Unauthenticated callers bounce to `/oauth/login/` (a tiny username/password form). Non-staff users render the [`forbidden.html`](/templates/oauth2_provider/forbidden.html) page. Consent screen is the project-level template at [`templates/oauth2_provider/authorize.html`](/templates/oauth2_provider/authorize.html) — `TEMPLATES['DIRS']` includes `BASE_DIR / 'templates'` so it wins over DOT's app-shipped default.
- **Token + revoke + introspect** — `POST /oauth/token/`, `POST /oauth/revoke_token/`, etc., from the `oauth2_provider.urls` include. PKCE S256 is required (`PKCE_REQUIRED=True` in `OAUTH2_PROVIDER` settings); refresh tokens rotate.
- **Resource binding (RFC 8707)** — authorization requests must specify exactly `settings.MCP_RESOURCE_URL`. `MCPAuthorizationResource` durably binds the authorization code to that resource; `MCPTokenResource` binds the issued token. Issuance is transactional: binding failure cannot produce an accepted unbound token. Code exchange and refresh preserve the approved resource and recheck current staff-parent privileges. Missing, empty and wrong resource bindings are rejected; there is no legacy fallback.
- **Scopes and consent** — `mcp:catalog`, `mcp:author`, `mcp:publish`, `mcp:read` and `mcp:write` are independent grants. New consent defaults to global catalog reads without household data and always shows the requested permissions. Discovery and invocation enforce `tool_policy.py`; unknown tool names fail registration. All tools publish read-only/destructive/idempotency/open-world annotations. Destructive operations additionally require top-level `arguments.confirmation: true` after the client obtains user confirmation; annotations and flags do not establish human or Google-data consent by themselves.
- **Existing connections** — broad `mcp` tokens and unbound tokens must reconnect. Do not upgrade old grants or infer write permission. Losing staff status, being deactivated or changing away from parent also blocks existing access and refresh. Migrate the new grant-binding table before serving the changed OAuth endpoints.
- **Login throttle** — `/oauth/login/` has a transport-peer `oauth_login` throttle (10/minute by default), sharing the configured Django cache. It ignores client-supplied forwarded-IP headers; clients behind one proxy share this conservative limit. Rejected attempts receive HTTP 429 before password authentication once the configured limit is reached.
- **Admin surface** — `/manage → Admin → OAuth clients` (the [`OAuthClientsCard`](/frontend/src/pages/Manage.jsx) sub-section) distinguishes server-wide registered Applications from the current user's unexpired AccessTokens. DCR precedes authorization; a registration does not mean consent or sign-in completed. An empty token list means no current unexpired access token for this user, not proof about another user or the client's callback outcome. Client-wide revocation affects every user of that registration; single-token revocation is caller-owned. Gated by the existing `adminPing()` probe (no second ping needed). Backed by `/api/admin/oauth/applications/` + `/api/admin/oauth/tokens/` (and matching DELETE endpoints), all on `IsStaffParent` semantics.
- **Test factory** — [`make_oauth_token(user, *, application=None, resource=None, scope='mcp:read', expires_in_seconds=3600)`](/config/tests/factories.py) mints an `AccessToken` row directly so MCP tests don't have to do the PKCE round-trip. Returns `(access_token, "Bearer <token>")`. The end-to-end PKCE flow (DCR → authorize → token → refresh) is covered exactly once in [`config/tests/test_oauth.py::EndToEndPKCEFlowTests`](/config/tests/test_oauth.py).
- **Env vars** — `MCP_PUBLIC_BASE_URL` is the single switch (e.g. `https://abby.bos.lol/mcp`). [`config/settings.py`](/config/settings.py) derives `SITE_URL` (origin stripped from it → OAuth issuer + endpoint URLs) and `MCP_RESOURCE_URL` (the RFC 8707 resource indicator, equals `MCP_PUBLIC_BASE_URL` verbatim) from that one value. When `MCP_PUBLIC_BASE_URL` is empty, both fall back to `http://localhost:8000` for local dev. Production deployments MUST set it — otherwise the discovery JSON advertises `localhost` endpoints that Cowork / mcp-remote can't reach. Other settings: `OAUTH2_PROVIDER` dict + `LOGIN_URL='/oauth/login/'` in [`config/settings.py`](/config/settings.py).

See [native Codex setup and troubleshooting](../../docs/operations/mcp-authoring.md#connect-codex-in-a-normal-browser)
for resource discovery, normal PWA updates and the remote browser/SSH workflow.
The browser's OAuth routes (including query strings) must bypass Workbox's SPA
navigation fallback as well as Django's catch-all. Existing clients receive the
new worker through the normal guarded update banner. Native Codex owns URL
construction, callback state and its success page; verify terminal completion
and authenticated discovery, not registration or browser text. Preserve working
grants; never log codes, tokens or full authorization/callback URLs.

The authenticated `abby://mcp/capabilities` resource reports the current grant,
workflow purposes, required scopes and availability flags without household
records. Server initialization instructions direct clients there. It is a
resource rather than an additional tool, and grants or upgrades no permissions;
additional scopes require explicit OAuth reconnection.

## Context helpers (`apps/mcp_server/context.py`)

- `get_current_user` — resolves the requesting user from the Bearer token.
- `require_parent` — guard for parent-only tools.
- `require_staff_parent` — gates global-content authoring inside MCP, mirroring the DRF `IsStaffParent` permission.
- `resolve_target_user(user, requested_id)` — child→self + same-family scoping for MCP tools that accept an optional `user_id`. Cross-family requests raise `MCPNotFoundError` (NOT permission-denied — never leak existence of a sibling family's user).
- `get_in_family(model, pk, family)` — replaces bare `Model.objects.get(pk=...)` calls in MCP tools, raising `MCPNotFoundError` on cross-family probes (existence-leak preventing).

`get_in_family` + `require_staff_parent` were added in commit `cbd5182` as part of the 7-chokepoint multi-family scoping contract. The 7 ARE the contract — adding new MCP tools just calls them.

## Tools

Taxonomy lists default to effective available choices; `include_retired=true`
includes saved categories/skills for management/history. Existing `update_category`,
`update_subject` and `update_skill` accept reversible `is_retired`. Retirement also
hides descendants through `available_for_new_choices`, retaining their own flags.
Trees, saved XP, existing tags and accepted rewards keep exact identities. New
reference writers reject retired choices under transactional ancestor locks.
Read [taxonomy authoring](../../docs/operations/mcp-authoring.md) before changing
this boundary; default managers and award resolution must remain unfiltered.

Tools are grouped under `apps/mcp_server/tools/`. Parent-only tools must call `require_parent()` (or `require_staff_parent()` for global content). Tools that accept an optional `user_id` must run it through `resolve_target_user`. Tools that look up objects by pk must use `get_in_family`.

`list_timecards` accepts `status="closed"` for approved zero-dollar weeks that
a parent closed without a payout. Existing child-self and parent-family scoping
also apply to this history filter.

`record_payout` confirms a transfer already completed in Greenlight; it never sends money. It requires `transferred_on` and a stable `idempotency_key` alongside child `user_id` and positive cent-precision `amount`. Retry with identical details and the same key. Optional `reference`, `description` (memo), and `timecard_id` use the same family-scoped, approved-payable, duplicate-safe service as the REST workflow. A timecard must be approved and paid in full. Payment balances describe money still owed, separately from externally observed Greenlight balance snapshots; see [payments guidance](/apps/payments/CLAUDE.md).

Prepared-art tools are `register_sprite`, `register_sprite_batch`, `list_sprites`, `get_sprite`, `delete_sprite`, `update_sprite_metadata`, plus filesystem pack registration through `register_sprite_assets`. Writes require staff parent and `mcp:publish`. AI image/sprite generation, rerolling and prompt/playbook tools are retired. Historical sprite images and stored metadata remain readable.

The complete [tool inventory](../../docs/mcp-tools.md) records the enforced scope and confirmation requirement for all 267 tools across 37 modules. Names do not determine permission: `get_daily_challenge` and `list_cosmetics` can create records and require `mcp:write`.

`list_homework` and `get_homework` share an active-assignment queryset scoped to
the parent's family or the child's own assignments. Foreign and missing detail
IDs both return not found; child filters never expand the child's visibility.

### History pagination and results

`list_projects` and `list_payment_ledger` accept a bounded `cursor` alongside
their existing filters and page limits. Both return `total`, `has_more` and
nullable `next_cursor`; projects retain `projects` and page-length `count`, and
payments retain `entries`. Continue with the same actor, family and filters.
Cursors are signed, expire after 24 hours, and use descending creation time
plus primary key for tied timestamps. The initial maximum ID excludes later
inserts, including backdated ones. Every page rechecks authorization. `total`
counts currently matching authorized rows within that ID boundary; deletions,
reassignment or filter-field edits can change it. This is not a database snapshot.

Changed project/payment history, project detail/create, payment mutation,
movement detail/log, redemption and catalog-read results expose concrete field
schemas through `outputSchema`. The four reading tools also have explicit
result schemas. Existing serializer extension fields remain supported; this
does not make every registered result fully typed. See `output_schemas.py` and
`reading_schemas.py` for the exact field contracts.

Wire tool failures set `isError: true` and include matching JSON text and a
`structuredContent.error` object with `code`, `message`, `retryable` and `field_errors`.
Input field errors use argument paths such as `params.title`. Permission,
not-found, confirmation, validation and retry-conflict codes are distinct;
unexpected failures return a generic `internal_error` without exception details.
This tool-result contract is separate from HTTP authentication failures and
JSON-RPC protocol errors.

### Retry identities

These mutation inputs require a stable UUID for the exact operation:

| Tool | Required UUID field |
| --- | --- |
| `create_project` | `request_id` |
| `adjust_payment` | `request_id` |
| `request_redemption` | `request_id` |
| `log_movement_session` | `client_request_id` |

Identical retries return the persisted original response without another
project, payment, redemption, stock reservation or movement award. Reusing a
UUID with changed details returns `idempotency_conflict`. Current account,
family and source ownership are rechecked on replay; a deleted source retains
the request tombstone and cannot be recreated with its old UUID. Migrate
`0004_mcpmutationreceipt` before serving these contracts. Destructive tools still
require transport confirmation on each call.

The first three operations bind UUIDs to actor and operation; movement binds
them to target and operation, matching its native retry identity across
authorized callers. Source deletion clears cached response data while retaining
the UUID tombstone. Member deletion clears the family's cached responses and
removes actor-scoped receipts; movement tombstones survive the actor's departure
while the target survives. Cleared receipts fail not-found without re-execution.
Receipt responses are bounded to 256 KiB and commit with the domain write.

### Reading

`list_reading_books` and `get_reading_summary` require `mcp:read`;
`create_reading_book` and `log_reading_session` require `mcp:write`. Parents must
explicitly choose a same-family child with `user_id`; children remain
self-scoped. Shelf reads paginate in ascending ID order using `after`,
`next_after` and `has_more`. They do not log reading or award anything.

Reading creates use required UUID `client_request_id` values and the same
validation, membership locks and services as REST. Identical retries return the
current saved record; changed details conflict. A session references the child's
own book and includes minutes, pages, section or reflection. Dates default to the
family-local day and cannot be in the future. `reading_reward` and summary
`reading_adventure` report actual saved reward evidence, with the usual daily
caps; saving a book earns nothing. Reflections never become reward context.
See [reading guidance](../reading/CLAUDE.md) for reward and retention semantics.

Modern goal preview/create also accept `trigger_type="reading_logged"` with
`metric="count"` and `unit="actions"`. Each action counts an actual awarded
daily Reading Adventure receipt, not individual logs, books, pages or minutes.

Pet acquisition uses `get_pet_incubation` (read), `start_pet_incubation` and
`claim_pet_incubation` (confirmed writes). Start consumes the egg/potion once,
using a UUID request ID for safe retries, and creates no owned pet. Readiness is
server-owned; a read or elapsed timer cannot hatch automatically. Only an explicit
ready claim creates the pet and its normal badge/Chronicle effects. Exact-ID claim
retries return the same pet. All three use the usual self/same-family target rules.
The instant `hatch_pet` tool is retired and unregistered; there is no MCP timer bypass.

## Content workflows

See [RPG MCP authoring](../../docs/operations/mcp-authoring.md) for the full
workflow. `mcp:catalog` reads global references/rules without player state;
`mcp:author` owns drafts and review plans; `mcp:publish` changes the runtime
catalog. Pack publication requires the same actor/family, expiring preview ID,
source digest and exact reviewed catalog diff. Unowned legacy drafts require
reconciliation. Author/proposal audit actor FKs preserve evidence with SET_NULL
when accounts are deleted; do not block existing account deletion with PROTECT.

`challenge_reconciliation.py` provides dedicated preview/get/publish tools for
one explicit conflicting system-definition pair. Author reads/plans and
confirmed publication use separate scopes and concrete global-only results.
The native service owns fresh account authorization and mutex-first admission:
do not put an outer `authorized_household` transaction around preview/publish.
Receipts bind exact source, ownership and accepted-goal state without exposing
household identities or counts; cooperative differences need a separate strict
acknowledgment. Source rows, accepted promises and repeat cadence are preserved.
See [canonical reconciliation](../../docs/operations/mcp-authoring.md#canonical-challenge-reconciliation).

`challenges.py` uses the current goal serializer/service, required UUID creation,
saved-state-only audit and self/family pins. Reads never call materializing
`list_goals`. Saved rows include retry eligibility, closed-attempt reasons,
qualifying triggers and versioned future-week setup through the shared payload;
the audit batches this metadata without creating attempts or weekly promises.
Explicit retry and schedule changes use `rpg_management.py` with confirmed
`mcp:write` operations. The `challenges.py` reader `get_voyager_feedback` accepts only empty
`params` and returns the bounded current-family aggregate, saved policy groups,
mature-outcome denominators, unknown evidence and trusted-test-family exclusion.
It requires a staff parent and the separate `mcp:read` grant. The observer's
current family, role, activity and staff authority remain locked through report
materialization. `economy.py` separates actual ledger accounting from anonymous
projections; receipt totals overlap ledger amounts. `catalog.py` paginates
global content and audits runtime eligibility without private player records.
`asset_proposals.py` saves family briefs and paginated history, exports reviewed
JSON and records unverified external delivery claims. These tools generate,
download, approve and publish no artwork.

MCP transfers permitted results to an external client. See the [Google/AI disclosure inventory](../../docs/operations/google-ai-disclosure.md) for Google-derived data, external-provider controls and evidence required before any compliance claim.

## Gotchas

See [the multi-family scoping rule in root CLAUDE.md](/CLAUDE.md) — the 7 chokepoints include MCP's `resolve_target_user` and `get_in_family`. Cross-family probes return `MCPNotFoundError` (404 semantics), never permission-denied. Chronicle services in MCP tools must use `timezone.localdate()` (Phoenix-local), not naive UTC dates, so chapter-year + birthday-event boundaries don't drift around midnight.

## Connection verification

`scripts/smoke_mcp.py` is a read-only OAuth client. Supply an existing access
token through `MCP_TOKEN` and choose the server origin with `--base-url` or
`MCP_BASE_URL` (default `http://127.0.0.1:8000`). It appends `/mcp`, initializes,
checks permission-filtered discovery and invokes available catalog reads. It
prints counts and fixed error categories, never tokens or response bodies. It
does not log in or mutate records. The retired `--full` mode refuses before
network access; write checks belong in disposable Django tests.

## Key entry points
- `auth.py` — staff-parent Bearer authentication with exact scopes and resource bindings.
- `tool_policy.py` — explicit default-deny scope/annotation/confirmation policy.
- `pagination.py` — signed, caller-bound project/payment history cursors.
- `retries.py` — atomic mutation receipts, current authorization and deletion tombstones.
- `output_schemas.py`, `reading_schemas.py` — concrete result contracts on changed tools.
- `models.py` — durable authorization-code and token resource bindings.
- `context.py` — `get_current_user`, `require_parent`, `require_staff_parent`, `resolve_target_user`, `get_in_family`, `MCPNotFoundError`, `MCPValidationError`.
- `tools/` — per-feature tool modules.
- `tests/test_family_scoping.py` — cross-family probe tests.
- `/config/oauth_views.py`, `/config/oauth_validator.py` — DOT integration + resource binding.
- `/config/tests/test_oauth.py::EndToEndPKCEFlowTests` — end-to-end PKCE coverage.


### Content and RPG management

The workbench, editorial, effective-rule, household RPG and reading maintenance
modules wrap native services and publish explicit result schemas. See the
[authoring guide](../../docs/operations/mcp-authoring.md#existing-catalog-editing-and-progression-evaluation)
for scopes, revisions, replay identities, quotas and publication contracts.
Private reads/replays and household materialization retain current-account
checks under family/member locks. Catalog projections omit household usage.
Editorial publication edits copy/selection; installed mechanics and assets remain
separate reviewed changes. Taxonomy hard deletes remove only unused, unmanaged
leaves. Referenced or managed definitions report `taxonomy_in_use`; saved progress,
earned badges, tags and challenge promises are preserved. REST shares the same
deletion service. Reviewed publication/versioning governs source retirement.
