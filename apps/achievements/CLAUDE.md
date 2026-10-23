# apps/achievements/

Skill tree (Category → Subject → Skill → Badge), the unified `AwardService.grant` dispatch, and 58 badge criterion types grouped by subsystem. The skill XP routing in this app is shared across every major activity in the codebase.

## Reachable collectible goals (October 2026)

`availability.py::badge_goal_is_available` computes whether a collectible goal
can still be reached with approved future catalog content and the user's saved
progress. Pet hatch/species/mount thresholds use approved compatible pairs
plus legacy owned pets/mounts; saved pets can still evolve. Potion-shelf goals
include already owned typed potions, and named sets include already owned
items. A full four-slot cosmetic goal needs an existing active accessory,
because new accessories and accessory equip are unavailable. Other criteria,
including independent badge and consumable collections, stay available.

Unreachable unearned goals are omitted by `visible_badges` from child catalog
and summary surfaces. Earned badges remain visible, counted and eligible for
trophy selection, with read-only `catalog_available` reporting current goal
availability. Quest prerequisite availability uses the same check and honors
an already earned required badge. The original criterion checkers, thresholds,
XP/coin payouts and earned rows are unchanged; asset policy must not silently
lower a badge requirement. Generic engine tests can use explicit scoped
synthetic catalog bindings. Regression coverage is in
`apps/rpg/tests/test_catalog_consumers.py`.

Badge catalog, earned-list and summary reads share lazy availability inputs
within one request, including supported companion pairs and that account's
saved collections. `available_pet_pairs` batches authored compatibility reads;
an empty compatibility relation keeps its existing unrestricted meaning.
Standalone service checks and later requests recompute availability after
ownership or catalog changes. Query-growth and account-isolation regressions
live in `tests/test_badge_availability_queries.py`.

## Models
- `SkillCategory → Subject → Skill → Badge` — full hierarchy.
- `SkillPrerequisite` — allows cross-category and cross-subject requirements.
- `SkillProgress` — per-user skill state.
- `ProjectSkillTag`, `MilestoneSkillTag` — XP fan-out tables (chores/habits/quests/homework use sibling tables in their apps).
- 58 criterion types in `Badge.CriteriaType` — see "XP/Badges" gotcha for the criterion overview.

## Services

`source_identity.py` resolves installed journal, grade, Reading and daily-bonus XP
destinations by their exact current or retained original category/skill identity.
Retained matches require exact version-1 MCP authoring provenance in
`RPGContentOverride`. Distinct competing identities fail closed; source-less
canonical rows remain supported. Retirement preserves these installed routes,
and normal unlock eligibility still controls credit. Labels never redirect saved
receipts or cause past awards to be replayed.

Taxonomy deletion is shared by REST and MCP through
`apps.rpg.content.taxonomy_deletion.delete_taxonomy`. Only unused leaves may be
removed. Incoming relationships, saved homework-template skill tags, challenge reward/gate snapshots, retained
source dependencies and managed bundled/pack identities block deletion. REST
returns HTTP 409 with `detail` and `code: taxonomy_in_use`; MCP reports the same
code without private dependency names or counts. Another family's authored entry
is read-only. An unused caller-owned direct entry can be removed with its direct
override metadata in the same transaction; managed source retirement requires
reviewed source reconciliation. Full target-row locks prevent incoming FK races.
REST badge create/update joins the catalog write fence and rechecks current staff
authority before saving; PATCH merges with the row current after that fence.

Reversible taxonomy retirement lives in `taxonomy.py`. `is_retired` records a
row's own state; `available_for_new_choices` also checks its ancestors. Only
choice querysets filter retirement. History, default ORM managers, progress,
prerequisites and award resolution retain all identities. New explicit references
use `validate_new_taxonomy_references` within the saving transaction, retaining
unchanged saved IDs. PostgreSQL `FOR SHARE` on ordered ancestors and the target
conflicts with retirement/reparent updates; `KEY SHARE` alone does not. Every
new-reference transaction first shares all current categories in primary-key
order, covering multiple admissions in that transaction. Catalog writers use
the matching category `NO KEY UPDATE` prefix after their existing table
admission, before any upsert or target-row mutation. Private quest inserts/table
admission precede the reference locks; never invert those boundaries.
REST and MCP retire/restore share fresh authority, ownership and catalog fences.
YAML omission preserves the saved state; explicit false restores it.

