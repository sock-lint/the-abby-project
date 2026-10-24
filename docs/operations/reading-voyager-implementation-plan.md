# Reading Voyager implementation plan

**Status:** Review plan only, October 19, 2026. No task below has been
implemented or executed by this proposal. Implement only after the owner
chooses to proceed. The [policy proposal](reading-voyager-proposal.md) and
[review-only values](reading-voyager-proposal.json) define the scope.

The deliverable is one faithfully enforced Reading Voyager policy: Reading
Companion completed AND Reading Comprehension level 1, followed by a fresh
56-day window for 20 daily Reading Adventures. Preserve existing accepted
promises and rewards. No tenure, seasonal gate or other challenge change is
part of this implementation.

## 1. Add inactive authoring support

Inspect current `QuestDefinition`, `apps/quests/goals.py`, legacy
`QuestService`, catalog queries/serializers, `apps/rpg/content/`, MCP catalog
exports and the Lab. Verify current main and PR #291 before selecting the
implementation base; the Lab study commit is not a deployment identity.

Add explicit, validated global-definition references for a prerequisite
challenge and a named skill/minimum level. The representation and migration
must be reviewed before coding the policy. Existing definitions default to
no additional gate. Resolve natural authoring references to exact server IDs;
reject missing, ambiguous, self-referential, cyclic, private-family or unsupported
requirements. A deleted prerequisite must not silently turn its dependent
challenge into an ungated offer. Use a protective reference or an explicit
unavailable state rather than permissive nulling.

Extend loader validation, Workbench edit/preview/publication/override handling,
catalog exports, audit and shared fixtures together. Include new fields in
catalog/rules fingerprints and evaluated publication state. A preview must
show the actual two requirements, duration and reward invariants. Revision or
catalog changes invalidate that preview. YAML reload must retain published
overrides and normal ownership/active-legacy guards.

Do not put the proposed keys into active YAML before consumers enforce them.
The first implementation can add support with all existing offers unchanged.
A later exact reviewed publication activates the policy. Keep schema support
and policy activation independently reviewable and avoid a duration-only
intermediate release.

## 2. Enforce the same policy at every accepted-start path

Centralize eligibility for automatic catalog enrollment, legacy solo starts,
co-op assignments and any scroll/reroll path that starts a challenge. REST,
MCP and internal callers must use the same check. Each co-op recipient must
satisfy their own milestones. Another child's, parent's or family's progress
cannot qualify the recipient.

Reading Companion completion means the recipient's durable catalog completion,
including a legitimate retained completed legacy run. A same-name parent goal,
a pin, an opened detail sheet or an earned unrelated badge is not completion.
Reading Comprehension must be the exact unlocked skill with actual level at
least 1. Preserve native earned-badge requirements as additional conditions.

Store an explicit first-eligibility/offer boundary under the existing account
lock. `SkillProgress` has no achieved-level timestamp: do not infer one from
current XP, account age or `updated_at`. For preexisting qualifying state,
observe eligibility prospectively; never fabricate a historical unlock date.

Evaluate requirements before processing each new fact, then freeze the
decision for that fact. Completing Reading Companion must not also credit
Voyager from the same fact. Reading XP legitimately awarded before its
`reading_logged` fact may satisfy the skill requirement for that fact when
the predecessor was already complete. Opening-day credit must follow this
order rather than depend on the order of definition rows or a prior GET.

Once eligible, open the window on a new qualifying fact and save the accepted
rule/reward snapshot. Browsing a locked definition may expose eligibility
information but must not consume the completion window. Exclude processed
history and pending facts from before the eligibility boundary. Specify and
test accepted timestamp versus processing timestamp for late delivery, retries
and cutover, so a delayed old receipt cannot acquire retroactive credit.

Keep current account-first locking, source identity, once-per-family-day
reading receipts and reward idempotency. Reads and pins may not award anything.
Use the existing household calendar/deadline convention and retain an
exclusive end; test sub-day timestamps and DST, not just integer day numbers.

## 3. Preserve accepted work and explain locked offers

Inventory every saved goal for the target definition through an authorized,
bounded preflight count. Include unpinned and unopened goals. No household
inspection was performed for this proposal and no zero-user assumption is
valid release evidence.

Existing goals/occurrences retain their original identity, dates, prose,
contributions, targets, items, XP and Coin promises. Completed and expired
goals cannot reopen or rearm. Existing accepted 45-day windows stay 45 days;
this proposal does not include a migration extending them. Block exact
publication while active legacy runs make scalar edits unsafe. Retain the
same Voyager definition; a version split requires a separate reviewed routing
and retirement design.

Expose server-confirmed lock reasons and remaining milestones in catalog
discovery and the relevant child/parent details. Before unlock, explain
"Complete Reading Companion and reach Reading Comprehension level 1" without
showing an expiring countdown. After opening, show progress, the saved
household-local deadline and the unchanged reward. Existing accepted history
shows its frozen explanation. The client must never infer eligibility from a
name, character level or optimistic local progress.

Update synthetic response fixtures and their React consumers with the actual
API shape. Retain staff-parent-only authoring, child self-scope, same-family
parent inspection and private journal boundaries.

