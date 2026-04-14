# CLAUDE.md

## Project
The Abby Project — Django + React app for tracking kids' projects, chores, and homework: time tracking, weekly timecards, payment ledger (Greenlight), non-monetary Coins economy + reward shop, skill tree (Category → Subject → Skill) with badges, Instructables/PDF project ingestion with an AI enrichment pipeline, and a Habitica-inspired RPG gamification layer (character profiles, streaks, habits, random drops, collectible pets with mount evolution, quests, and cosmetics).

## Stack
- **Backend:** Django 5.1, DRF 3.15, PostgreSQL 16, Redis 7, Celery 5.4 + Beat, Gunicorn, Python 3.12
- **Frontend:** React 19, Vite 8, Tailwind 4, Framer Motion, React Router 7, lucide-react
- **Deploy:** Single multi-stage Docker image — Node builds the React bundle, Django serves it + the API via WhiteNoise from one origin. Compose services: `db`, `redis`, `django`, `celery_worker`, `celery_beat`. Coolify via `.deploy.yml`; CI/CD via `.github/workflows/ci-cd.yml`.
- **Observability:** Self-hosted Sentry at `logs.neato.digital` — error tracking, performance tracing, and release automation with source map upload via `@sentry/vite-plugin`.

## Commands
```bash
# Full stack
docker compose up --build
docker compose exec django python manage.py migrate --noinput
docker compose exec django python manage.py seed_data --noinput
docker compose exec django python manage.py createsuperuser

# Frontend (local)
cd frontend && npm run dev       # :3000 with /api proxy to :8000
npm run build
npm run lint

# Backend tests (ingestion pipeline has tests under apps/projects/tests/)
docker compose exec django python manage.py test
```

## Architecture
```
config/              Django project
  settings.py        Single settings module, env-driven
  urls.py            API includes + SPA catch-all (spa_view)
  celery.py          Celery app factory
  health.py          /health endpoint
  base_models.py     Abstract CreatedAtModel, TimestampedModel
  permissions.py     Shared IsParent DRF permission
  services.py        BaseLedgerService (get_balance/get_breakdown) — shared by
                     PaymentService and CoinService
  viewsets.py        RoleFilteredQuerySetMixin, NestedProjectResourceMixin,
                     get_child_or_404, child_not_found_response
apps/
  projects/          User (role=parent|child), Project (payment_kind), Milestone,
                     Step (FK to Milestone), Resource (FK to Step),
                     MaterialItem, Notification, ProjectTemplate (+ milestones,
                     steps, materials), ProjectCollaborator, SavingsGoal,
                     ProjectIngestionJob, Instructables scraper, AI suggestions,
                     ingestion/ Scrapy-style Item Pipeline,
                     management/commands/seed_data.py
  timecards/         TimeEntry (Active|Completed|Voided), Timecard,
                     ClockService, TimeEntryService, TimecardService,
                     Celery tasks, CSV export
  payments/          PaymentLedger (hourly/project_bonus/bounty_payout/
                     milestone_bonus/materials_reimbursement/payout/adjustment/
                     chore_reward/coin_exchange),
                     PaymentService (extends BaseLedgerService),
                     Greenlight CSV import, PaymentAdjustmentView
  achievements/      Subject → Skill → Badge models (17 criterion types incl.
                     subjects_completed), SkillPrerequisite, SkillProgress,
                     ProjectSkillTag, MilestoneSkillTag,
                     SkillService, BadgeService
  rewards/           CoinLedger, Reward, RewardRedemption, ExchangeRequest,
                     CoinService (extends BaseLedgerService), RewardService,
                     ExchangeService (money→coins with parent approval),
                     CoinAdjustmentView (parent-only manual adjust)
  chores/            Chore (recurring task definitions), ChoreCompletion
                     (submit→approve workflow), ChoreService,
                     supports alternating-week schedules (shared custody)
  homework/          HomeworkAssignment (one-off tasks with due dates,
                     effort-scaled rewards, timeliness bonuses),
                     HomeworkSubmission (submit→approve with proof photos),
                     HomeworkProof (required image uploads), HomeworkTemplate,
                     HomeworkSkillTag (XP distribution), HomeworkService,
                     AI-planned long-form homework via MCP create_project
  portfolio/         ProjectPhoto, ZIP export
  rpg/               CharacterProfile (level, streaks, cosmetic slots),
                     Habit, HabitLog, ItemDefinition (9 item types, 5 rarities),
                     UserInventory, DropTable, DropLog,
                     StreakService, HabitService, DropService, CosmeticService,
                     GameLoopService (central orchestrator hooked into
                     clock-out, chore approval, project/milestone signals,
                     habit taps). Celery tasks: evaluate_perfect_day_task,
                     decay_habit_strength_task.
  pets/              PetSpecies (8 base creatures), PotionType (6 variants →
                     48 possible pets/mounts), UserPet (growth 0-100),
                     UserMount (evolved form), PetService (hatch, feed,
                     evolve, activate).
  quests/            QuestDefinition (boss/collection, trigger_filter JSON,
                     badge gating), Quest (status, rage_shield),
                     QuestParticipant (multi-player-ready), QuestRewardItem,
                     QuestService (start, record_progress, complete, expire,
                     apply_boss_rage). Celery tasks: expire_quests_task,
                     apply_boss_rage_task.
frontend/src/
  api/
    client.js        Fetch wrapper with token auth
    index.js         All endpoint functions (single import surface)
  hooks/useApi.js    useAuth, useApi
  components/        Card, Loader, ErrorAlert, EmptyState, StatusBadge,
                     TabButton, BottomSheet, FormModal, Layout,
                     NotificationBell, DifficultyStars, ProgressBar
  constants/         colors.js, styles.js (shared Tailwind class helpers)
  utils/             format.js, api.js (normalizeList), image.js
  pages/             Dashboard, Projects, ProjectDetail, ProjectNew,
                     ProjectIngest, ClockPage, Chores, Homework, Habits,
                     Inventory, Stable, Quests, Character, Timecards, Payments,
                     Rewards, Achievements, Portfolio, Manage (parent CRUD),
                     SettingsPage, Login
  hooks/useDropToasts.js  Polls /api/drops/recent/ every 20s, emits rarity-
                          colored toast celebrations via DropToastStack
  themes.js          Seasonal theme switching
```