- `SkillService` — `distribute_tagged_xp(user, tags, pool)` — splits by `xp_weight`.
- `BadgeService` — badge evaluation across all criterion types.
- `AwardService.grant(user, *, xp, coins, coin_reason, money, money_entry_type, xp_tags, xp_source_label, badge_scopes, …)` — **unified distribution helper**. Paired XP + coin + optional money ledger entry. Single entry point for all award flows. Applies `xp_boost_multiplier(user)` from `apps/rpg/services` before distributing XP (boosted total flows through tag-weighted splits; original base preserved in activity extras). Inner `CoinService`/`PaymentService` calls are wrapped in `activity_scope(suppress_inner_ledger=True)` to avoid double-logging. `badge_scopes` limits badge evaluation to the relevant criterion families for performance (see Badge Scopes below).

The `perfect_timecard` criterion recognizes approved and closed weeks. Closing
an approved zero-dollar week preserves its eligibility for later badge evaluation.

`chronicle_milestones_logged` counts the account's saved `FIRST_EVER` and
`MILESTONE` entries, matching Turning Point and Life Chronicler. Other Chronicle
kinds do not contribute. New firsts and graduation milestones evaluate the
`chronicle` and `badges` scopes in their marker transaction; duplicate writers
do not replay awards. See `apps/chronicle/tests/test_milestone_badges.py`.

Every newly created `UserBadge` also receives one `badge_earned` drop through
`DropService.award_accomplishment`, including badges with no XP or Coin bonus.
The earned marker, payout, loot and salvage share the existing account-locked
transaction. Re-evaluation does not backfill old badges, and a failed drop rolls
the award back for retry. This hook never invokes the activity game loop or
advances another challenge. See `apps/rpg/tests/test_accomplishment_drops.py`.

Badge evaluation follows saved eligibility changes: every positive habit tap
checks habit milestones even when its configured XP is zero, and Perfect Day
checks its counter badges within the daily receipt transaction. Inventory
grants and consumable use check the `rpg_inventory` and `badges` scopes after
their saved changes. This includes drop, challenge, expedition, digital shop,
mystery/lucky-dip, food-basket and new starter-cover grants.
Exact catalog-retirement compensation restores accepted resources with badge
evaluation disabled; it is not a new accomplishment or acquisition event.
Item-granting consumables defer their nested inventory checks until the whole
use has saved its effect, usage history and stack decrement. A collection must
qualify from that final ownership; a failed use discards the deferred requests.

`BadgeService.evaluate_badges` queues nested scope requests per account while
an ordered pass is active. A badge drop can finish another collection; queued
inventory checks run after that pass using current ownership and unique earned
markers, without recursive calls or replaying the activity loop. All resulting
badge XP, Coins and one loot draw per badge share the source transaction. A
failure rolls back the cascade and leaves it retryable. Existing earned badges
are never repaid; badge/inventory reads and catalog loading do not evaluate badges.

## XP transactions and lock order

Every skill-progress or badge-evaluation mutation entry point opens an atomic
transaction and locks the award user's row before reading or locking
`SkillProgress` or creating a `UserBadge`. This covers direct XP, both tagged distribution paths, unlock
evaluation, badge evaluation, and badge XP bonuses. An outer transaction keeps
the locks until its own commit. Receipt services must acquire the user lock
before their before/after progress snapshots; taking progress locks first and
then calling achievements reverses the order and can deadlock.

The user gate uses `select_for_update(no_key=True)` on PostgreSQL. It serializes
awards even when a progress row does not exist, while remaining compatible with
foreign-key `KEY SHARE` locks from activity inserts before an award. Progress
rows are then selected for update. XP saves only `xp_points` and the level
derived from that total; unlock evaluation saves only `unlocked`. Tagged awards
roll back together. Badge eligibility, the earned marker, XP, coins, and the
badge activity record share a transaction so a failed payout remains retryable.
Badge XP keeps the existing active-skill eligibility (`unlocked`, `level > 0`),
floor division and minimum-one award, then evaluates prerequisite unlocks.

Pet hatching and confirmed evolution call `BadgeService.evaluate_badges` with
`{"pet", "badges"}` inside their ownership transaction, after the new pet or
mount exists. Hatching takes the user gate before its ingredient locks; growth
callers already hold that gate before profile, pet and inventory locks. The
shared pet growth transition covers food, direct consumables and passive
growth. Existing earned markers and payout transactions make repeats harmless;
a failed payout rolls back the ownership change and consumed ingredients too.
The pet service sends `badge_earned` notifications only for the newly returned
awards, using the shared self-scoped notifier and a best-effort savepoint with
push deferred until commit. Notification failures preserve the committed award;
retries do not repeat earned markers, payouts or successful notifications.
See `apps/pets/tests/test_badge_milestones.py`.

