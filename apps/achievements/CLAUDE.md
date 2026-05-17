# apps/achievements/

Skill tree (Category → Subject → Skill → Badge), the unified `AwardService.grant` dispatch, and 48 badge criterion types grouped by subsystem. The skill XP routing in this app is shared across every major activity in the codebase.

## Models
- `SkillCategory → Subject → Skill → Badge` — full hierarchy.
- `SkillPrerequisite` — allows cross-category and cross-subject requirements.
- `SkillProgress` — per-user skill state.
- `ProjectSkillTag`, `MilestoneSkillTag` — XP fan-out tables (chores/habits/quests/homework use sibling tables in their apps).
- 21 criterion types in `Badge.CriteriaType` — see "XP/Badges" gotcha for the 48-criterion overview.

## Services
- `SkillService` — `distribute_tagged_xp(user, tags, pool)` — splits by `xp_weight`.
- `BadgeService` — badge evaluation across all criterion types.
- `AwardService.grant(user, *, xp, coins, coin_reason, money, money_entry_type, xp_tags, xp_source_label, …)` — **unified distribution helper**. Paired XP + coin + optional money ledger entry. Single entry point for all award flows.

## Gotchas

- **Skill tree hierarchy:** `SkillCategory → Subject → Skill → Badge`. Subjects group related Skills inside a Category (SkillTree-platform model). `Skill.subject` is nullable; a data migration backfills one "General" Subject per Category. `SkillTreeView` response includes both nested `subjects` (new) and flat `skills` (legacy) for backward compatibility. `SkillPrerequisite` allows cross-category and cross-subject requirements. **Taxonomy (14 categories, life-RPG horizon):** maker/STEM side (Electronics, Coding, Making & Fabrication, Woodworking, Science, Math), domestic side (Cooking, Sewing & Textiles, Outdoors), creative side (Art & Crafts, Music, Language Arts), plus the two "whole-life" categories (Life Skills — budgeting/planning/presentation/persistence/communication/time-management/technical-writing/driving; Physical — endurance/strength/flexibility/cycling/swimming/team-sports). Math + Language Arts were added in the 2026 expansion; their `category_mastery` badges landed in the 2026-04-23 review (G2). Driving + Team Sports are `locked: true` behind age/skill prerequisites. The 2026-04-21 review retired two legacy duplicate categories (`Electronics & Circuits`, `STEM Fundamentals`) via the one-shot `cleanup_rpg_catalog` management command — the loader itself is upsert-only and can't delete.

- **Skill XP — seven entry points** (2026-04-21 unification, extended 2026-04-22 and 2026-04-23): every major activity has a `*SkillTag` through-table so parents can declare which skills a given entity exercises. `AwardService.grant(xp_tags=…, xp=pool, xp_source_label=…)` is the single dispatch; `SkillService.distribute_tagged_xp(user, tags, pool)` is the underlying helper that splits by `xp_weight`.

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

  Journal + Creations are the two activities without a parent-authored `*SkillTag` table. Journal uses a hardcoded `JOURNAL_SKILL_WEIGHTS = [("Creative Writing", 2), ("Vocabulary", 1)]` — stable two-skill fan-out. Creations are **child-picked at log time** (1 primary + optional 1 secondary from a creative allow-list — see `apps/creations/constants.py`) and split 70/30 when both are set, 100% to primary when solo. The baseline XP uses a `_CreationTag` shim matching `SkillService.distribute_tagged_xp`'s duck-type — no DB fan-out table needed for this pool. The parent-granted bonus IS persisted via `CreationBonusSkillTag` because parents can override the child's choices and the tags are visible on the Creation's audit trail.

  The three weighted variants (Chore/Habit/Quest) share the `ProjectSkillTag` shape (`entity FK`, `skill FK`, `xp_weight`). Homework stays on the `xp_amount` fixed-per-tag pattern to preserve parent intuition ("this assignment is worth 15 XP each to Math and Reading"). Untagged chores/habits/quests award coins + items + badge evaluation without skill-tree credit — that matches the pre-2026-04-21 behaviour so nothing silently regresses. `quests.yaml` authoring accepts a `skill_tags:` block per quest using `"Skill Name"` (unique) or `"Category::Skill Name"` disambiguation; the loader upserts `QuestSkillTag` rows. Parent-authored chores/habits set tags via MCP (`set_chore_skill_tags`, `set_habit_skill_tags`, `set_quest_definition_skill_tags`), Django admin, or — for chores + habits — the parent UI form.