## Auth (important)
- API uses DRF **TokenAuthentication** (not session).
- Login: `POST /api/auth/` with `{action: "login", username, password}` → returns user + `{token}`.
- Frontend stores token in `localStorage` key `abby_auth_token`, sends `Authorization: Token <key>`.
- Django admin still uses session auth at `/admin/`.
- Parent-only endpoints use `config.permissions.IsParent`; child-scoped querysets use `RoleFilteredQuerySetMixin.get_role_filtered_queryset` (parents see everything, children see rows where `role_filter_field == self`).

## Shared plumbing (`config/`)
- **`config/base_models.py`** — `CreatedAtModel` (auto `created_at`), `TimestampedModel` (adds auto `updated_at`), and `ApprovalWorkflowModel` (adds `decided_at` + `decided_by` FK for submit-then-approve flows; subclasses define their own `status` field/choices). Concrete models across apps inherit from these; abstract bases live in `config/` rather than any single app.
- **`config/services.py`** — `BaseLedgerService` with `ledger_model`, `category_field`, `default_value` class attrs. `PaymentService` and `CoinService` subclass it for `get_balance`/`get_breakdown`; subclasses add their own award/spend helpers. Also exports `finalize_decision(instance, new_status, parent, notes="")` — used by every approval service to stamp `status`/`decided_at`/`decided_by` on pending-decision models.
- **`config/permissions.py`** — `IsParent` DRF permission class. Used throughout parent-only viewset actions (`create`, `update`, `destroy`) and manual adjustment endpoints.
- **`config/viewsets.py`** — `RoleFilteredQuerySetMixin`, `NestedProjectResourceMixin` (for URLs like `projects/<project_pk>/milestones/`), plus `get_child_or_404` + `child_not_found_response` helpers for parent-targeting-child actions.
- **`apps/mcp_server/context.py`** — `get_current_user`, `require_parent`, `resolve_target_user(user, requested_id)` (child→self scoping for MCP tools that accept an optional `user_id`).

