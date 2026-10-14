# apps/quests/

Automatic challenges track every relevant goal independently of its pin. The legacy boss/collection engine, co-op rows, rage shields and daily-challenge promises remain available for saved work. Shared source ingestion is driven by the game-loop activity seam; feature flows must not create contribution or reward rows directly.

## Supported rewards and reachable prerequisites (October 2026)

Quest definition reads filter `reward_items` through
`apps/rpg/catalog_support.py`, and completion applies the same filter before
new inventory grants or egg salvage. Unavailable eggs, potion variants and
pet accessories are skipped without replacement Coins; the definition's
ordinary XP/coin payout and completion progress are unchanged. Definitions,
active quests and saved ownership are retained.

Read-only `catalog_available` reports whether the required badge is still a
reachable goal, or was already earned by the account. React omits unavailable
new unlocks while retaining active/history rows. The start service still
requires the actual earned badge; availability does not grant it or relax its
criteria. Broader reward mechanics remain testable with scoped synthetic asset
bindings. See `apps/rpg/tests/test_catalog_consumers.py`.

## Automatic goal tracking

- `ChallengeEnrollment` records the first tracking boundary and timezone; changing a pin does not reset it.
- `ChallengeGoal` stores a personal catalog or parent-authored goal. Its private `is_catalog` origin survives a deleted template; the optional `catalog_definition` uses `SET_NULL`. `ChallengeOccurrence` freezes one period, activity rule, target and reward promise, including catalog name/type metadata for saved catalog history.
- `ChallengeActivity` records a durable source identity and safe context; `ChallengeContribution` credits a source once per occurrence. Private journal prose never belongs in this context.
- `ChallengePin` points to one new occurrence or an existing legacy quest for Today presentation.
- `DailyBonus` records one automatically awarded receipt per child per family-local day. The old `DailyChallenge` rows and their claim state are preserved.
- `goals.py` owns automatic enrollment, matching, recurrence, contribution processing, payout, retry and pinning. Locks begin with the account row, matching `AwardService`; hold that lock while changing contribution/completion state.
- Every saved qualifying action advances eligible goals independently of the pin. Catalog goals retain the source limits of one planned homework assignment and two logged creations per local day. The service-owned counter freezes a private boolean `ChallengeActivity.context.catalog_eligible`; incoming client context cannot grant eligibility, and retries/deletions cannot promote an over-limit fact.
- Explicit parent-created goals can count all valid matching saved records. Movement goal progress includes every valid session after the separate three-session XP/drop cap. Reads and pins never award or consume inventory.
- Planning/creation quota counters keep their existing active-Django-timezone day (default America/Phoenix). Parent goal windows and daily bonuses remain family-local; this fix does not move the source reward gates to a new clock.
- New parent goals measure counts, minutes or decimal distance and can repeat weekly. Weekly boundaries are Monday through Sunday in the family timezone; late approval retains the activity's original period. Paid occurrences never rearm following a correction or deletion.
- Catalog goals use their actual trigger filters; themes and XP reward tags do not restrict qualifying activities. Reward-only definitions (`badge_earned`/`perfect_day`) are omitted from new automatic enrollment, while saved legacy instances remain readable. Default unfiltered goals count effort events; expedition returns need an explicit trigger filter. Newly offered/evaluated goals get a fresh full-duration window, with enrollment/cutover, definition creation, actual badge unlock and active legacy deadline as lower cutoffs. The earliest eligible pending fact can anchor the initial window so saved work/retries count; processed history is never replayed into a new catalog goal. Nonrepeatable goals keep one window, repeatable goals keep successive frozen-duration windows from their saved anchor, and no existing dates reset on return, pinning or completion.
- Catalog retirement preserves saved paid/unpaid occurrences and contributions. A remaining saved window can finish with its frozen reward promise, but a detached catalog goal creates no future repeat windows. Eligibility and achievement queries use the durable catalog origin and frozen name/type after deletion, keeping parent-authored goals outside catalog badge history. Migration `0007` backfills this origin/metadata without changing progress, rewards or ledgers.
- Completion responses distinguish reward previews from actual `reward_receipt` amounts. Awarded automatic receipts include their persisted `items` outcomes; converted egg rows have `salvaged_to_coins`, already included in `coins_awarded`. Pending and legacy receipts omit actual item outcomes. Source replay and reward retries must not rerun streaks, random drops or already-paid awards.

Endpoints: `GET /api/challenges/` (parent may select a same-family child with `user_id`), `POST /api/challenges/goals/` (parent only), and `POST`/`DELETE /api/challenges/<goal_id>/pin/` (self-scoped presentation). New IDs are `goal:<occurrence_id>`; retained legacy IDs are `legacy:<quest_id>`.

The daily bonus qualifies through approved work/completed projects or milestones, or ten cumulative project/movement minutes. Its day comes from the trusted accepted/saved `occurred_at` timestamp in the family timezone, while parent challenge periods continue to use `occurred_on` for the original work day. Minutes accumulate within the same half-open family-local timestamp range. Explicit completed legacy settlement retains its original promised date. The bonus pays automatically once per family-local day; Today access and a rotation task are not prerequisites. XP uses explicit source skill tags or the explicit Persistence fallback and reports only actual unlocked-skill credit.

See [automatic challenge operations](../../docs/operations/automatic-challenges.md) for cutover, repair and validation. Real server responses and the React consumer checks live in `config/tests/test_challenge_api_contract_fixtures.py`, `contracts/api/fixtures/challenge*.json`, and `frontend/src/api/challengeContractFixtures.test.js`.

## Preserved legacy behavior

The following model/service notes describe the existing `Quest` and `DailyChallenge` promises. Do not apply their one-active-slot or claim requirements to automatic goals and the daily bonus.

## Models
- `QuestDefinition` (boss/collection, `trigger_filter` JSON, `required_badge` gating, `xp_reward`/`coin_reward`/`QuestRewardItem`).
- `Quest` (active quest row per user — `status`, `current_progress`, `rage_shield`, `end_date`).
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
