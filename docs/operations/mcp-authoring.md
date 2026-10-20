# RPG content authoring and auditing through MCP

Abby's MCP supports external assistants creating projects, challenges and RPG
content. The assistant drafts and explains; Django owns validation, family
access, reward calculations and saved progression. These tools add no embedded
LLM or image-generation provider. Prepared artwork comes from the external
asset-production process.

## Permissions

Permissions are independent; request only those needed for the task:

| Scope | Purpose |
| --- | --- |
| `mcp:catalog` | Global content references, effective catalog audits, economy rules and anonymous scenario comparisons. New connections default to this scope. |
| `mcp:author` | Private family-owned content-pack drafts, validation/publication previews and asset proposal briefs. |
| `mcp:publish` | Apply reviewed content packs and change global catalog definitions or prepared artwork. |
| `mcp:read` | Permitted household records, saved challenge progress, actual Coin ledgers and award evidence. |
| `mcp:write` | Create/change permitted household records, including parent challenge goals and project templates. |

Catalog access includes no child progress, journals, payments or household
ledgers. The skill tree with a child's progress remains a household read;
catalog skill definitions are separate. Household-specific shop offers and
parent-authored challenges do not become global catalog references.

HTTP MCP remains restricted to active staff parents. Scope checks also apply
to invocation of tools hidden from discovery. Global publication requires
`mcp:publish`; a draft grant alone cannot publish. Reconnect to explicitly grant
the desired permissions; old grants are never upgraded. A destructive tool
requires top-level `arguments.confirmation: true` alongside `params`, after the
client obtains confirmation. This flag is a client acknowledgement, not proof
of a person's approval or Google-data consent.

## Tool results and safe retries

Discover the tool's current input and `outputSchema` before building a client.
Project/payment history, project create/detail, payment mutations, movement
log/detail, redemption and catalog reads expose concrete result fields. The
four reading tools also declare their result fields. Other tools retain their
existing response contracts; this is not a claim that every tool result has a
complete field schema. Existing serializer extension fields remain supported.

Wire tool failures return `isError: true` and the following shape in
`structuredContent`, with matching JSON in the text content:

```json
{
  "error": {
    "code": "invalid_input",
    "message": "Check the indicated tool arguments.",
    "retryable": false,
    "field_errors": {"params.title": ["Field required"]}
  }
}
```

Use the code and field paths to repair a request. Permission, not-found,
confirmation, validation and idempotency-conflict failures have distinct codes.
Unexpected failures use a generic `internal_error`; they do not expose an
exception or traceback. HTTP authentication and JSON-RPC protocol errors retain
their separate transport contracts. A timeout or uncertain result is a reason to
inspect saved state and reuse an operation's retry identity, not invent a new one.

The following writes require UUIDs; omitting the field is an input error:

| Tool | UUID field | Transport confirmation |
| --- | --- | --- |
| `create_project` | `request_id` | Not required |
| `adjust_payment` | `request_id` | Required |
| `request_redemption` | `request_id` | Required |
| `log_movement_session` | `client_request_id` | Not required |

Generate one UUID for the intended operation, then preserve its exact details
and UUID across retries. An identical retry returns its original saved response
without a second project, ledger entry, Coin debit, stock reservation or movement
award. Changed details under the same UUID return `idempotency_conflict`.
Replays recheck current account, family and source ownership. A deleted source
leaves a request tombstone; retrying its old UUID cannot recreate it. Retry
identity does not replace authorization or confirmation.

Project creation, payment adjustments and redemption UUIDs are scoped to the
actor and operation. Movement UUIDs belong to the target child's activity
history, so another currently authorized caller cannot replay a deleted session
as new work. Account deletion clears cached household responses; a surviving
movement tombstone retains no response prose. A cleared response returns
not-found rather than executing its operation again. Responses larger than
256 KiB are rejected atomically; use a smaller project request.