## Gotchas
- **Single-origin frontend:** The multi-stage `Dockerfile` builds the React bundle with Node, copies `frontend/dist` into `/app/frontend_dist`, and `collectstatic` pulls it into `STATIC_ROOT` via `STATICFILES_DIRS`. `config/urls.py` ends with a `re_path(r"^.*$", spa_view)` catch-all that returns the built `index.html` for any non-API route — React Router handles the rest in the browser. `frontend/vite.config.js` sets `base: '/static/'` for build mode so bundled asset references resolve through WhiteNoise. The API client in `frontend/src/api/client.js` uses relative `/api` URLs. No `VITE_API_URL` env var in production; no separate frontend container.
- **CSRF/proxy:** `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST=True`, and `CSRF_TRUSTED_ORIGINS` needed behind Traefik/Caddy.
- **Sentry release automation:** `@sentry/vite-plugin` in `frontend/vite.config.js` uploads source maps to `logs.neato.digital` during the Dockerfile's frontend-build stage, then deletes `.map` files so they're never served. Conditional on `SENTRY_AUTH_TOKEN` — local builds skip it. CI passes the token + org + project as Docker build args (stage 1 only, not in final image). After deploy, CI `curl`s the Sentry API to associate commits and create a deployment record. Both backend (`SENTRY_RELEASE` in `.env`) and frontend (`VITE_SENTRY_RELEASE` build arg) share the same 8-char git SHA release tag.
- **Ingestion pipeline** (`apps/projects/ingestion/`): Scrapy-style `Pipeline` of ordered `Stage`s assembled by `default_pipeline()` in `pipeline.py` and executed from `runner.py` (which `tasks.run_ingestion_job` calls). `detect.route_source` picks the per-source ingestor (`instructables.py`, `pdf.py`, `generic_url.py`) which becomes the `ParseStage`. Default stages: `ParseStage → NormalizeStage → MarkdownStage → EnrichStage`. `IngestionItem` (alias of `IngestionResult`) carries additive `raw_html`, `markdown`, `ai_suggestions`, `pipeline_warnings` fields — `result_json` shape is additive-only so the frontend poller is unchanged. Instructables scrapes cached in Redis 24h via `fetch_cached()`. Async job tracked in `ProjectIngestionJob` (UUID pk). Tests live in `apps/projects/tests/test_ingestion.py`.
- **AI enrichment** (`ingestion/enrich.py`): `EnrichStage` is a no-op without `ANTHROPIC_API_KEY`. When set, calls Claude (`CLAUDE_MODEL`, default `claude-haiku-4-5-20251001`) with the item's markdown and writes `{category, difficulty, skill_tags, extra_materials, summary}` to `item.ai_suggestions`. Rendered as opt-in chips on the `ProjectIngest` preview — never mutates title/description/milestones/materials automatically. Markdown conversion (`ingestion/markdown.py`) prefers `crawl4ai`, falls back to `markdownify`, then synthesizes from title+description.
- **Clock-in rules:** quiet hours 10pm–7am; max 8h single entry; auto clock-out via Celery every 30 min; >4h flagged for review. DB constraint: one active `TimeEntry` per user (partial unique index on `status="active"`). Entries support a `voided` status — parents can void a completed entry via `POST /api/time-entries/{id}/void/`.
- **Weekly timecards** auto-generated Sunday 23:55 local via Celery Beat; weekly email summaries fire Sunday 08:00. Uses `project.hourly_rate_override` or `user.hourly_rate`. `TimecardService.approve_timecard(timecard, parent, notes)` is the single entry point for the approved-state transition. `Timecard` predates `ApprovalWorkflowModel` and still uses `approved_by`/`approved_at` field names, so the service inlines the audit stamp rather than using `finalize_decision` (renaming the fields would be a wide migration for no behavior change).
- **Skill tree hierarchy:** `SkillCategory → Subject → Skill → Badge`. Subjects group related Skills inside a Category (SkillTree-platform model). `Skill.subject` is nullable; a data migration backfills one "General" Subject per Category. `SkillTreeView` response includes both nested `subjects` (new) and flat `skills` (legacy) for backward compatibility. `SkillPrerequisite` allows cross-category and cross-subject requirements.
- **XP/Badges:** clock-out distributes 10 XP/hour across project skill tags (`ProjectSkillTag.xp_weight`); milestone completion awards `MilestoneSkillTag.xp_amount`. Triggers badge evaluation across 17 criterion types (`projects_completed`, `hours_worked`, `category_projects`, `streak_days`, `first_project`, `first_clock_in`, `materials_under_budget`, `perfect_timecard`, `skill_level_reached`, `skills_unlocked`, `skill_categories_breadth`, `subjects_completed`, `hours_in_day`, `photos_uploaded`, `total_earned`, `days_worked`, `cross_category_unlock`). Badges also award rarity-scaled Coins.
- **Project payment kinds:** `Project.payment_kind` is `required` (counts toward allowance) or `bounty` (up-for-grabs cash reward). On completion, the signal posts either `project_bonus` or `bounty_payout` to `PaymentLedger` — the Payments UI renders them as separate breakdown tiles.
- **Steps vs. Milestones:** `ProjectMilestone` are the *chapters* of a project — parent-authored, optional `bonus_amount` that hits `PaymentLedger.milestone_bonus` via `apps/projects/signals.py:85-125` on completion, optional `MilestoneSkillTag` XP. `ProjectStep` are the *tasks inside a chapter* — instructional walkthrough rows that never award XP, coins, or money. `ProjectStep.milestone` is a nullable FK (`SET_NULL`) so a step can either be grouped under a milestone or "loose" (ungrouped). Deleting a milestone un-groups its steps rather than cascading. The frontend's unified **Plan** tab (`frontend/src/pages/ProjectDetail.jsx`) renders milestones as accordions with their nested steps + a per-phase progress bar; projects with zero milestones fall back to a flat step list. **Milestone completion is not auto-triggered** when the last step is checked — parents control bonus payouts manually because the milestone-complete signal posts to PaymentLedger. Templates mirror the same shape (`TemplateStep.milestone` → `TemplateMilestone`); both clone directions (`POST /api/templates/from-project/`, `POST /api/templates/{id}/create-project/`) preserve the step→milestone linkage by rebuilding `ms_id_map` on each side.
- **Project resources:** `ProjectResource` is a reference link (video / doc / image / link) attached either to a project (`step__isnull=True`) or to a specific `ProjectStep` via FK. The detail serializer's top-level `resources` only returns project-level rows; step-scoped resources are nested inside each step to avoid double-counting. Ingestion `ResourceDraft.step_index` (and the MCP `NewResource.step_index`) are 0-based indices into the same payload's `steps` list — both `ProjectIngestViewSet.commit` and the MCP `create_project` tool resolve them to real FKs after creating the steps.
- **Project ingestion preview:** `frontend/src/pages/ProjectIngest.jsx` lets parents author **Milestones** (chapters) above **Steps** (tasks) before commit. Each step row carries a milestone dropdown that writes `milestone_index` (0-based) into the staged payload; deleting a milestone shifts every step's `milestone_index` down so post-commit FKs don't dangle. The commit endpoint silently falls back to `milestone=None` when an index is out of range — never 500.
- **Coins economy** (`apps/rewards/`): non-monetary progression currency parallel to `PaymentLedger`. `CoinLedger` is append-only with reasons `hourly|project_bonus|bounty_bonus|milestone_bonus|badge_bonus|redemption|refund|adjustment|chore_reward|exchange`. Earn hooks: clock-out awards `settings.COINS_PER_HOUR × hours` (default 5), project completion awards flat×difficulty (bounty pays 2.5×), badge earn awards `settings.COINS_PER_BADGE_RARITY[rarity]`. Spend happens through `RewardService.request_redemption`, which deducts coins immediately into a "held" debit tied to the `RewardRedemption` row. Parents can make manual adjustments through `POST /api/coins/adjust/` (validates balance on negative amounts).
- **Money→Coins exchange** (`apps/rewards/`): Children can exchange earned money for coins at a configurable rate (`settings.COINS_PER_DOLLAR`, default 10). `ExchangeRequest` tracks the lifecycle (pending → approved/denied). `ExchangeService.request_exchange` validates balance, snapshots the rate, and notifies parents. On approval, `ExchangeService.approve` atomically debits `PaymentLedger` (`coin_exchange`, negative) and credits `CoinLedger` (`exchange`, positive). Money is **not held** at request time — balance is re-verified at approval. Denial has no ledger side-effects. Routes: `POST /api/coins/exchange/` (create), `GET /api/coins/exchange/rate/` (current rate), `GET /api/coins/exchange/list/` (role-filtered), `POST /api/coins/exchange/{id}/approve/` and `.../reject/` (parent-only). Frontend: exchange button on `/rewards` (child-only), pending exchange queue (parent-only), exchange history with status badges.
- **Reward shop** (`apps/rewards/`): Parent-approved redemption flow mirroring timecard approval. Child requests a `Reward` → `RewardRedemption` status `pending` + coins held → parent approves (`fulfilled`) or denies (refund via `CoinLedger.Reason.REFUND`, stock restored). Rewards have rarity tiers and optional stock. Parents can CRUD `Reward` rows (uses `RewardWriteSerializer` + multipart for image upload). Routes: `/api/rewards/`, `/api/rewards/{id}/redeem/`, `/api/redemptions/` with `approve`/`reject` actions, `/api/coins/` for balance + recent ledger, `/api/coins/adjust/` for parent adjustments. Frontend page: `/rewards`. Parent approval queue rendered inline.
- **Chores** (`apps/chores/`): recurring household tasks with a submit-then-approve workflow. `Chore` defines the task (title, icon, `reward_amount`, `coin_reward`, recurrence `daily|weekly|one_time`). `ChoreCompletion` tracks each instance (status `pending|approved|rejected`, snapshots reward values at submission). **Shared-custody support:** `Chore.week_schedule` is `every_week` (default) or `alternating`; when alternating, `schedule_start_date` sets the reference "on" week and `ChoreService.is_active_this_week()` compares ISO week parity. Availability is computed on-the-fly — no pre-generated instances, no Celery. On approval, `ChoreService.approve_completion()` posts `PaymentLedger.EntryType.CHORE_REWARD` and `CoinLedger.Reason.CHORE_REWARD`. `ChoreCompletion.completed_date` is a `DateField` — for daily chores it equals today; for weekly it equals Monday of the week. A `UniqueConstraint` on `(chore, user, completed_date)` excluding rejected completions prevents duplicates. Routes: `/api/chores/` (CRUD + `complete` action), `/api/chore-completions/` (read-only + `approve`/`reject` actions). Frontend page: `/chores`. MCP tools: `list_chores`, `get_chore`, `create_chore`, `update_chore`, `complete_chore`, `list_chore_completions`, `approve_chore_completion`, `reject_chore_completion`.
- **Homework** (`apps/homework/`): one-off homework assignments with a submit-then-approve workflow requiring proof image uploads. Both parents and children can create assignments (child-created auto-assigns to self). Rewards are effort-scaled (`HOMEWORK_EFFORT_MULTIPLIERS`, 1-5 levels mapping to 0.5x-2.0x) with timeliness bonuses (`HOMEWORK_EARLY_BONUS` 1.25x for early, `HOMEWORK_LATE_PENALTY` 0.5x for late, zero beyond `HOMEWORK_LATE_CUTOFF_DAYS`). Rewards are computed and snapshotted at submission time. `HomeworkSkillTag` awards XP on approval, triggering badge evaluation. `HomeworkTemplate` stores reusable assignment configs with skill tags as JSON. **AI-planned long-form homework:** `HomeworkAssignment.project` (nullable FK to `Project`) links to a full project generated via Claude + MCP `create_project` tool use for complex multi-step assignments. `POST /api/homework/{id}/plan/` triggers AI planning. Routes: `/api/homework/` (CRUD + `submit` + `save-template` + `plan`), `/api/homework-submissions/` (read-only + `approve`/`reject`), `/api/homework-templates/` (CRUD + `create-assignment`), `/api/homework/dashboard/`. Frontend page: `/homework`. Portfolio integration: approved homework proofs appear alongside project photos with filter tabs. MCP tools: `list_homework`, `get_homework`, `create_homework`, `submit_homework`, `list_homework_submissions`, `approve_homework_submission`, `reject_homework_submission`.
- **RPG game loop** (`apps/rpg/services.py`): `GameLoopService.on_task_completed(user, trigger_type, context)` is the single orchestrator called from all existing flows — clock-out (`apps/timecards/services.py`), chore approval (`apps/chores/services.py`), project/milestone completion signals (`apps/projects/signals.py`), and habit taps (`apps/rpg/views.py`). Pipeline: (1) `StreakService.record_activity` updates `CharacterProfile.login_streak`, first-of-day action awards streak-scaled check-in coins (`3 × min(1 + streak × 0.07, 2.0)`) via `CoinLedger.Reason.ADJUSTMENT`; (2) `DropService.process_drops` rolls against `BASE_DROP_RATES[trigger_type]` + streak bonus (`min(streak × 0.05, 0.50)`); (3) `QuestService.record_progress` applies damage/collection if the user has an active quest and the trigger matches the quest's `trigger_filter`. Returns `{trigger_type, streak, drops, quest, notifications}` — failures in quest progress are logged but never break the parent flow (wrapped in `try/except`).
- **Streaks & daily engagement** (`apps/rpg/`): `CharacterProfile` auto-created per user via `post_save` signal on `projects.User` (see `apps/rpg/signals.py`). `login_streak` resets to 1 on a gap > 1 day, increments on consecutive days, and is tracked alongside `longest_login_streak`. Milestone notifications fire at streaks of 3, 7, 14, 30, 60, 100 (`NotificationType.STREAK_MILESTONE`). **Perfect Day:** `evaluate_perfect_day_task` (Celery, 23:55 local) awards `perfect_days_count += 1` and 15 bonus coins to any child who was active today AND completed every daily chore. Gentle-nudge design: missed days dim the streak flame visually and reset the multiplier, but NEVER destroy earned coins/XP/items.
- **Habits** (`apps/rpg/`): Micro-behaviors distinct from chores — no parent approval, multiple taps/day allowed, no dollar rewards. `Habit.habit_type` is `positive`/`negative`/`both` — positive rejects `-1` taps, negative rejects `+1`. Each tap creates a `HabitLog` with `streak_at_time` snapshot. `strength` increments with `+1`, decrements with `-1`; the `decay_habit_strength_task` (Celery, 00:05 local) decays untapped habits by 1 toward 0. `HabitSerializer` exposes a computed `color` field (red-dark → red-light → yellow → green-light → green → blue) based on strength. Positive taps trigger `GameLoopService.on_task_completed(user, "habit_log", {"habit_id": ...})`. Both parents and children can create habits for themselves; parents can create for any child and are the only ones who can edit/delete.
- **Drops & inventory** (`apps/rpg/`): `ItemDefinition` is the master catalog (9 item types: egg, potion, food, cosmetic_frame, cosmetic_title, cosmetic_theme, cosmetic_pet_accessory, quest_scroll, coin_pouch; 5 rarities). Cross-entity references are typed: `ItemDefinition.pet_species` FK (eggs → `PetSpecies`), `ItemDefinition.potion_type` FK (potions → `PotionType`), `ItemDefinition.food_species` FK (food → preferred `PetSpecies`). `metadata` JSONField stays for genuinely free-form per-type fields (border colors, title text, coin-pouch counts). `DropTable` maps trigger → item → weight with `min_level` gating. `DropService.process_drops` rolls `random.random()` against effective rate, weighted-selects from eligible rows, handles **cosmetic salvage** (already-owned cosmetics auto-convert to coins via `item.coin_value`), increments `UserInventory.quantity`, and logs to `DropLog`. Frontend `useDropToasts` polls `/api/drops/recent/` every 20s and emits rarity-colored toast celebrations via `DropToastStack` (mounted globally in Layout).
- **Pets & mounts** (`apps/pets/`): Lifecycle is **Egg + Potion → Pet → Mount**. `PetService.hatch_pet` consumes one egg item and one potion item from `UserInventory`, reads `egg.pet_species` and `potion.potion_type` FKs (falls back to the legacy `metadata["species"]`/`["variant"]` strings for unmigrated rows), enforces one pet per `(user, species, potion)` combo, and creates a `UserPet` with `growth_points=0`. `PetSpecies.available_potions` M2M declares which species × potion combos are valid (defaults to all potions when unspecified in a content pack). `PetService.feed_pet` consumes a food item and adds growth — +15 if `food.food_species == pet.species` (preferred, FK-driven), +5 otherwise (neutral). At `growth_points >= 100`, the pet auto-evolves: `UserPet.evolved_to_mount=True` and a matching `UserMount` row is created (the original pet is retained in the stable). Only one `UserPet` and one `UserMount` can be `is_active=True` per user at a time — `set_active_pet`/`set_active_mount` deactivate any current one in the same transaction. Dashboard displays the active pet with a growth bar.
- **Quests** (`apps/quests/`): Two types — `boss` (damage-based HP pool) and `collection` (item-count target). `Quest` has a time-boxed `end_date` and tracks `current_progress` and `rage_shield` (extra damage required after an idle day). One active quest per user at a time (`Quest.status=="active"`). **Damage formula** per trigger in `TRIGGER_DAMAGE`: clock_out 10/hr, chore 15, homework 25, milestone 50, badge 30, project_complete 75, habit_log 5. Collection quests count 1 per qualifying trigger. **Trigger filtering** via `QuestDefinition.trigger_filter` JSONField: `allowed_triggers` (whitelist), `project_id`, `skill_category_id`, `chore_ids`, `savings_goal_id`, `streak_target`, `perfect_day_target` — empty filter = all triggers count. **Badge gating:** `QuestDefinition.required_badge` blocks start until earned. **Rage shield:** `apply_boss_rage_task` (Celery, 00:15 local) adds `rage_shield += 20` to any active boss quest where no participant made progress today — visual urgency, easily recoverable. **Expiration:** `expire_quests_task` (Celery, 00:10 local) marks past-due active quests as expired. On completion: `_complete_quest` awards `coin_reward` (via `CoinService`), `xp_reward` (via `AwardService.grant`), and any `QuestRewardItem` entries (to `UserInventory`), then notifies. `QuestParticipant` tracks per-user contribution — built multi-player-ready but currently solo-only in the UI.
- **Cosmetics** (`apps/rpg/`): `CharacterProfile` has 4 nullable FK slots (`active_frame`, `active_title`, `active_theme`, `active_pet_accessory`) with `limit_choices_to={"item_type": ...}` enforcing correct type. `CosmeticService.equip(user, item_id)` validates ownership in `UserInventory` (cosmetics are NOT consumed on equip) and writes to the correct slot based on `COSMETIC_SLOT_MAP`. `CosmeticService.unequip(user, slot)` nils the slot. Duplicate cosmetic drops auto-salvage (see Drops gotcha). Frontend `/character` page shows owned cosmetics grouped by slot with click-to-equip; active items get a rarity-colored ring. Avatar frame renders as a colored border on the profile hero card; title renders as a chip under the display name.
- **RPG content authoring** (`content/rpg/`): Pets, eggs, potions, items, drops, quests, badges, and the skill tree are authored as YAML in `content/rpg/initial/*.yaml` and loaded by `python manage.py loadrpgcontent` — a dependency-ordered, idempotent upsert. `seed_data` invokes this internally. The loader (`apps/rpg/content/loader.py`) is the single source of truth for cross-entity wiring: one `pet_species.yaml` entry fans out to both a `PetSpecies` row and an egg `ItemDefinition` with typed FK; same pattern for `potion_types.yaml` → potion items. Third-party packs live under `content/rpg/packs/<name>/` and are loaded with `--namespace <prefix>-` so slugs don't collide with core. When adding new RPG content, edit YAML — don't add `get_or_create` calls to Python seed code. See `content/rpg/README.md` for schema + authoring workflow.
- **Parent data management:** The `/manage` page (`frontend/src/pages/Manage.jsx`) houses parent CRUD for Children, Project Templates, Rewards, Categories, Subjects, Skills, and Badges. Parents can also:
  - edit child hourly rate via `PATCH /api/children/{id}/` (`ChildViewSet`, `IsParent`, `get/patch` only).
  - adjust coin balances (`POST /api/coins/adjust/`) and payment ledger (`POST /api/payments/adjust/`).
  - void completed time entries (`POST /api/time-entries/{id}/void/`).
  - save a completed `Project` as a reusable `ProjectTemplate` (copies milestones + materials) and later spin a new project from a template for any child.