`tests/test_xp_transactions.py` checks rollback, retry, division, levels, and
unlocks. `tests/test_xp_concurrency.py` requires PostgreSQL and uses independent
connections plus controlled overlapping saves to catch lost awards, duplicate
first progress creation, duplicate badge payouts, FK lock upgrades, and receipt
lock-order inversions. SQLite skips the concurrency tests because its
`select_for_update` does not provide row serialization. Run them with
`python manage.py test --settings=config.settings_test apps.achievements` and an
explicit `DATABASE_URL` for a disposable test instance. Keep background task
execution isolated from the database test transactions.

Character level is a persisted cache of the total actual saved `SkillProgress.xp_points` across all skills, using the same seven-tier `XP_THRESHOLDS` curve (0..6). Direct skill awards and badge XP refresh it after progress and unlock writes under the shared user gate; a failed profile update rolls back the award. Read-only character XP fields project that saved credit, with `xp_needed_for_level` as the width of the current threshold band and zero progress/width at level 6. Existing manually set cache values are normalized by migration 0028 and subsequent real skill XP awards, while presentation-only profile writes preserve them.

Skill Tonic now routes through `SkillService.award_xp`, including prerequisite unlocks, character-level synchronization, and badge evaluation. Consumables, pet mutations, streak activity, and cosmetic equip/unequip/starter-cover writes use the same user-first gate before profile, inventory or progress rows so they can compose with awards. Django admin and raw ORM progress edits remain outside this service contract and require their own coordination; later standard XP awards resynchronize the cache from their actual saved totals. Quest participant ordering still requires its existing outer-service coordination; this user gate alone does not claim global deadlock freedom.

Validation on 2026-10-09 used a disposable localhost PostgreSQL 16.1 cluster
and an external Django 5.1.15 environment, without loading `.env` or existing
databases. All 244 selected tests passed (achievements plus habit, journal,
journal receipt, homework, boost, and consumable service coverage). The same
SQLite run passed with the four PostgreSQL concurrency tests skipped. The
newly added grade integration suite also passed all 38 tests on SQLite;
`GradeService` uses the same user-before-progress order and `no_key=True` gate.
The temporary runner disconnected only the project's two Celery connection-recycling
hooks, which otherwise close PostgreSQL `TestCase` connections during eager
tasks. Running the new regressions against the original services reproduced
lost awards (260 or 270 XP instead of 330), partial rollback, and stale unlock
saves overwriting XP.

## Gotchas

- **Skill tree hierarchy:** `SkillCategory → Subject → Skill → Badge`. Subjects group related Skills inside a Category (SkillTree-platform model). `Skill.subject` is nullable; a data migration backfills one "General" Subject per Category. `SkillTreeView` response includes both nested `subjects` (new) and flat `skills` (legacy) for backward compatibility. `SkillPrerequisite` allows cross-category and cross-subject requirements. **Taxonomy (14 categories, life-RPG horizon):** maker/STEM side (Electronics, Coding, Making & Fabrication, Woodworking, Science, Math), domestic side (Cooking, Sewing & Textiles, Outdoors), creative side (Art & Crafts, Music, Language Arts), plus the two "whole-life" categories (Life Skills — budgeting/planning/presentation/persistence/communication/time-management/technical-writing/driving; Physical — endurance/strength/flexibility/cycling/swimming/team-sports). Math + Language Arts were added in the 2026 expansion; their `category_mastery` badges landed in the 2026-04-23 review (G2). Driving + Team Sports are `locked: true` behind age/skill prerequisites. The 2026-04-21 review retired two legacy duplicate categories (`Electronics & Circuits`, `STEM Fundamentals`) via the one-shot `cleanup_rpg_catalog` management command — the loader itself is upsert-only and can't delete.

