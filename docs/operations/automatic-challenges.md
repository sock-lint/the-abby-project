# Automatic challenges

Challenges describe a goal within a period. Matching saved activity advances
every eligible goal in the background. Pinning changes which goal is featured
on Today; it neither enrolls the child nor determines whether their work counts.
Badges remain permanent recognition of milestones, skills and sustained effort.
A single activity can count toward a daily bonus, a challenge and a badge.
Named and collection-quest badges require completion of the real catalog
challenge. A parent goal's title or measurement does not grant those badges or
unlock a catalog storyline.

## Canonical offers and family challenges

System templates with the same name and identical activity rules, periods and
rewards are reconciled to one canonical definition. Superseded definitions stay
in the database for saved promises and history; new offers use the canonical
definition. Conflicting same-name system rules are withheld from new enrollment
and reported by the catalog audit until reconciled. Parent-authored templates
retain their separate household identity.

Reconciliation never removes paid receipts, contributions or accepted windows.
If only a superseded personal goal exists, its identity and saved promises move
to the canonical definition. If both exist, their already accepted windows remain
payable, while the superseded goal cannot create another repeat window. Legacy
completion and active-window guards consider equivalent definition identities.
There is no retroactive reward clawback or activity replay.

### Review unresolved duplicate pairs

The native reconciliation service and three dedicated MCP tools provide an
explicit maintenance path for one conflicting pair at a time. Select the
retained source and the creatorless canonical definition by their exact IDs;
names and primary-key order never choose the winner. Both must be unresolved
same-name system roots. The service refuses incompatible rules, periods,
rewards, tags and milestone gates, along with source ownership or dependency
states that it cannot safely preserve.

Use `preview_challenge_reconciliation` with a stable `client_request_id`, then
inspect `get_challenge_reconciliation`. These require an active staff parent
and `mcp:author`. The preview records the chosen pair, provenance categories,
rule differences and preservation policy without changing the catalog. It
contains no household identities, usage records or counts. Reuse the UUID and
exact pair after an uncertain response; changed details conflict.

After reviewing the exact preview, `publish_challenge_reconciliation` requires
`mcp:publish`, its preview ID and content digest, and top-level
`confirmation: true`. A one-time personal/cooperative difference also requires
`acknowledge_cooperative_transition: true`. That acknowledgment applies to the
reviewed pair: existing personal windows keep their promises, while future
offers use the selected canonical assignment rules.

Two exact reviewed v1-to-v2 profiles additionally permit
`acknowledge_policy_transition: true` when the preview reports
`requires_policy_acknowledgement`:

- Daily Rituals keeps three habit actions in a one-day repeating window and
  20 XP, changing 10 Coins plus one Small Coin Pouch to 2 Coins without a pouch.
- Comeback Kid keeps its seven-day cadence, target of three, 60 XP and exact
  Streak Freeze reward, changing three habit taps and 40 Coins to three distinct
  habit days and 10 Coins, with the reviewed description explaining the days.

The source filters, canonical v2 filters, Coin amounts and item identities are
checked against those profiles. Other fields must match, including skill IDs
and weights; target, cadence, eligibility or arbitrary reward edits are refused.
The policy acknowledgement must be repeated when recovering a completed publish.
Existing accepted initial/saved windows keep their old terms. Only later
canonical windows use the reviewed v2 offer on the saved anchor and cadence;
overlapping aliases open no future cycles. Other behavioral differences,
including a repeating personal-to-cooperative conversion, need a separate
content decision and are not merged here.

Expired or changed catalog/ownership/history bindings require a new preview
UUID. Current account and family authority is checked on reads and replays.
Successful publication has one durable receipt and cannot repeat the mapping
or any reward. Installing this workflow does not automatically reconcile data.

Publication retains both definitions and their creator/source provenance.
Where no canonical goal already exists, it moves only a catalog goal's
definition link, preserving that goal's ID, cadence, timestamps and promises.
Additional accepted alias windows remain payable but cannot open another
repeat cycle. An enrolled source goal whose initial window has not opened yet
has that window saved at its original anchor first, including repeating goals
with unrelated pre-anchor history. Publication never creates an unsaved later
cycle, replays facts or pays rewards. One-time retry chains keep their saved
authoritative window. A shared account/catalog admission order and a fresh definition
check prevent stale first enrollment from recreating an alias goal during
publication. See `apps/quests/reconciliation.py` and its PostgreSQL tests.