- **Project templates** (`apps/projects/models.py`: `ProjectTemplate`, `TemplateMilestone`, `TemplateMaterial`): cloned from a completed project via `POST /api/templates/from-project/`; materialized into a new `Project` via `POST /api/templates/{id}/create-project/` with `assigned_to_id`. Optional `is_public` flag.
- **Savings goals** (`apps/projects/models.py`: `SavingsGoal`): child-set targets with `target_amount`/`current_amount` and `percent_complete` property. Endpoints under `/api/savings-goals/`; `update_amount` action recomputes against current balance.
- **Collaborators** (`apps/projects/models.py`: `ProjectCollaborator`): additional child assigned to a project with a `pay_split_percent`. Managed via `/api/projects/{project_pk}/collaborators/`.
- **Notifications:** `apps.projects.Notification` with `NotificationType`s including `redemption_requested`, `chore_submitted`, `chore_approved`, `exchange_requested`, `exchange_approved`, `exchange_denied`, `homework_submitted`, `homework_approved`, `streak_milestone`, `perfect_day`, `daily_check_in`. Routes under `/api/notifications/` with `unread_count`, `mark_all_read`, and per-item `mark_read` actions.
- **Email:** console backend in dev; `DEFAULT_FROM_EMAIL=noreply@summerforge.local`.
- **Timezone:** `America/Phoenix`.