Read the authenticated `abby://mcp/capabilities` resource for the connection's
`granted_scopes` and workflow purposes, `required_scopes` and `available` flags.
It includes retry/error guidance without household records. Initialization
instructions point clients to this resource; it adds no tool and grants or
upgrades no permission. Reconnect through explicit OAuth consent when another
scope is needed.

## Connect Codex in a normal browser

An existing Abby account must be an active **staff parent** to authorize MCP.
The Abby app's saved sign-in and Django's OAuth browser session are separate;
the OAuth form may ask for the same Abby username and password again. The
resulting consent page shows the requested scopes. Start with `mcp:catalog`;
granting it does not grant authoring, publication or household access.

For a new native Codex connection, use the Streamable HTTP endpoint and let
Codex discover the resource and authorization endpoints:

```toml
[mcp_servers.abby]
url = "https://abby.bos.lol/mcp"
scopes = ["mcp:catalog"]
```

This is a new-connection example, not a reason to replace a working configuration
or revoke its grant. Abby advertises its exact resource through
`/.well-known/oauth-protected-resource` and requires exactly
`https://abby.bos.lol/mcp`. Omit the optional `oauth_resource` setting and
`--oauth-resource` flag when using this discovery path. In the confirmed Codex
CLI **0.162.1** incident, explicitly setting that same resource as well caused
Codex to send it twice. Removing the redundant client setting fixed that
attempt. Duplicate construction is native-client behavior; Abby continues to
reject repeated, missing or different resource values. Do not edit generated
authorization URLs or weaken resource validation to compensate.