An explicitly cooperative catalog definition requires a parent to choose at
least two children from the same family under Family challenges. The resulting
saved campaign has one shared progress total and uses the existing co-op payout
rules: every assigned participant receives the full accepted completion reward.
Cooperative templates do not create new individual automatic goals or enter a
single-child Progression Lab forecast. Existing individual promises keep their
accepted windows. Any accepted individual version of a nonrepeatable challenge
prevents a second shared assignment, including an expired unpaid version: a late
approval can still fulfill that original promise. For repeatable definitions,
new shared assignments wait for accepted individual windows to end.

MCP parent goal preview and creation accept Daily Reading Adventures through the
same count rule as REST. A saved daily reading reward is the source identity;
extra sessions and retries do not add another daily contribution.

## Activity, periods and rewards

Use the original activity date to assign challenge progress to a period. Parent approval
confirms a submitted chore or homework contribution; approving last week's work
does not move it into this week's goal. Late approval may finish its original
period. Work outside the goal's window does not count.

Homework uses the submission's saved calendar day and timezone, so changing the
household timezone or assignment deadline before approval cannot move that work
to another day. Weekly goal backfill uses the same saved day, even when the
source timestamp falls outside the goal's absolute timestamp window after a
timezone change. Older submissions without a valid timing snapshot use the
configured Django timezone as a stable fallback; their original household zone
cannot be reconstructed. Existing challenge facts and paid history are never
rewritten. Weekly chores continue using their recorded period-start date, while
approval timestamps remain separate for catalog eligibility and daily bonuses.

Parent-created `this_week` goals use Monday through Sunday in the family's
timezone, with the next Monday as the exclusive end boundary. A repeating weekly
goal creates a separate occurrence for the next week. Completing a goal early
does not start another paid occurrence in the same week. The period, target,
reward and activity rule are frozen on each occurrence. Changes to a future goal
must not rewrite earlier earned progress or promised rewards. Explicit midweek
weekly creation includes already saved matching work from that week and may
complete immediately; the parent form explains this before saving.

Taxonomy retirement does not cancel a saved recurring rule or an accepted
future weekly setup. Later windows retain the rule's reward skill IDs even if
the skill or an ancestor is retired. A historical deleted skill stays in the
saved snapshot without a fabricated XP award; completion still pays its saved
Coins and records actual XP for surviving skills. New goals and newly selected
future reward skills still require available taxonomy. Explicit retries have
their own current-offer eligibility checks.

Catalog goals use the stored trigger filters, not their names, artwork or reward
skill tags. A coding theme does not restrict contributions to coding unless the
filter explicitly does so. A new catalog goal receives its full window when it
is first offered or evaluated automatically. Enrollment/cutover, template
creation, the actual badge unlock and any active legacy deadline remain lower
boundaries. An eligible pending saved action can anchor that first window so its
initial save or retry still counts; already processed history does not start or
replay a new catalog goal. Nonrepeatable goals keep that one window. Repeatable
goals use successive windows from their saved anchor and stored duration.
Project and milestone completion saves take the child's shared award lock before
writing the source or assigning its first accepted completion timestamp. Initial
catalog reads use that same lock, so they cannot enroll after an in-flight first
completion and exclude its credit. REST and MCP leave timestamp assignment to
the canonical completion signal; stale saves retain an existing accepted time.
Unrelated partial saves, such as a plan's `updated_at`, do not take the award lock
after their caller has already locked the project row. PostgreSQL overlap
regressions are in `apps/projects/tests/test_challenge_credit_concurrency.py`.
Existing windows never restart when the child returns, completes or pins them. An already active
legacy challenge retains its original dates, target, progress and reward promise.
New offers, manual solo/co-op starts, rerolls and private quest creation require
an activity that the saved-work pipeline can produce. Reward-only badge-earned,
Perfect-Day and quest-completion rules cannot start a new campaign. Boss rules
also need at least one matching activity that deals damage. Mixed rules remain
eligible when they include a supported progress source; missing, null and empty
trigger lists keep their existing unfiltered meaning. Retained definitions report
`catalog_available: false` when they cannot progress; saved campaigns, history,
rewards and identical creation-request retries stay preserved.

