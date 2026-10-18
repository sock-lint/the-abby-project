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

## Challenge coverage

Use `list_challenges` for saved modern goals, frozen reward promises, actual
award receipts, daily-bonus evidence and retained legacy history. It does not
enroll missing goals, advance recurrence or award rewards. Its saved-state
view can therefore differ from the app's materializing Challenges page.

Use `preview_challenge_goal` with a same-family child, activity trigger, metric
(`count`, `minutes`, `distance`), target, matching unit, period and reward/skill
tags. It shares the app's `GoalWriteSerializer` and writes nothing. Weekly
goals follow the family's calendar week. XP requires explicit valid skills.

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
are persistent database state. Reconnect external clients for the revised
permissions. Tool names, real input schemas and annotations are discoverable
through MCP; [the tool inventory](../mcp-tools.md) records the required grants.
The [Google/AI disclosure inventory](google-ai-disclosure.md) remains the source
for provider/data-transfer disclosures and operator evidence requirements.