OpenAI documents native MCP login with `codex mcp login abby`, and `/mcp` in
the Codex terminal UI shows active servers. See the [official MCP guide](https://developers.openai.com/codex/mcp)
and [configuration reference](https://developers.openai.com/codex/config-reference)
for supported client options. The incident-specific guidance here does not
claim that every Codex version has the same duplicate-resource behavior.

### Browser on your computer, Codex on abby-01

For a new sign-in or an intentional reconnect, start SSH forwarding and native
Codex login **together**, then use the URL printed by that running command.
For example, from a terminal on the computer running your browser, with a free
loopback port on both computers:

```bash
ssh -t -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8766:127.0.0.1:8766 abby-01 \
  "codex -c 'mcp_oauth_callback_port=8766' mcp login abby --scopes mcp:catalog"
```

The port is illustrative. Codex's server-specific `oauth.callback_port`, if
configured, takes precedence over the global callback port; the listener and
forwarded port must match. Confirm that the fresh URL's loopback redirect uses
the forwarded port before continuing. Keep this terminal and SSH connection
open. Copy the fresh **authorization URL** from that terminal into your normal
browser, sign in to Abby if asked, review catalog access and authorize once.
Use only the callback generated by this attempt. The callback's loopback address
is on the browser computer, so the tunnel must already lead to that same running
remote Codex listener.

Wait for native Codex to report successful authorization in the terminal. Then
open the Codex terminal UI, inspect `/mcp`, and confirm authenticated tool
discovery for Abby succeeds with catalog-only access. The confirmed production
connection discovered **11 catalog tools** on October 18, 2026; counts can change
as the catalog evolves. A configured server entry, registered client or browser
success message alone does not establish completion. Preserve an already
working grant rather than rerunning login as a diagnostic check.

### If sign-in does not complete

| Symptom | Meaning and next step |
| --- | --- |
| The authorization URL shows the ordinary Abby app instead of the Django OAuth form or consent page. | Abby's service worker previously treated `/oauth` navigation as an app route. Open Abby in the same browser profile, finish or save open work, accept the normal **Reload** update banner, then start a fresh login and open its new URL. The updated worker leaves OAuth authorization/login URLs, including their query strings, to Django. Private browsing and manual cache clearing are not the update procedure. |
| Several clients appear under OAuth management, but your active token list is empty. | Dynamic client registration happens before consent and token exchange. Registrations can remain after abandoned or failed attempts. The token list shows only unexpired access tokens for the Abby user currently signed in; an empty list does not prove sign-in completed or describe another user's access. An expired or revoked token also disappears from that list. |
| The browser says “Authentication complete,” while Codex reports “Authorization state not found.” | In the confirmed incident, an expired callback reached a replacement native Codex listener. That browser message belongs to the native client, and cannot prove state validation or token exchange succeeded. End the failed attempt you own, start forwarding and login together again, and use only its fresh authorization URL. Do not reopen the old callback or reuse a URL from terminal history. |
| An authorization URL or callback expired, or its original listener stopped. | OAuth state and the PKCE verifier belong to the original native login attempt; authorization codes are short-lived and single-use. Start a fresh attempt. Reopening the old tab or starting a replacement listener does not restore the original state. |
| Abby rejects repeated `resource` values. | For the confirmed Codex 0.162.1 case, omit the redundant client `oauth_resource` setting and use native discovery. Keep Abby's exact-resource check and request a fresh authorization URL. |

In **Manage → Admin → OAuth clients**, **Registered clients** are client
registrations across the server, not a list of successful user connections.
**Your active access tokens** lists your currently unexpired access tokens and
their scopes. Registration alone grants no access. Revoking all tokens for a
client affects other users of that registration too; do not revoke registrations
or tokens just to tidy unsuccessful attempts or diagnose a working connection.

Abby owns routing OAuth pages to Django, clear management labels, staff-parent
eligibility, exact-resource validation, scopes and server-side PKCE enforcement.
Native Codex owns authorization URL construction, its callback listener and
state validation, credential storage and the callback success page. An Abby
deployment cannot recover expired native state or change that success message.
Keep credentials, codes, tokens, full authorization URLs and complete callback
URLs out of logs, screenshots, issue/PR evidence and troubleshooting messages.
Record only versions, sanitized error text and whether terminal authorization
and authenticated discovery completed.

## Reading shelves and logs

Use `list_reading_books` and `get_reading_summary` with `mcp:read` to inspect
saved shelves, totals and today's Reading Adventure evidence. Parents must
choose a same-family child with `user_id`; children access themselves only.
Shelf lists return `has_more` and `next_after`; pass the latter as `after`
with the same target and status to continue in ascending ID order. Reads create
no progress and award nothing.

With `mcp:write`, `create_reading_book` saves a title, author, status and optional
interests. `log_reading_session` references that child's `book` ID and records
minutes, pages, a section or a reflection; at least one is required. Print,
ebook and audiobook formats use the same existing reward rules. Omit
`occurred_on` for the family-local day; future dates are rejected.

Both writes require a stable UUID `client_request_id`. Identical retries reuse
the current saved record; changed details conflict. Reading uses the same
validation and services as REST. Saving a book grants nothing. Session
`reading_reward` and summary `reading_adventure` report actual persisted awards
and daily progress; they are not projected rewards. A retry cannot repeat an
award, and correction/deletion cannot create another daily opportunity.
Reflections remain reading records and never enter reward context. See
[reading guidance](../../apps/reading/CLAUDE.md) for the daily threshold,
correction and retention rules.

## Challenge coverage

Use `list_challenges` for saved modern goals, frozen reward promises, actual
award receipts, daily-bonus evidence and retained legacy history. It does not
enroll missing goals, advance recurrence or award rewards. Its saved-state
view can therefore differ from the app's materializing Challenges page.

Use `preview_challenge_goal` with a same-family child, activity trigger, metric
(`count`, `minutes`, `distance`), target, matching unit, period and reward/skill
tags. It shares the app's `GoalWriteSerializer` and writes nothing. Weekly
goals follow the family's calendar week. XP requires explicit valid skills.

For reading goals, use `trigger_type="reading_logged"`, `metric="count"` and
`unit="actions"`. One action means an actual awarded daily Reading Adventure,
backed by its saved reward receipt. Individual sessions, books, pages and
reflection text do not independently advance that goal. This is a count of
daily Adventures, not a reading-minutes metric.

After review, call `create_challenge_goal` with the reviewed fields, a stable
UUID `request_id` and transport confirmation. Repeating the identical request
reuses its existing goal; conflicting details are rejected. Existing qualifying
work can immediately satisfy the goal and pay its reward. `pin_challenge` and
`unpin_challenge` change presentation only, using saved `goal:<id>` or
`legacy:<id>` identities.

The older `get_daily_challenge`, `claim_daily_challenge` and quest assignment
tools remain compatibility surfaces. They do not create current measurable
parent goals. Use the modern tools for new challenge authoring and auditing.

## Reviewed content-pack publishing

1. Inspect global content and rules with `read_rpg_catalog`,
   `audit_rpg_catalog` and `get_economy_rules`.
2. Create/edit the family's pack with `write_pack_file` or
   `draft_pack_entries`. The structured merge helper accepts item, species,
   potion, badge, quest and shop-reward entries; raw YAML also supports drop
   rules and skill trees. A draft is not a catalog publication.
   Name-only draft rows can gain a stable `id` through an append without
   changing neighboring rows. Keep existing IDs when editing; adding an ID
   to an already-published name-keyed row still requires explicit ownership
   migration before publication.
3. Call `preview_content_pack` (also exposed as `validate_content_pack`). It
   runs strict domain validation and the real loader in a rollback, then saves
   an expiring publication plan. Review exact before/after changes and retained
   content, not just row counts.
4. Compare anonymous reward scenarios and inspect catalog findings. Resolve
   unavailable artwork and unreachable prerequisites before promising new
   acquisitions. An asset proposal does not make an item available.
5. Call `publish_content_pack` with that plan's `preview_id` and
   `content_digest`, using the same actor/family and explicit confirmation.
   Changed source bytes, changed catalog state, an expired plan or a different
   actor requires another preview. The publication and its receipt commit
   together. Retrying a completed publication returns its existing receipt.

`load_content_pack` follows the same reviewed-publication contract; it cannot
bypass a preview. Its `dry_run` option creates a preview. Stable pack-owned
entry identities protect renames; a matching display name is not permission
to overwrite another pack or bundled content. Shop publication targets the
author's explicit family. Draft files are also family-owned. Unowned legacy
draft directories require operator reconciliation rather than automatic
adoption by the first caller.

Reconciliation removes owned obsolete drop rules and retires removed shop
offers. Quest reward links are reconciled to the new definition. Owned
inventory, accepted quest/goal snapshots and pending shop promises remain
intact. Other missing definitions are retained and reported instead of being
cascade-deleted. The legacy standalone prune tool is not a replacement for
reviewed atomic publication.

Existing legacy quests still read their definition's non-item rules. A pack
cannot change their reward amounts, progress rules, duration, prerequisite or
XP destinations while an accepted legacy run is active; create a new version
for future content. Cosmetic edits and item-link edits remain possible because
accepted item promises have durable snapshots. Preview reports aggregate
protected-run counts without exposing participant identities.

## Reward auditing and balance comparisons

`get_economy_rules` exposes current server settings, rates, XP thresholds,
boost behavior, daily caps and calculation references. `preview_economy_scenario`
compares bounded anonymous plans without selecting an account, issuing rewards,
rolling randomness or simulating through writes/rollback. Each projection
states supported sources, assumptions, conditional bonuses and omissions.
Explicit proposed project/challenge payouts are assumptions, not discovered
server-approved reward amounts. Drop expectations use current eligible pools;
expected item value is not spendable Coins. Affordability is conditional on
the supplied scenario, not a promise of when a child will earn a reward.

For actual outcomes, use `list_coin_ledger` and `get_economy_audit` with
`mcp:read`. Dates follow the target family's timezone. Ledger pagination uses a
signed cursor bound to the account and filters; repeat those filters when
continuing. New higher-ID entries do not enter that page sequence. Audit
periods default to 30 days and are bounded to 366 inclusive days.

Accounting comes from persisted Coin amounts, separating earn reasons,
spending, refunds, exchanges and mixed adjustments. Activity-event Coin deltas
are not an accounting substitute: a base activity amount can differ from a
boosted saved credit. Typed reward receipts explain actual awards where those
amounts exist. Receipt subtotals overlap the ledger and must not be added to
it. Historical completion guards do not reconstruct missing award amounts;
these tools do not claim a complete historical XP ledger or proof that the
economy is balanced.

Catalog inspection is paginated with real totals and continuation. Iterate
all pages for a complete audit. Availability/reachability findings use runtime
selectors without querying a child's private ownership or progress.

## Reusable projects

Project templates retain weighted project skill tags and fixed milestone XP
tags when saved, read and instantiated through REST or MCP. `update_template`
supports structural replacement: supply all four nested arrays (`milestones`,
`materials`, `steps`, `resources`) together; use empty arrays to clear them.
Omitted fields retain their saved values. Index and skill references are
validated before an atomic update.

Use stable `request_id` UUIDs for duplicate-safe template create/save/instantiate
requests. A different payload with an existing UUID is rejected. Set
`create_project_from_template.status` to `draft` to review a plan before
starting it; the compatibility default remains `in_progress`.

## Complete project and payment history

`list_projects` and `list_payment_ledger` accept an optional `cursor` and return
`total`, `has_more` and nullable `next_cursor` alongside their existing results.
Project `count` remains the current page's length; it is not the history total.
Keep the original target and filters when continuing, and pass `next_cursor`
as the next request's `cursor`. Page size may change within its existing limit.
Payments remain money owed and settled in Abby's ledger, not a live external
Greenlight balance.

Cursors are signed, bound to the tool, actor, role, family and filters, and expire
after 24 hours. Payment date filters also bind the active timezone. Tied creation
timestamps use primary-key ordering, so page boundaries do not skip or repeat
tied rows. The initial maximum ID excludes later inserts, even if backdated.
Every page checks current authorization again. `total` counts currently
matching authorized records within that ID boundary; deletion, reassignment or
changed status can alter it. The cursor does not freeze a database snapshot.
Invalid, expired or differently scoped cursors are rejected; restart without a
cursor when deliberately changing filters.

## Proposing external assets

An assistant can turn catalog findings into `propose_asset` briefs. Each brief
contains a stable key, asset kind, creative direction, rationale, existing
alternatives, explicit intended uses, output formats and budgets, acceptance
criteria and license requirements. Each use names its surface/content reference,
placement, player purpose and implementation work. New art does not implicitly
introduce a new reward, equip rule, creature binding or renderer capability.

The handoff workflow is:

1. `propose_asset` with a stable request UUID. Identical retries return the same
   proposal. Proposals are private to their authoring family.
2. Inspect with `list_asset_proposals` / `get_asset_proposal`; history summaries
   paginate through `after_event_id` and `event_limit`, without repeating full
   briefs. Edit with
   `update_asset_proposal` and the expected revision.
3. Review the exact brief with `review_asset_proposal`, selecting `ready` or
   `cancelled`. Edits to a ready brief reset it to proposed and require review.
4. `export_asset_proposal` returns the versioned `abby.asset-proposal` JSON
   contract for a ready brief, including its revision and SHA-256 brief digest.
   This export does not call or enqueue an external pipeline.
5. After external production, `record_asset_delivery` records an opaque
   artifact ID, SHA-256 and notes against the expected proposal revision. It
   records a delivery claim without fetching or verifying the file.

All responses retain `publication_authority: proposal_only`. A ready brief
or recorded delivery establishes neither license clearance nor visual/runtime
acceptance. It does not register sprites, change the supported-art registry,
grant inventory or publish files. The existing prepared-art review/release
process handles those separate decisions. No pipeline credentials, webhook
endpoint or generation provider are configured by this feature.

## Rollout and verification

Run migrations before serving the new tools: MCP proposal history, RPG pack
provenance/publication receipts and project-template learning/request records
are persistent database state. The mutation retry contracts additionally need
`apps.mcp_server` migration `0004_mcpmutationreceipt`. Reconnect external clients for the revised
permissions. Tool names, real input schemas and annotations are discoverable
through MCP; [the tool inventory](../mcp-tools.md) records the required grants.
The [Google/AI disclosure inventory](google-ai-disclosure.md) remains the source
for provider/data-transfer disclosures and operator evidence requirements.

### Read-only connection check

Supply an existing OAuth access token in `MCP_TOKEN`, then run:

```bash
python scripts/smoke_mcp.py --base-url http://127.0.0.1:8000
```

`--base-url` accepts the server origin, without `/mcp`; `MCP_BASE_URL` supplies
the same option and defaults to `http://127.0.0.1:8000`. Remote origins require
HTTPS. The script appends `/mcp`, initializes the connection, verifies filtered
discovery and runs the catalog reads available to that grant. A catalog grant
allows the two bounded catalog checks; another grant may verify initialization
and discovery with zero catalog calls. Successful output contains only tool and
call counts; errors use fixed messages. Tokens and response bodies are not
printed. The script does not log in or mutate household/catalog records.

The old `--full` mutation smoke mode is retired and refuses before making a
network request. Write validation runs against disposable data through the
Django MCP tests; deleting created rows cannot undo ledger/reward opportunities
or notification history from a production smoke run.


## Existing catalog editing and progression evaluation

`get_content_workbench` supplies bounded global references without family shop
usage or private drafts. `get_rpg_rules` and `explain_rpg_catalog_entry` expose
installed calculations, effective effects, audits and bounded incoming global
references. Household shops, goals, inventory and saved progress are omitted.
XP curves, new effect handlers, incubation rules and asset support remain
reviewed source/configuration changes.

Use `create_content_draft` → `save_content_draft` → `preview_content_draft` →
`simulate_content_draft` → `publish_content_draft`. List/get tools resume only the
acting author's drafts. Save requires the current revision and confirmation.
Publication requires its exact revision, preview ID, digest, matching paired
simulation and explicit confirmation. Private drafts use `mcp:author`, publication
uses `mcp:publish`, and references use `mcp:catalog`; grants remain independent.
Private reads and replays recheck the current author under family/member locks.

`get_progression_lab` describes the installed simulator. The catalog-only
`simulate_progression_scenario` runs an anonymous baseline, including supported
365-day horizons. It shares native work limits and the ten-per-minute quota;
paired draft simulations share the five-per-minute quota. Reports preserve
coverage/exclusions and never create real rewards or household state.

Direct taxonomy/badge writes validate complete merged candidates and preserve
original source identities across matching bundled reloads. Another family's
owned pack/override is read-only. Numeric badge thresholds require JSON numbers;
numeric strings, booleans and nonfinite values are rejected. Taxonomy must retain
matching categories/subjects and an acyclic prerequisite graph. Taxonomy deletes
remove only unused, unmanaged entries: progress, earned badges, tags, prerequisites,
saved challenge promises and retained source dependencies block deletion. Managed
bundled/pack definitions require reviewed source reconciliation. REST returns 409
with a readable `detail` and `code: taxonomy_in_use`; MCP returns that structured
code. Errors expose no private dependency names or counts. Unused caller-owned
direct entries can be deleted with their own override metadata atomically.
Private quest category filters recheck their explicit IDs within the creation
transaction; a missing category rolls back both the new definition and its MCP
receipt. Identical request replay still returns the saved original response.

Skill identities include their category. Duplicate labels show their category in
the native pickers; MCP writes continue to use numeric IDs. Quest YAML references
accept a unique bare name or `Category::Skill`; bare prerequisites within a skill
tree refer to that skill's category. Ambiguous qualified spellings are rejected,
including collisions caused by literal `::` in category or skill names. Subject
assignment also resolves the exact category/subject pair. Automatic
daily bonus fallback XP targets `Life Skills::Persistence`, and sample movement
tags target Physical skills. An absent canonical skill never selects another
category's namesake.

Pack relationship edits distinguish omission from explicit clearing:
`required_badge` omitted retains its value; null clears it. Skill `prereqs`
omitted retains edges; an explicit list replaces the owned skill's edges,
including an empty list. Direct prerequisite overrides take precedence over YAML.
Structured badge/quest/shop merges use stable IDs when supplied. Pack items use
the same bounded runtime metadata validation as the database workbench.

## Household RPG management

Parents explicitly select a same-family child with `user_id`; children remain
self-scoped. All new writes require literal top-level `confirmation: true`.

- `retry_challenge` takes `challenge_id="goal:<occurrence_id>"` for an eligible
  expired unpaid attempt. Native predecessor replay and lifetime reward guards
  remain authoritative; no synthetic progress is created.
- `update_challenge_schedule` takes `goal_definition_id`, `expected_revision`,
  UUID `request_id`, and `paused` and/or partial `next_week` fields. Only parents
  edit schedules; accepted/current periods keep their frozen promises.
- `list_expeditions`, `get_expedition`, `start_expedition` and `claim_expedition`
  retain native allowance/timers and frozen loot. Start requires UUID `request_id`;
  claim uses the exact expedition ID. Neither can shorten waits or reroll loot.
- `list_reward_redemptions`, `get_reward_redemption` and
  `deliver_reward_redemption` expose saved promises and explicit parent physical
  handover. Delivery never spends Coins or repeats a digital grant.

Start/schedule UUIDs replay the original saved response; use reads for current
state. Changed details conflict. Native retry/claim/delivery use exact saved IDs.
Reads and writes recheck current authority while materializing results. Expedition
and redemption cursors share caller-bound signed history pagination and its
24-hour validity/initial-insert boundary.

Legacy `create_quest_definition` commits definition/assignment atomically. Its
optional `request_id` enables exact safe replay; preserve it after uncertain
responses. Without a UUID, the legacy non-idempotent contract remains. Chores
expose `xp_reward` and one-time `due_date`, sharing REST merged validation;
recurrence changes clear the old one-time deadline. Shop restocking shares the
REST wishlist/notification workflow.

## Reading maintenance

`get_reading_book`, `get_reading_session` and `list_reading_sessions` supplement
shelf/summary reads; session history uses signed continuation cursors.
`update_reading_book` corrects metadata and status, including finished books.
`update_reading_session`, `delete_reading_session` and `delete_reading_book` share
REST owner locks and validation. Books with history keep their deletion guard.
Confirmed corrections/deletions never rearm daily rewards, rewrite UUID credit,
or award more XP/Coins. Parents can maintain inactive-child history in their family.

## Textual editorial content

`list_editorial_drafts` returns compact identity, revision and preview/publication
summaries. Use `get_editorial_draft` for the full saved edits and exact preview.

`list_editorial_content` reads global Lorebook/affirmation copy without learner
state or private writing. Create/save/preview/publish editorial draft tools use
private actor/family revisions. Save requires confirmation; publish additionally
requires `mcp:publish` and the exact revision/preview/digest. Previews expire after
30 minutes or a source/catalog change. List/get resume the author's own drafts.

Lorebook edits cover existing titles, audience titles, summaries, kid voice and
mechanics prose. Trial handlers, unlock conditions and reward flags stay in source.
Affirmations support bounded single-line text, tone, new slugs and retirement.
Retirement excludes future selection but preserves historical slug resolution;
at least one active affirmation remains. Published copy overlays cached YAML on
each read, without a worker cache-flush operation. Apply migration
`rpg.0038_editorial_content_publication` before serving these workflows.