## 4. Prove the implementation and rerun the exact narrower policy

Add meaningful red-before-fix tests for these acceptance groups:

| Group | Required proof |
| --- | --- |
| AND gates | Neither milestone alone qualifies; both qualify; wrong/locked skill and sibling/foreign progress do not qualify |
| Fact order | Predecessor-finishing fact cannot credit successor; valid reading-XP threshold fact can; definition order and GET timing cannot change credit |
| Clock | Full 56-day accepted window, exact exclusive deadline, inactive days, family timezone, DST and delayed processing |
| Idempotency | Concurrent enrollments/starts, duplicate source delivery, retries after payout failure and repeated reads never double-credit or pay |
| Preservation | Saved 45-day goals, unopened goals, expired/paid history, inventory and active legacy guards remain intact |
| Authoring | Cycles, invalid/private references, dependency deletion, stale preview, exact publication, YAML reload and override ownership |
| Clients | Server-owned lock reasons, no premature countdown, accepted-history copy and API producer/consumer parity |

Run focused backend tests on synthetic data, including PostgreSQL locking
checks for affected transaction paths. Run relevant React interaction tests,
lint and builds when the UI changes. Complete the normal hosted gates in
[PR validation](pr-validation.md) and independent cross-model review; unavailable
or failed gates remain unresolved. No production credentials enter tests.

Rerun anonymous simulations using **only the selected Voyager gate**. The
earlier five-target recipe is a comparison reference, not exact proof of this
narrower policy. Use fresh global catalog/rules bindings and pair current
45-day ungated rules with the complete 56-day gated candidate. Hold routines,
seeds, horizon and all Coin/expedition settings fixed. Separately compare
45/49/56/63 within the Voyager-only gate to isolate forgiveness from pacing.
Do not introduce the separate 100-Coin experiment into these pairs.

Retain the earlier 20-seed light/reading/regular controls and five-seed
interruption sensitivities. Cover one omitted reading, week 4 reading-only
omissions, week 4 full-app absence and weeks 4/6 absence. Include two visits per
week as a limitation check. Live code cannot assume a child's future routine
and withhold a difficult offer just because the Lab's capacity filter did.

The prior full-recipe light expectations are offer day 10, completion day 57
with no break, day 64 with week 4 away, and failure with two omitted weeks at
56 days. Verify those expectations against the isolated policy instead of
copying the old result as a pass. Keep target 20, authored Coins 0, XP 50,
skill weight 1 and one existing Bookworm title fixed. Explain any changed
indirect rewards or event ordering; do not force Coin equality as a substitute
for running the real implementation.

Report reached counts and full denominators, conditional dates, expired versus
unoffered cases, eligibility/opening phase, opening-day credit, saved rewards,
first companion timing, available-challenge visits and fixed-identity content
coverage. Check existing read-only/no-award simulator guarantees. Label private
calendar controls and different-catalog evidence honestly; do not bypass the
Notebook's same-catalog validator or rewrite fingerprints.

## 5. Review and activate the complete policy separately

Refresh exact IDs, expected old values, ownership, active-legacy checks and
current implementation bindings. Prepare the revisioned publication containing
both gates, 56 days and the exact proposed description. Present the complete
before/after diff and fresh evidence for owner review.

When actual source content is changed, update
`content/rpg/bundled/reading-adventures/quests.yaml` and the Reading Adventure
entry in `content/lorebook/entries.yaml` together. Verify the chosen mechanism
honors existing database-authored overrides. This plan does not choose a
silent YAML deployment as an alternative to exact publication.

After implementation review, hosted checks and explicit release approval, the
authorized operator follows the normal publication/deployment workflow. This
proposal is not that approval. Capture the exact revision, definition ID,
before/after fingerprint, publication receipt, deployed commit and trusted live
verification. Withhold activation if gate support, reference resolution,
legacy guards or evidence is incomplete.

Rollback affects future offers through another exact reviewed policy change.
Keep all accepted 56-day windows and earned items/rewards intact, along with
their historical gate/offer receipts. Do not delete goals, rewind progress or
restore an old catalog by overwriting accepted promises.

## 6. Close the feedback loop after cohorts can mature

Use bounded, authorized aggregates that distinguish eligibility observation,
offer opening, first details opening, qualifying reading dates, completion,
expiry and payout. A materialized server row is not a screen impression.
Store only the minimum identity/timestamp/rule binding needed by these server
events; publish no child identities or reading/journal prose in design reports.

Review early failures and opening-day credit promptly. Evaluate final
completion/expiry only after each offer has had its own full 56-day window
and processing allowance. A 30-day discovery report cannot establish final
success for this challenge. Keep immature, unknown and historical cohorts
separate, with full denominators and small-cohort limitations. No eligible
users means insufficient observed evidence, not a successful experiment.

Compare reading-opportunity bands where observed data supports them, including
two/week, three/week and interruptions. Track the 20-reading workload, the
existing 50-XP/Bookworm receipt, duplicate/salvage outcomes, and collection
coverage separately from authored content supply. Record a dated review
decision and the next concrete action. If low-frequency children regularly
expire, evaluate an 84-day or different-workload follow-up; do not silently
expand this selected policy or infer retention from completion alone.