- **Skill XP entry points** (2026-04-21 unification, extended through 2026-10-17): parent-authored activities use `*SkillTag` through-tables to declare which skills an entity exercises; journal and reading use fixed skills, and creations use child-picked skills. `AwardService.grant(xp_tags=…, xp=pool, xp_source_label=…)` is the single dispatch; `SkillService.distribute_tagged_xp(user, tags, pool)` is the underlying helper that splits by `xp_weight`.

  | Activity | Tag model | XP pool source | Wiring point |
  |---|---|---|---|
  | Ventures (projects) | `ProjectSkillTag` | 10 XP/hr on clock-out | `TimecardService` → `AwardService.grant(project=…)` |
  | Milestones | `MilestoneSkillTag` | `xp_amount` per tag (fixed) | `signals.py` project/milestone handlers |
  | Study (homework) | `HomeworkSkillTag` | `xp_amount` per tag (fixed) | `HomeworkService.approve_submission` |
  | Duties (chores) | `ChoreSkillTag` | `Chore.xp_reward` pool | `ChoreService.approve_completion` |
  | Rituals (habits) | `HabitSkillTag` | `Habit.xp_reward` pool | `HabitService.log_tap` (positive direction only) |
  | Trials (quests) | `QuestSkillTag` | `QuestDefinition.xp_reward` pool | `QuestService._complete_quest` |
  | Journal entries | — (hardcoded) | 15 XP split 2:1 | `ChronicleService.write_journal` (one per user per local day, enforced by unique constraint) |
  | Creations | child-picked on row (primary + optional secondary) | 10 XP baseline pool + parent-granted bonus pool (default +15 XP) | `CreationService.log_creation` (first 2 per local day) + `CreationService.approve_bonus` |
  | Reading | fixed Language Arts::Reading Comprehension | 15 base XP after ten cumulative new minutes today | `ReadingRewardService.credit_new_session` (one reward per family-local day) |

  Journal, Creations and Reading do not use a parent-authored `*SkillTag` table. Journal uses a hardcoded `JOURNAL_SKILL_WEIGHTS = [("Creative Writing", 2), ("Vocabulary", 1)]` — stable two-skill fan-out. Reading credits its fixed skill and persists actual boosted XP in a daily receipt; missing or locked skills receive no invented XP. Creations are **child-picked at log time** (1 primary + optional 1 secondary from a creative allow-list — see `apps/creations/constants.py`) and split 70/30 when both are set, 100% to primary when solo. The baseline XP uses a `_CreationTag` shim matching `SkillService.distribute_tagged_xp`'s duck-type — no DB fan-out table needed for this pool. The parent-granted bonus IS persisted via `CreationBonusSkillTag` because parents can override the child's choices and the tags are visible on the Creation's audit trail.

  The three weighted variants (Chore/Habit/Quest) share the `ProjectSkillTag` shape (`entity FK`, `skill FK`, `xp_weight`). Homework stays on the `xp_amount` fixed-per-tag pattern to preserve parent intuition ("this assignment is worth 15 XP each to Math and Reading"). Untagged chores/habits/quests award coins + items + badge evaluation without skill-tree credit — that matches the pre-2026-04-21 behaviour so nothing silently regresses. `quests.yaml` authoring accepts a `skill_tags:` block per quest using `"Skill Name"` (unique) or `"Category::Skill Name"` disambiguation; the loader upserts `QuestSkillTag` rows. Parent-authored chores/habits set tags via MCP (`set_chore_skill_tags`, `set_habit_skill_tags`, `set_quest_definition_skill_tags`), Django admin, or — for chores + habits — the parent UI form.

