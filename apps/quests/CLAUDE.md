# apps/quests/

Automatic challenges track every relevant goal independently of its pin. The legacy boss/collection engine, co-op rows, rage shields and daily-challenge promises remain available for saved work. Shared source ingestion is driven by the game-loop activity seam; feature flows must not create contribution or reward rows directly.

## Supported rewards and reachable prerequisites (October 2026)

The owner-authorized prelaunch retirement is a narrow exception to the promise
preservation rules here. Its exact obsolete item IDs are removed from accepted
quest/goal item promises and occurrence item receipts while keeping unrelated
items, progress, timestamps and authored Coin/XP amounts. It does not map an old
species into a different family or invent replacement quest rewards. All other
accepted promises retain the behavior below. See
[unused first-party content retirement](../../docs/operations/companion-lifecycle.md#unused-first-party-content-retirement).

Default bundled loading attempts this transition once, with a durable success
marker in the same transaction. A changed identity, protected reference or
resource-validation conflict rolls back retirement and warns while ordinary
loading continues without a success marker. The strict manual command remains
available; dry runs or a later bundled failure roll back marker, resources and
cleanup together. Separate settlement of held shop Coins, supported incubation
ingredients and saved unclaimed expedition resources runs before deletion, without
new challenge facts, XP, badges, boosts or reward rolls.

The parent challenge catalog sorts by type, name, then primary key. A system
definition and a parent-authored definition can share a name and type; the
identity tie-break keeps their existing image bindings and row order stable
across PostgreSQL query plans. `tests/test_catalog_ordering.py` covers reversed
physical insertion without changing the shared API fixtures.

New quest definition reads and accepted starts filter `reward_items` through
`apps/rpg/catalog_support.py`. New automatic occurrences freeze only eligible
items in their server-owned snapshot; new legacy solo/co-op starts freeze
`Quest.reward_items_snapshot`. Accepted snapshots remain visible and fulfill
their original item IDs and quantities once after catalog retirement,
including existing egg-salvage rules. Unavailable new offers receive no
replacement Coins. Ordinary XP/coin payouts and progress remain unchanged.

Pre-cutover legacy quests have a null item snapshot and retain their current
`QuestRewardItem` links. Reconciliation freezes active null snapshots once,
without rewards or timestamp/progress changes; its dry-run reports affected
quest IDs without writes. Content loading freezes these links before authored
quest updates. Earlier edits cannot be reconstructed because old quests had no
historical item snapshot. `reward_items.py` owns this boundary; the nullable
field is server-only and is distinct from an accepted empty list.

Read-only `catalog_available` reports whether the required badge is still a
reachable goal, or was already earned by the account. React omits unavailable
new unlocks while retaining active/history rows. The start service still
requires the actual earned badge; availability does not grant it or relax its
criteria. Broader reward mechanics remain testable with scoped synthetic asset
bindings. See `apps/rpg/tests/test_catalog_consumers.py`.

## Native reading milestone offers

`QuestDefinition.prerequisite_quest`, `required_skill` and `required_skill_level`
combine with the existing earned-badge requirement using AND. The target must
be a one-time global collection challenge with exactly the `reading_logged`
activity filter; only reading currently has the trusted new-source hook.
Prerequisites use exact global catalog identities, including completed legacy
participation or automatic catalog occurrences, never a parent goal's name.
The named skill must be unlocked and meet the required level. Direct cycles,
private references and unsupported activity rules are rejected by model and
publication validation.

`ReadingRewardService` calls `activity.freeze_milestone_eligibility` only while
earning a genuinely new daily receipt, after reading XP and before game-loop
evaluation, under the source/user transaction. This captures the eligible
`ChallengeGoal` and its occurrence before the fact can finish a predecessor.
An unrelated action, GET, old source first observed later, pending repair or
replayed daily receipt cannot open a milestone window. The internal
`ingest_activity(..., fresh_milestone=True)` acceptance seam is for trusted
callers and synthetic native tests; incoming context never grants it.

New goals freeze `catalog_gate_snapshot` and `catalog_gate_activity_id`; the
occurrence also stores `snapshot.catalog_gate`. Both the opening source's ID
lower bound and the saved half-open timestamp window apply to later credit.
Existing goals retain empty/null defaults, their original deadlines, snapshots,
contributions, receipts and pins. No accepted milestone automatic or legacy
window rearms after expiry or failure. Legacy quests have no historical
completion timestamp, so their saved state time is only a conservative source
cutoff, never a claimed completion date.

The self/family-scoped `/api/challenges/` response includes `locked_catalog`
with read-only catalog metadata and server-confirmed `milestone_eligibility`.
An unlocked row still waits for the next qualifying saved reading receipt;
it has no accepted window, countdown or pinnable goal identity. Rows whose
one-time prerequisite can no longer finish (its only accepted window ended
uncompleted, directly or through a gated predecessor chain) are omitted;
`milestone_eligibility.prerequisite_unavailable` owns that rule. Reading this
metadata awards nothing. New milestone-gated solo, co-op and scroll starts are
refused after explaining any unmet requirement: a manual legacy start cannot
begin the clock before the child's next qualifying Reading Adventure. Existing
legacy runs continue with their accepted windows and rewards.
Installing these schema/services does not activate a
policy or rewrite bundled or published content.

## Automatic goal tracking

- `ChallengeEnrollment` records the first tracking boundary and timezone; changing a pin does not reset it.
- `ChallengeGoal` stores a personal catalog or parent-authored goal. Its private `is_catalog` origin survives a deleted template; the optional `catalog_definition` uses `SET_NULL`. `ChallengeOccurrence` freezes one period, activity rule, target and reward promise, including catalog name/type metadata for saved catalog history.
- `ChallengeActivity` records a durable source identity and safe context; `ChallengeContribution` credits a source once per occurrence. Private journal prose never belongs in this context.
- `ChallengePin` points to one new occurrence or an existing legacy quest for Today presentation.
- `DailyBonus` records one automatically awarded receipt per child per family-local day. The old `DailyChallenge` rows and their claim state are preserved.
- `goals.py` owns automatic enrollment, matching, recurrence, contribution processing, payout, retry and pinning. Locks begin with the account row, matching `AwardService`; hold that lock while changing contribution/completion state.
- Source services acquire that account gate before saving the accepted timestamp used by first enrollment. Untimed internal facts sample their fallback clock under the same gate. Explicit source timestamps, cutover exclusions and saved window boundaries remain unchanged; a concurrent initial catalog read cannot cut off a newly accepted action.
- Every saved qualifying action advances eligible goals independently of the pin. Catalog goals retain the source limits of one planned homework assignment and two logged creations per local day. The service-owned counter freezes a private boolean `ChallengeActivity.context.catalog_eligible`; incoming client context cannot grant eligibility, and retries/deletions cannot promote an over-limit fact.
- Explicit parent-created goals can count all valid matching saved records. Movement goal progress includes every valid session after the separate three-session XP/drop cap. Reads and pins never award or consume inventory.
- Planning/creation quota counters keep their existing active-Django-timezone day (default America/Phoenix). Parent goal windows and daily bonuses remain family-local; this fix does not move the source reward gates to a new clock.
- New parent goals measure counts, minutes or decimal distance and can repeat weekly. Weekly boundaries are Monday through Sunday in the family timezone; late approval retains the activity's original period. Paid occurrences never rearm following a correction or deletion.
- Homework challenge work days use the submission's saved v1 timing snapshot, even after a household timezone or deadline edit. Legacy/malformed snapshots fall back to the configured Django timezone, since the original household zone is unknown; existing challenge facts retain their saved dates. Weekly backfill uses the goal's saved timezone and resolves the same frozen work day from a bounded source scan. Approval timestamps remain separate for catalog cutoffs and approval-day daily bonuses; weekly chores keep their saved period-start date.
- Contributions and totals use the existing three-decimal precision with explicit `ROUND_HALF_UP` before persistence/completion, keeping processing, weekly backfill and unpaid corrections consistent across databases.
- Catalog goals use their actual trigger filters; themes and XP reward tags do not restrict qualifying activities. Reward-only definitions (`badge_earned`/`perfect_day`) are omitted from new automatic enrollment, while saved legacy instances remain readable. Default unfiltered goals count effort events; expedition returns need an explicit trigger filter. Newly offered/evaluated goals get a fresh full-duration window, with enrollment/cutover, definition creation, actual badge unlock and active legacy deadline as lower cutoffs. The earliest eligible pending fact can anchor the initial window so saved work/retries count; processed history is never replayed into a new catalog goal. Nonrepeatable goals keep one window, repeatable goals keep successive frozen-duration windows from their saved anchor, and no existing dates reset on return, pinning or completion.
- Catalog retirement preserves saved paid/unpaid occurrences and contributions. A remaining saved window can finish with its frozen reward promise, but a detached catalog goal creates no future repeat windows. Eligibility and achievement queries use the durable catalog origin and frozen name/type after deletion, keeping parent-authored goals outside catalog badge history. Migration `0007` backfills this origin/metadata without changing progress, rewards or ledgers.
- Completion responses distinguish reward previews from actual `reward_receipt` amounts. Awarded automatic receipts include their persisted `items` outcomes; converted egg rows have `salvaged_to_coins`, already included in `coins_awarded`. Pending and legacy receipts omit actual item outcomes. Source replay and reward retries must not rerun streaks, random drops or already-paid awards.

Endpoints: `GET /api/challenges/` (parent may select a same-family child with `user_id`), `POST /api/challenges/goals/` (parent only), and `POST`/`DELETE /api/challenges/<goal_id>/pin/` (self-scoped presentation). New IDs are `goal:<occurrence_id>`; retained legacy IDs are `legacy:<quest_id>`.

Catalog detail discovery records presentation separately from progress.
`POST /api/challenges/<goal_id>/opened/` accepts an empty object for the active
child's own catalog occurrence and saves only its first details-opening time.
It accepts active or saved history windows that have started, never a parent
view, sibling, legacy ID or future window. Retries retain the first timestamp;
the action never materializes goals, processes activities, pins or awards.
Payloads expose nullable `first_details_opened_at` and `catalog_repeatable`.

`GET /api/challenges/discovery/` is a bounded read for active staff parents in
their current family. It aggregates one-time catalog windows created in the
last 30 family-local days among recent children with explicitly new tracked
enrollments. Old enrollments retain a null tracking marker and unknown history.
Server materialization is not an impression or eligibility timestamp; opened
and completed groups overlap and neither proves reading or enjoyment. The
endpoint excludes trusted observer families, identities and prose, and returns
unknown counts when its cohort or occurrence bound is exceeded. Only the
browser client's transport partition/retry query keys are allowed. See
`tests/test_discovery.py` and the actual challenge response fixtures.

`GET /api/challenges/voyager-feedback/` is a separate read-only staff-parent
report for the current family's active nonstaff children registered within
180 inclusive family-local days. It never calls `list_goals`, repairs saved
facts, opens a window or changes rewards. Trusted `LiveTestFamily` households
are excluded. Only transport partition/retry query keys are accepted; child
and family selectors are refused. The response contains aggregate counts,
without child identities, accepted row IDs, authored prose or reading details.

`voyager_feedback.py` resolves the unique global Reading Voyager identity;
missing/ambiguous definitions and exceeded child/history limits withhold counts
rather than fabricating zero outcomes. Current child states are distinct from
saved-window policy groups. Readiness uses current exact prerequisite, unlocked
skill and earned badge facts, with bulk identity queries independent of history
length. It is not a historical first-unlock timestamp. `acceptance_mode`
distinguishes current automatic tracking from native milestone offers waiting
for the next new Reading Adventure. Accepted or conflicting history takes
precedence over new-offer readiness; membership is rechecked before aggregation.

Saved 45-day windows require frozen count-20 reading rules, exactly 45 elapsed
days and no native milestone snapshot. Their old badge requirements were not
frozen, so do not describe this bucket as proof of historically ungated access.
The selected 56-day bucket additionally requires matching strict version-one
goal/occurrence gate snapshots, the exact unique global Reading Companion and
Language Arts::Reading Comprehension identities, skill level 1, no badge and
the saved opening activity ID. Other or malformed policies stay separate.
Current catalog edits never reclassify an accepted promise from today's rules.

Only fully ended saved windows enter mature outcomes. Early completions remain
pending until the full deadline; `mature_denominator` is known completed plus
known expired, excluding pending and unknown evidence. Ended active rows at the
target may be awaiting repair and remain unknown. Completion recorded after the
deadline can reflect valid saved work processed later. Legacy quests lack a
frozen full policy and completion time, so their mature outcome remains unknown.
Counts are observations within current membership, not causal experimental or
retention evidence. Tests live in `tests/test_voyager_feedback.py`; actual API
fixtures are produced alongside the other challenge contracts.

Goal payloads expose server-owned `origin: parent|catalog|legacy` for presentation. Automatic catalog origin uses the saved `is_catalog` marker even after a template is retired; retained `Quest` rows always report `legacy`. Names, pinning and client input do not determine origin or change tracking.

Goal payloads also expose nullable `completed_at` from the saved occurrence.
It records when completion was processed, which can follow approval, retries or
backfill after the goal period. React labels it “Completion recorded” alongside
the preserved household-local period; it must not classify the child's work as
late by comparing that timestamp to the period end. Legacy quests have no saved
completion timestamp and return null, never their general `updated_at` value.
An incomplete ended occurrence remains in history with its saved progress and
null completion timestamp. Existing weekly and rolling cycles continue to use
the goal's saved timezone after a household timezone change, including across
DST. React includes the year in saved periods and the exact exclusive deadline
in goal details; showing only the final included date must not imply that a
rolling period accepts work through the end of that entire day.

The daily bonus qualifies through approved work/completed projects or milestones, or ten cumulative project/movement minutes. Its day comes from the trusted accepted/saved `occurred_at` timestamp in the family timezone, while parent challenge periods continue to use `occurred_on` for the original work day. Minutes accumulate within the same half-open family-local timestamp range. Explicit completed legacy settlement retains its original promised date. The bonus pays automatically once per family-local day; Today access and a rotation task are not prerequisites. XP uses explicit source skill tags or the explicit Persistence fallback and reports only actual unlocked-skill credit.

See [automatic challenge operations](../../docs/operations/automatic-challenges.md) for cutover, repair and validation. Real server responses and the React consumer checks live in `config/tests/test_challenge_api_contract_fixtures.py`, `contracts/api/fixtures/challenge*.json`, and `frontend/src/api/challengeContractFixtures.test.js`.

MCP `challenges.py` exposes saved-state inspection, shared-serializer preview,
UUID-safe parent goal creation and same-family pins. Audit reads must not call
the materializing `list_goals()` path. Goal creation can backfill and immediately
pay a satisfied period; it requires explicit client confirmation. Legacy daily
challenge tools do not create current measurable parent goals.

## Preserved legacy behavior

New legacy starts and the parent catalog share `queries.definitions_visible_to`:
system definitions are global, while parent-authored definitions belong only to
their creator's current family. A private definition with a deleted creator is
unavailable for new starts. Saved campaigns/history keep their accepted promise.
Solo and co-op services enforce this boundary for REST, MCP and internal callers;
co-op participants must also share one family. Parent-authored reward amounts
remain a decision within that household.
Known foreign or mixed-family campaigns accepted before this gate cannot record
new progress or pay. Existing creatorless campaigns retain their saved promise;
deleting an author does not cancel a valid participant's accepted reward.

Reading Adventure's `reading_logged` event advances explicitly filtered
automatic goals using the awarded `ReadingDailyReward` primary key as its
durable source. The resolver checks the owner and saved award; arbitrary
session IDs, minute quantities and prose grant no credit. Its saved award day
survives session corrections/deletion, and current-week parent count goals can
backfill that earned receipt without replaying source rewards. Reading stays
outside unfiltered default effort and the daily bonus. New bundled reading
goals add a deterministic supported Chick acquisition and Birdseed care path
with zero authored Coins.

The same event can advance saved legacy quests
when their trigger filters match (5 base boss damage or one collection step).
It fires at most once per family-local day after ten reading minutes. Reading
does not qualify the daily bonus; its own reading reward receipt is separate.

The following model/service notes describe the existing `Quest` and `DailyChallenge` promises. Do not apply their one-active-slot or claim requirements to automatic goals and the daily bonus.

Legacy nonrepeatable definitions cannot start again after a participant has
completed that definition, through child starts, parent assignments or co-op
assignments. Failed and expired attempts remain retryable; repeatable
definitions retain their existing restart behavior. These checks share the
user locks used by campaign creation and completion.

Co-op completion pays the full quest XP, coins and available item promise to
every assigned participant, including a member with no contribution. Each
recipient keeps their own XP boosts, badge eligibility and egg-salvage rules.
The campaign's completed status and all participant awards, inventory and
notifications commit together; a failed payout rolls back the finishing hit
and remains retryable. Responses retain the finishing child's reward shape.
Progress locks all participant users in ascending primary-key order before
the quest and contribution rows. When the game loop is invoked inside a source
transaction that already owns an acting-child award lock, only legacy co-op
progress waits for that source's commit, then runs in its own atomic block.
That callback remains bound to the originally observed campaign and cannot
credit a replacement assigned after another participant finishes it.
Source rollback discards this callback; callback failure is logged without
rolling back committed source work. Solo progress and top-level habit calls
remain synchronous. PostgreSQL regressions live in
`tests/test_reward_concurrency.py`; replay, recipient and rollback checks are
in `tests/test_reward_integrity.py`.

## Models
- `QuestDefinition` (boss/collection, `trigger_filter` JSON, `required_badge` gating, `xp_reward`/`coin_reward`/`QuestRewardItem`).
- `Quest` (active quest row per user — `status`, `current_progress`, `rage_shield`, `end_date`; server-owned nullable `reward_items_snapshot` retains accepted item IDs/quantities).
- `QuestParticipant` (multi-player-ready, wired today for parent-authored co-op quests).
- `QuestRewardItem` (per-quest reward bundle).
- `QuestSkillTag` (XP fan-out — same shape as `ProjectSkillTag`).
- `DailyChallenge` (separate slot — unique on `(user, date)`; 5 challenge types).

## Services
- `QuestService` — `start`, `record_progress`, `_complete_quest`, `expire`, `apply_boss_rage`, `start_co_op_quest`.
- `DailyChallengeService` — `get_or_create_today`, `record_progress`, `claim_reward`.

Celery names are retained: `expire_quests_task` (00:10 local) and `apply_boss_rage_task` (00:15 local) maintain saved legacy quests. `rotate_daily_challenges_task` (00:30 local) now performs bounded pending-fact repair and settlement of genuinely completed unpaid legacy bonuses; it does not assign new random daily challenges.

## Endpoints
- `POST /api/quests/{definition_id}/co-op/ {user_ids}` (parent-only, family-scoped) — wraps `QuestService.start_co_op_quest`.
- `GET /api/challenges/daily/` and `POST /api/challenges/daily/claim/` retain the legacy serializer/claim contract. The current React daily card reads `daily_bonus` from `GET /api/challenges/`.

## Gotchas

- **Quests**: Two types — `boss` (damage-based HP pool) and `collection` (item-count target). `Quest` has a time-boxed `end_date` and tracks `current_progress` and `rage_shield` (extra damage required after an idle day). One active quest per user at a time (`Quest.status=="active"`). **Damage formula** per trigger in `TRIGGER_DAMAGE`: clock_out 10/hr, chore 15, homework_complete 25, homework_created 5, milestone 50, badge 30, project_complete 75, habit_log 5. Collection quests count 1 per qualifying trigger. **Trigger filtering** via `QuestDefinition.trigger_filter` JSONField: `allowed_triggers` (whitelist of `TriggerType` values), `project_id`, `skill_category_id`, `chore_ids`, `savings_goal_id`, `on_time` (boolean — when true, only counts homework contexts with `on_time=True`) — empty filter = all triggers count. Validated via `apps/quests/validators.py::validate_trigger_filter` — wired into `QuestDefinition.clean()`, `QuestWriteSerializer`, and MCP `create_quest_definition`; unknown keys or trigger values raise `ValidationError` before any write. The 2026-04-23 review removed `streak_target` and `perfect_day_target` from the allowlist — they were validated but never read, producing silently-broken quests. Re-add only when a reader lands in `QuestService.record_progress`. **Badge gating:** `QuestDefinition.required_badge` blocks start until earned. **Rage shield:** `apply_boss_rage_task` (Celery, 00:15 local) ticks every active boss quest: idle day climbs by `RAGE_SHIELD_CLIMB_STEP` (15) capped at `RAGE_SHIELD_CAP` (100); active day decays by `RAGE_SHIELD_DECAY_STEP` (25) toward 0. The decay-on-return path preserves the gentle-nudge doctrine — absence costs progress, but return clears the penalty. Returns `{"raged": int, "decayed": int}`. **Expiration:** `expire_quests_task` (Celery, 00:10 local) marks past-due active quests as expired. On completion: `_complete_quest` awards `coin_reward` (via `CoinService`), `xp_reward` (via `AwardService.grant`), and any `QuestRewardItem` entries (to `UserInventory`), then notifies. **Egg salvage** (2026-04-23, N1): when a `QuestRewardItem` is an `EGG` whose `pet_species` already appears in the user's `UserMount` table, the egg auto-salvages to `coin_value × quantity` instead of stacking dead eggs in inventory — same logic as cosmetic-dupe salvage in `DropService`. The `rewards["items"]` entry carries a `salvaged_to_coins` field so frontends can render the salvage path differently. Pinned by `QuestEggSalvageTest` in [`tests/test_services.py`](tests/test_services.py). `QuestParticipant` preserves per-user contributions to existing co-op quests. The legacy **`POST /api/quests/{definition_id}/co-op/`** endpoint (parent-only, family-scoped) wraps `QuestService.start_co_op_quest`; it must reject a duplicate campaign for a catalog goal already tracked automatically. The new parent goal form assigns one child, while saved co-op data and the older components remain retained. `QuestWriteSerializer` accepts a `coop_user_ids` array (≥2) and a `skill_tags` array of `{skill_id, xp_weight}`; `CreateQuestView` consumes both atomically so untagged custom quests no longer silently award 0 skill XP. The retained legacy form's **Advanced details** panel exposes `allowed_triggers` and `on_time_only` (`trigger_filter.on_time`); it is not mounted by the current Challenges page. **Reward rubric for new authors:** see the comment block at the top of [`content/rpg/initial/quests.yaml`](/content/rpg/initial/quests.yaml) for the Easy/Standard/Epic tier conventions; the 2026-04-23 review rebalanced Dragon Slayer (Standard tier), Focus Master, and Midnight Oil to align with the rubric.

- **Historical daily challenges**: `DailyChallenge` retains its unique `(user, date)` row, five challenge types, target/progress and original reward promise. The old clock-hour rule floors each session separately, and the legacy `claim_reward` marker zeros both reward fields after paying once. New daily bonuses use accumulated minutes instead. A paid new bonus bridges subsequent legacy get/claim calls to an already-paid row, preventing a second payout. The bounded settlement task pays genuinely completed old bonuses once, preserving their original amount and zeroing the legacy marker; schema migrations and reads never settle them. Legacy services and serializer shapes remain compatibility surfaces, while the new UI reads automatic bonus receipts from the challenge list.

## Tunables (constants in `apps/quests/services.py`)
- `TRIGGER_DAMAGE` — per-`TriggerType` boss damage table; clock_out multiplied by hours. QUEST_COMPLETE and PERFECT_DAY are intentionally absent (they're rewards, not damage sources).
- `RAGE_SHIELD_CLIMB_STEP = 15`, `RAGE_SHIELD_DECAY_STEP = 25`, `RAGE_SHIELD_CAP = 100` — asymmetric boss-quest rage tuning. Idle days climb +15 (saturates in ~7 idle days); active days decay -25. Decay outpaces climb on purpose so a child returning from a multi-day absence claws back faster than they fell behind — preserves the gentle-nudge doctrine. `RAGE_SHIELD_STEP` is kept as a back-compat alias pointing at the climb step.

## Key entry points
- `services.py` — `QuestService`, `DailyChallengeService`, `TRIGGER_DAMAGE`, rage-shield constants, `DAILY_CHALLENGE_TEMPLATES`.
- `validators.py::validate_trigger_filter` — single shared validator wired into `QuestDefinition.clean()`, `QuestWriteSerializer`, MCP `create_quest_definition`.
- `tasks.py` — `expire_quests_task`, `apply_boss_rage_task`, `rotate_daily_challenges_task`.
- `tests/test_services.py`, `tests/test_daily_challenge.py` (legacy); `tests/test_goals.py`, `tests/test_daily_bonus.py`, `tests/test_goal_concurrency.py` and `config/tests/test_challenge_api_contract_fixtures.py` (automatic goals and actual receipts).