## Env vars (see `.env.example`)
`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CORS_ALLOWED_ORIGINS` (dev-server only), `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PARENT_PASSWORD`, `CHILD_PASSWORD` (seed), `ANTHROPIC_API_KEY` (optional — enables Claude-based project suggestions AND the ingestion `EnrichStage`), `CLAUDE_MODEL` (optional, default `claude-haiku-4-5-20251001`). `VITE_SENTRY_RELEASE` (auto-set by CI to 8-char git SHA — tags frontend errors with the release version). CI-only secrets (GitHub repo settings, not `.env`): `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` — used by `@sentry/vite-plugin` for source map upload and by the deploy step for Sentry release/deploy notification.

### Tunable settings (`config/settings.py`)
- `COINS_PER_HOUR` (default `5`) — coins awarded per clock-out hour.
- `COINS_PER_BADGE_RARITY` — per-rarity coin bonus map (common 5 → legendary 150).
- `COINS_PER_DOLLAR` (default `10`) — coins received per $1.00 in money→coins exchange.
- `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` — 25 MB each, sized for PDF ingestion and photo uploads.
- `HOMEWORK_EFFORT_MULTIPLIERS` — per-effort-level reward scaling (1→0.5x to 5→2.0x).
- `HOMEWORK_EARLY_BONUS` (default `1.25`) — multiplier for submitting before due date.
- `HOMEWORK_ON_TIME_MULTIPLIER` (default `1.0`) — multiplier for same-day submission.
- `HOMEWORK_LATE_PENALTY` (default `0.5`) — multiplier for late submission.
- `HOMEWORK_LATE_CUTOFF_DAYS` (default `3`) — beyond this many days late, rewards are zero.
- `CELERY_BEAT_SCHEDULE`: `auto-clock-out` every 30 min; `weekly-timecards` Sun 23:55; `weekly-email-summaries` Sun 08:00; `daily-reminders` 07:00; `rpg-perfect-day` 23:55 (evaluate perfect days); `rpg-habit-decay` 00:05 (decay untapped habits); `quest-expire` 00:10 (mark expired quests); `quest-boss-rage` 00:15 (add rage shield to idle boss quests).