- **Parent UI for skill tags** (chores + habits): `<SkillTagEditor>` ([`frontend/src/components/SkillTagEditor.jsx`](/frontend/src/components/SkillTagEditor.jsx)) renders inside `ChoreFormModal` + `HabitFormModal` — parents add rows (skill picker grouped by category via `<optgroup>` + weight dropdown 1-5), the component handles dedupe (already-used skills don't appear in the add menu), and the full tag list POSTs inline on create/update. No separate "skill-tags" sub-endpoint — [`ChoreWriteSerializer`](/apps/chores/serializers.py) and [`HabitWriteSerializer`](/apps/habits/serializers.py) accept `skill_tags: [{skill_id, xp_weight}, …]` alongside the rest of the form.
  - **API contract** — three semantics on the write payload:
    - `skill_tags` omitted → leave existing tags alone (typical PATCH case)
    - `skill_tags: [...]` with entries → replace the entire tag set
    - `skill_tags: []` → strip all tags (explicit clear)
  - **`write_only=True` is load-bearing.** The write serializers declare `skill_tags = ListField(child=DictField(), required=False, write_only=True)`. Without `write_only`, DRF's `create()` response-body serialization would try to iterate the reverse-FK `chore.skill_tags` RelatedManager through `ListField.to_representation` and 500 with `'RelatedManager' object is not iterable`. The read surface comes from the nested `ChoreSkillTagSerializer`/`HabitSkillTagSerializer` on `ChoreSerializer`/`HabitSerializer` (which emit the friendly shape with `skill_name` + `skill_category`). Pinned by `test_skill_tags_are_only_write` in [`apps/chores/tests/test_views.py`](/apps/chores/tests/test_views.py).
  - **Atomic apply.** `ChoreViewSet.perform_create/update` and `HabitViewSet.perform_create/update` wrap in `@transaction.atomic`, and the `_apply_skill_tags` helper pre-validates every `skill_id` before `bulk_create`. This matters on SQLite (dev/test) because it defers FK constraint checks to commit — without pre-validation a bad `skill_id` would return 201 and then rollback on IntegrityError, leaving callers confused. Pinned by `test_invalid_skill_id_in_skill_tags_returns_400`.

- **XP/Badges:** clock-out distributes 10 XP/hour across project skill tags (`ProjectSkillTag.xp_weight`); milestone completion awards `MilestoneSkillTag.xp_amount`. Triggers badge evaluation across 58 criterion types grouped by subsystem:
  - **time:** `hours_worked`, `hours_in_day`, `days_worked`, `first_clock_in`, `early_bird` (before 8 AM), `late_night` (after 9 PM)
  - **projects/milestones:** `projects_completed`, `first_project`, `category_projects`, `materials_under_budget`, `perfect_timecard`, `photos_uploaded`, `bounty_completed`, `milestones_completed`, `fast_project` (completed in ≤ N days), `co_op_project_completed` (ProjectCollaborator rows)
  - **skills:** `skill_level_reached`, `skills_unlocked`, `skill_categories_breadth`, `subjects_completed`, `cross_category_unlock`, `category_mastery` (excludes locked-by-default skills — see "Category Mastery" gotcha)
  - **economy:** `total_earned` (money lifetime), `total_coins_earned` (coin lifetime — ignores spends), `coins_spent_lifetime`, `savings_goal_completed`, `reward_redeemed`
  - **homework:** `homework_planned_ahead`, `homework_on_time_count`
  - **creations:** `creations_logged` (lifetime count, all statuses — Maker ladder), `creations_approved` (only APPROVED status — Framed/Featured/Legacy), `creation_skill_breadth` (distinct creative skills used across primary + secondary tags — Polymath)
  - **RPG progression:** `streak_days`, `perfect_days_count`, `streak_freeze_used`, `habit_max_strength`, `habit_count_at_strength` (N habits at ≥ strength S simultaneously), `habit_taps_lifetime` (cumulative positive taps), `chore_completions`, `quest_completed`, `boss_quests_completed` / `collection_quests_completed` (quest-subtype ladders), `pets_hatched`, `pet_species_owned`, `mounts_evolved`
  - **completionism + meta:** `badges_earned_count` (universal Collector ladder), `cosmetic_set_owned` (own every slug in a named set — e.g. Scholar's Wardrobe), `cosmetic_full_set` (all 4 slots equipped), `full_potion_shelf`, `consumable_variety`, `chronicle_milestones_logged` (Chronicle MILESTONE-kind entries — long-horizon recognition), `grade_reached`, `birthdays_logged`

  Each criterion has a matching `@criterion`-decorated checker in [`criteria.py`](criteria.py). `streak_freeze_used` + `perfect_days_count` read via `CharacterProfile.objects.filter(user=user).values(...).first()` rather than `user.character_profile.<field>` — the reverse-OneToOne cache goes stale after direct `profile.save()` calls and tripped earlier test setups. Badges also award rarity-scaled Coins. **`AwardService.grant(user, *, xp, coins, coin_reason, money, money_entry_type, …)`** is the unified distribution helper — chore approval and project completion route both ledgers through it in one call so paired awards are atomic, badge evaluation runs once, and new triggers extend in one place.

- **Badge scopes** (`_CRITERIA_SCOPES` in `criteria.py`): performance optimization that limits badge evaluation to relevant criterion families. Each call site passes `badge_scopes={...}` to `AwardService.grant` or `BadgeService.evaluate_badges`. Scope vocabulary: `time`, `project`, `skill_xp`, `chore`, `homework_create`, `homework_complete`, `habit`, `quest`, `pet`, `rpg_inventory`, `coin`, `money`, `savings`, `rewards`, `chronicle`, `creation`, `movement`, `badges` (meta — BADGES_EARNED ladder). Only criteria whose scope set intersects the caller's scopes are evaluated. The `badges` meta-scope is included in most calls because earning any badge can trigger the universal Collector ladder.

## Key entry points
- `services.py` — `SkillService`, `BadgeService`, `AwardService.grant`.
- `criteria.py` — `@criterion`-decorated checkers for every criterion type. Buckets criterion types by subsystem (time, projects/milestones, skills, economy, homework, creations, RPG progression, completionism).
- `models.py` — `SkillCategory`, `Subject`, `Skill`, `Badge`, `SkillPrerequisite`, `SkillProgress`, `ProjectSkillTag`, `MilestoneSkillTag`, `Badge.CriteriaType`.