Category restrictions match the category saved alongside the accepted activity's
skill tags. Later tag edits or moving a skill into another category do not
reinterpret that activity. Older facts without category evidence are retained
without inventing a category or replaying their progress.

Default goals count effort events,
so bonus awards do not recursively complete more goals. Expedition returns count
only when the goal explicitly includes that trigger.

Retiring a catalog definition detaches its personal goals without deleting saved
occurrences, contributions or receipts. An unpaid saved window retains its
original progress and reward promise and can still finish; paid history remains
paid. Retirement prevents future repeat windows. The private catalog-origin flag
and frozen catalog name/type retain catalog eligibility and badge history after
the definition is removed; a parent-created goal does not become catalog history.

Built-in catalog challenges retain the existing source eligibility limits:
only the first planned homework assignment and first two logged creations per
local day count. The source service freezes that eligibility when it saves the
record. Replaying a source, deleting an earlier record, or retrying progress does
not turn an ineligible record into eligible catalog credit. Additional valid
records remain saved and can count toward an explicit parent-created goal.

These eligibility counters use the active Django timezone (default
America/Phoenix), preserving their existing day boundary. Goal periods and the
automatic daily bonus use the family's timezone. Movement goal progress continues
for every valid session after its separate first-three-session XP/drop limit.

Movement distance is a separate optional measurement from minutes. Store a
decimal distance with `distance_unit: mi|km`, normalize it to metres, and sum
actual distance for distance goals. An older session without distance does not
gain invented mileage. Running-specific goals match the selected movement type;
other movement does not count. Each valid session can advance measurable goals
even after the existing daily movement XP/drop limit has been reached.
Goal contributions and totals round to three fractional digits using
`ROUND_HALF_UP` before saving and checking completion.

Saved source identities make contribution retries idempotent. Pinning, reading
and reopening a page award nothing. Completion awards each
occurrence once and returns a receipt containing the actual Coins, skill XP and
recorded item outcomes;
the configured reward preview is not proof of payment. Daily Coins remain
Lucky Coin eligible; goal Coins retain the existing unboosted quest policy.
Before completion, a correction removes or replaces the source contribution. A paid occurrence never
rearms because its source was changed or deleted.

## Explicit retries and parent weekly controls

Expired unpaid one-time catalog goals offer an explicit retry. The owning child
or a parent in that child's current family posts `{}` to
`/api/challenges/goal:<occurrence_id>/retry/`. The predecessor ID is the
idempotency key: repeating it returns the same successor, even after that
successor ends. No read, pin or background task starts an attempt. A retry gets
the saved full-duration promise and fresh progress, and accepts only newly
recorded facts within its new window. A private activity-ID floor excludes even
earlier pending facts whose timestamp equals the new start.

Explicit attempts share one lifetime reward across the canonical catalog
identity, retained aliases and legacy completions. The first attempt to finish
earns it; delayed processing may finish the older attempt first. Remaining
unpaid attempts close with `reward_already_awarded`, preserving their saved
progress and rules without claiming another payout. Original grandfathered
promises that have never been explicitly retried keep their original policy.
Paid, repeatable, shared, parent-authored and retired goals cannot start retries.
The list retains eligible expired offers beyond its general history limit.

A new retry is blocked while any originally promised item is missing or
unavailable, including withdrawn art or an incompatible egg/potion pair. The
list reports `retry.allowed: false` with `reason: reward_unavailable`, and the
first retry request returns 409. The check uses the saved item IDs/quantities;
later template edits cannot replace or remove that promise. Item-free rewards
remain retryable. Existing accepted attempts, late original completion and
predecessor replay retain their frozen rewards and the one-lifetime payout
guard. Taxonomy retirement keeps its separate new-retry admission check.

Parents can pause/resume future weeks or edit next week's name, description,
target, Coins, XP and skill tags for their household's recurring parent goals.
`PATCH /api/challenges/goals/<goal_definition_id>/schedule/` takes
`expected_revision` and `paused` and/or partial `next_week` setup. Every accepted
change becomes effective next Monday in the goal's saved timezone. A stale
revision returns 409 and requires reading the saved version. Activity type,
metric and unit stay fixed. Resume and setup edits use the normal goal validator;
a pure pause remains possible even if an old saved reward skill was deleted.