### RPG tunables (hardcoded constants in `apps/rpg/services.py`)
These are intentionally NOT in settings — they're game-design constants, not deploy-time config.
- `BASE_CHECK_IN_COINS = 3` — base daily check-in bonus before streak multiplier.
- `STREAK_MULTIPLIER_PER_DAY = 0.07` and `STREAK_MULTIPLIER_CAP = 2.0` — check-in bonus scales `min(1 + streak × 0.07, 2.0)`.
- `BASE_DROP_RATES` — dict of trigger → base drop probability (clock_out 0.40, chore 0.30, homework 0.35, milestone 0.80, badge 1.00, quest_complete 1.00, perfect_day 1.00, habit_log 0.15).
- `STREAK_DROP_BONUS_PER_DAY = 0.05` and `STREAK_DROP_BONUS_CAP = 0.50` — streak adds up to +50% to base drop rate.
- `GROWTH_PREFERRED_FOOD = 15`, `GROWTH_NEUTRAL_FOOD = 5`, `EVOLUTION_THRESHOLD = 100` (in `apps/pets/services.py`) — pet growth mechanics.
- `TRIGGER_DAMAGE` (in `apps/quests/services.py`) — per-trigger boss damage table; clock_out multiplied by hours.

## Conventions
- Inherit concrete models from `config.base_models.{CreatedAtModel,TimestampedModel}` instead of hand-rolling `created_at`/`updated_at`. Submit-then-approve models (ChoreCompletion, HomeworkSubmission, RewardRedemption, ExchangeRequest) inherit from `ApprovalWorkflowModel` for `decided_at`/`decided_by`.
- Subclass `config.services.BaseLedgerService` for any new append-only ledger. Use `config.services.finalize_decision` for approve/reject state transitions rather than hand-stamping `status`/`decided_at`/`decided_by`.
- For new parent-only endpoints: use `IsParent` from `config.permissions`. For parent-targets-child actions, accept `user_id` in the body and use `get_child_or_404` + `child_not_found_response`.
- For querysets that should be self-scoped for children but full for parents: use `RoleFilteredQuerySetMixin` and override `get_queryset` to call `get_role_filtered_queryset(super().get_queryset())`.
- Frontend: import endpoint functions from `frontend/src/api/index.js` (single source of truth) rather than calling `api.get`/`api.post` directly in pages. Use shared components/helpers from `components/`, `constants/`, `utils/` rather than duplicating.
- Settings values that belong in Django settings (e.g. `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `COINS_PER_HOUR`) should be read via `from django.conf import settings`, not `os.environ`.

## Key entry points
- `manage.py`, `config/wsgi.py`, `config/urls.py`, `config/celery.py`, `config/settings.py`
- `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/vite.config.js`
- Seed: `apps/projects/management/commands/seed_data.py` (sample users/projects/chores/habits); RPG catalog comes from `content/rpg/initial/*.yaml` via `apps/rpg/management/commands/loadrpgcontent.py` + `apps/rpg/content/loader.py`.
- Ingestion: `apps/projects/ingestion/pipeline.py`, `runner.py`, `tasks.py`
- Signals: `apps/projects/signals.py` (project completion → ledger + coin hooks + RPG game loop)
- RPG orchestrator: `apps/rpg/services.py` — `GameLoopService.on_task_completed` is the single entry point called from clock-out, chore approval, project/milestone signals, and habit taps. Extend by adding a new step to this method.
- RPG character auto-creation: `apps/rpg/signals.py` — `post_save` on `projects.User` creates `CharacterProfile`.
- Design spec: `docs/superpowers/specs/2026-04-13-rpg-gamification-layer-design.md`; phase plans under `docs/superpowers/plans/`.