- **Parent UI for skill tags** (chores + habits): `<SkillTagEditor>` ([`frontend/src/components/SkillTagEditor.jsx`](/frontend/src/components/SkillTagEditor.jsx)) renders inside `ChoreFormModal` + `HabitFormModal` — parents add rows (skill picker grouped by category via `<optgroup>` + weight dropdown 1-5), the component handles dedupe (already-used skills don't appear in the add menu), and the full tag list POSTs inline on create/update. No separate "skill-tags" sub-endpoint — [`ChoreWriteSerializer`](/apps/chores/serializers.py) and [`HabitWriteSerializer`](/apps/habits/serializers.py) accept `skill_tags: [{skill_id, xp_weight}, …]` alongside the rest of the form.
  - **API contract** — three semantics on the write payload:
    - `skill_tags` omitted → leave existing tags alone (typical PATCH case)
    - `skill_tags: [...]` with entries → replace the entire tag set
    - `skill_tags: []` → strip all tags (explicit clear)
  - **`write_only=True` is load-bearing.** The write serializers declare `skill_tags = ListField(child=DictField(), required=False, write_only=True)`. Without `write_only`, DRF's `create()` response-body serialization would try to iterate the reverse-FK `chore.skill_tags` RelatedManager through `ListField.to_representation` and 500 with `'RelatedManager' object is not iterable`. The read surface comes from the nested `ChoreSkillTagSerializer`/`HabitSkillTagSerializer` on `ChoreSerializer`/`HabitSerializer` (which emit the friendly shape with `skill_name` + `skill_category`). Pinned by `test_skill_tags_are_only_write` in [`apps/chores/tests/test_views.py`](/apps/chores/tests/test_views.py).
  - **Atomic apply.** `ChoreViewSet.perform_create/update` and `HabitViewSet.perform_create/update` wrap in `@transaction.atomic`, and the `_apply_skill_tags` helper pre-validates every `skill_id` before `bulk_create`. This matters on SQLite (dev/test) because it defers FK constraint checks to commit — without pre-validation a bad `skill_id` would return 201 and then rollback on IntegrityError, leaving callers confused. Pinned by `test_invalid_skill_id_in_skill_tags_returns_400`.

- **XP/Badges:** clock-out distributes 10 XP/hour across project skill tags (`ProjectSkillTag.xp_weight`); milestone completion awards `MilestoneSkillTag.xp_amount`. Triggers badge evaluation across 48 criterion types grouped by subsystem:
  - **time:** `hours_worked`, `hours_in_day`, `days_worked`, `first_clock_in`, `early_bird` (before 8 AM), `late_night` (after 9 PM)
  - **projects/milestones:** `projects_completed`, `first_project`, `category_projects`, `materials_under_budget`, `perfect_timecard`, `photos_uploaded`, `bounty_completed`, `milestones_completed`, `fast_project` (completed in ≤ N days), `co_op_project_completed` (ProjectCollaborator rows)
  - **skills:** `skill_level_reached`, `skills_unlocked`, `skill_categories_breadth`, `subjects_completed`, `cross_category_unlock`, `category_mastery` (excludes locked-by-default skills — see "Category Mastery" gotcha)
  - **economy:** `total_earned` (money lifetime), `total_coins_earned` (coin lifetime — ignores spends), `coins_spent_lifetime`, `savings_goal_completed`, `reward_redeemed`
  - **homework:** `homework_planned_ahead`, `homework_on_time_count`
  - **creations:** `creations_logged` (lifetime count, all statuses — Maker ladder), `creations_approved` (only APPROVED status — Framed/Featured/Legacy), `creation_skill_breadth` (distinct creative skills used across primary + secondary tags — Polymath)
  - **RPG progression:** `streak_days`, `perfect_days_count`, `streak_freeze_used`, `habit_max_strength`, `habit_count_at_strength` (N habits at ≥ strength S simultaneously), `habit_taps_lifetime` (cumulative positive taps), `chore_completions`, `quest_completed`, `boss_quests_completed` / `collection_quests_completed` (quest-subtype ladders), `pets_hatched`, `pet_species_owned`, `mounts_evolved`
  - **completionism + meta:** `badges_earned_count` (universal Collector ladder), `cosmetic_set_owned` (own every slug in a named set — e.g. Scholar's Wardrobe), `cosmetic_full_set` (all 4 slots equipped), `full_potion_shelf`, `consumable_variety`, `chronicle_milestones_logged` (Chronicle MILESTONE-kind entries — long-horizon recognition), `grade_reached`, `birthdays_logged`

  Each criterion has a matching `@criterion`-decorated checker in [`criteria.py`](criteria.py). `streak_freeze_used` + `perfect_days_count` read via `CharacterProfile.objects.filter(user=user).values(...).first()` rather than `user.character_profile.<field>` — the reverse-OneToOne cache goes stale after direct `profile.save()` calls and tripped earlier test setups. Badges also award rarity-scaled Coins. **`AwardService.grant(user, *, xp, coins, coin_reason, money, money_entry_type, …)`** is the unified distribution helper — chore approval and project completion route both ledgers through it in one call so paired awards are atomic, badge evaluation runs once, and new triggers extend in one place.

## Key entry points
- `services.py` — `SkillService`, `BadgeService`, `AwardService.grant`.
- `criteria.py` — `@criterion`-decorated checkers for every criterion type. Buckets criterion types by subsystem (time, projects/milestones, skills, economy, homework, creations, RPG progression, completionism).
- `models.py` — `SkillCategory`, `Subject`, `Skill`, `Badge`, `SkillPrerequisite`, `SkillProgress`, `ProjectSkillTag`, `MilestoneSkillTag`, `Badge.CriteriaType`.