Current and already accepted future occurrences keep their exact snapshots and
receipts. Paused weeks have no new occurrences; a later resume cannot reopen
them through delayed approval. Paused rules remain visible for parent controls.
Schedule changes do not process source work, backfill progress or award rewards.
Migration 0012 only adds schema/defaults; it creates no attempts or schedules
and changes no saved history or account rewards.

## Daily bonus

The daily bonus is one small automatic award per child per family-local day.
It qualifies on approved work or a completed project/milestone, or ten cumulative
minutes of logged project work or movement. Multiple short sessions accumulate.
Approvals qualify on the family-local day they are accepted. The challenge's
original work date still assigns its weekly goal progress; a weekly chore's
Monday bucket cannot backdate Thursday's daily bonus. Logged minutes accumulate
within the same family-local accepted/saved day.
It is created and evaluated while activity is saved, so opening Today and the
nightly task are not prerequisites.

The base reward is 10 Coins and 20 skill XP. XP uses explicit source skill tags
where available, with an explicit Persistence skill fallback for untagged
work. If neither is available, the receipt must report zero skill XP.
The receipt describes what was actually awarded, including an applicable boost.
Completing another qualifying activity that day does not grant a second bonus.

## Upgrade and recovery

Apply the additive migrations normally. Do not delete or rewrite `Quest`,
`QuestParticipant`, `DailyChallenge`, catalog definitions, inventory or ledgers.
Existing selected active challenges become the initial pin. Historical daily
reward values of zero retain their already-claimed meaning; nonzero values retain
the original reward promise. Schema migration and the first list/read must not
award completed historical work or create retroactive bonus payouts. The
scheduled bounded settlement may finish genuinely completed legacy bonuses with unpaid reward promises; it must
not award unfinished legacy rows or historical days without earned work.

`quests.0007_catalog_goal_retirement` backfills catalog origin from existing
definition links and adds frozen name/type metadata to their saved snapshots.
Parent goals retain their separate origin, and the catalog link becomes nullable
on deletion. This migration does not change saved targets, periods, contribution
amounts, payouts, inventory or account balances.

Do not backfill all historical activities through the full RPG game loop: that
would rerun streaks, drops and unrelated rewards. A progress repair uses durable
source/contribution identities and touches only missing challenge state. Keep
new progress unavailable until its migration and server implementation are
deployed together. If a reward failure occurs, retain the durable source fact
as pending for inspection and an idempotent retry; never fabricate a
successful receipt or discard saved activity to release a gate.

## Validation

The producer in `config/tests/test_challenge_api_contract_fixtures.py` sends real
parent goal, child list/pin and movement requests with synthetic accounts and a
fixed clock. Its shared JSON bodies are consumed through the React API client in
`frontend/src/api/challengeContractFixtures.test.js`. They cover an unpinned goal
completing alongside another goal, cumulative distance, a daily bonus, actual
reward receipts, boost amounts and family-scoped rejections.
Separate real endpoint examples cover delivered items, skipped unavailable
items and an owned egg converted to Coins, without awarding again on replay.

Reproduce against disposable test data:

```sh
SECRET_KEY=challenge-contract-test-only DATABASE_URL=sqlite:///:memory: \
  .venv/bin/python manage.py test --settings=config.settings_test \
  config.tests.test_challenge_api_contract_fixtures --verbosity=2
cd frontend
npm run test:run -- src/api/challengeContractFixtures.test.js
```

For an intentional contract change, set `UPDATE_API_CONTRACT_FIXTURES=1` only on
the local producer command, review the generated JSON, then rerun with that
variable absent. CI refuses fixture regeneration. Fixtures are raw server
responses, not hand-authored examples or permission-test replacements.

Run the affected goal/period/movement tests, migration-preservation check and
lorebook parity checks locally. The migration check covers both the pre-feature
upgrade and `0006` to `0007` with saved paid/unpaid catalog and parent goals,
including safe template deletion after the upgrade. Required hosted PR checks remain `Frontend
validation`, `Backend validation` and `API fixtures` as described in
[PR validation](pr-validation.md). PostgreSQL transaction tests are required for
concurrent contributions, completion/payout locking and recurrence; SQLite
contract checks do not verify those locks.
