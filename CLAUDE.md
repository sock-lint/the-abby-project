# CLAUDE.md

## Project
The Abby Project — Django + React app for tracking summer maker projects: time tracking, weekly timecards, payment ledger (Greenlight), non-monetary Coins economy + reward shop, skill tree (Category → Subject → Skill) with badges, and Instructables/PDF project ingestion with an AI enrichment pipeline.

## Stack
- **Backend:** Django 5.1, DRF 3.15, PostgreSQL 16, Redis 7, Celery 5.4 + Beat, Gunicorn, Python 3.12
- **Frontend:** React 19, Vite 8, Tailwind 4, Framer Motion, React Router 7, lucide-react
- **Deploy:** Single multi-stage Docker image — Node builds the React bundle, Django serves it + the API via WhiteNoise from one origin. Compose services: `db`, `redis`, `django`, `celery_worker`, `celery_beat`. Coolify via `.deploy.yml`; CI/CD via `.github/workflows/ci-cd.yml`.

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
                     milestone_bonus/materials_reimbursement/payout/adjustment),
                     PaymentService (extends BaseLedgerService),
                     Greenlight CSV import, PaymentAdjustmentView
  achievements/      Subject → Skill → Badge models (17 criterion types incl.
                     subjects_completed), SkillPrerequisite, SkillProgress,
                     ProjectSkillTag, MilestoneSkillTag,
                     SkillService, BadgeService
  rewards/           CoinLedger, Reward, RewardRedemption, CoinService
                     (extends BaseLedgerService), RewardService,
                     CoinAdjustmentView (parent-only manual adjust)
  portfolio/         ProjectPhoto, ZIP export
frontend/src/
  api/
    client.js        Fetch wrapper with token auth
    index.js         All endpoint functions (single import surface)
  hooks/useApi.js    useAuth, useApi
  components/        Card, Loader, ErrorAlert, EmptyState, StatusBadge,
                     TabButton, BottomSheet, Layout, NotificationBell,
                     DifficultyStars, ProgressBar
  constants/         colors.js, styles.js (shared Tailwind class helpers)
  utils/             format.js, api.js (normalizeList), image.js
  pages/             Dashboard, Projects, ProjectDetail, ProjectNew,
                     ProjectIngest, ClockPage, Timecards, Payments, Rewards,
                     Achievements, Portfolio, Manage (parent CRUD),
                     SettingsPage, Login
  themes.js          Seasonal theme switching
```

## Auth (important)
- API uses DRF **TokenAuthentication** (not session).
- Login: `POST /api/auth/` with `{action: "login", username, password}` → returns user + `{token}`.
- Frontend stores token in `localStorage` key `abby_auth_token`, sends `Authorization: Token <key>`.
- Django admin still uses session auth at `/admin/`.
- Parent-only endpoints use `config.permissions.IsParent`; child-scoped querysets use `RoleFilteredQuerySetMixin.get_role_filtered_queryset` (parents see everything, children see rows where `role_filter_field == self`).

## Shared plumbing (`config/`)
- **`config/base_models.py`** — `CreatedAtModel` (auto `created_at`) and `TimestampedModel` (adds auto `updated_at`). Concrete models across apps inherit from these; abstract bases live in `config/` rather than any single app.
- **`config/services.py`** — `BaseLedgerService` with `ledger_model`, `category_field`, `default_value` class attrs. `PaymentService` and `CoinService` subclass it for `get_balance`/`get_breakdown`; subclasses add their own award/spend helpers.
- **`config/permissions.py`** — `IsParent` DRF permission class. Used throughout parent-only viewset actions (`create`, `update`, `destroy`) and manual adjustment endpoints.
- **`config/viewsets.py`** — `RoleFilteredQuerySetMixin`, `NestedProjectResourceMixin` (for URLs like `projects/<project_pk>/milestones/`), plus `get_child_or_404` + `child_not_found_response` helpers for parent-targeting-child actions.

## Gotchas
- **Single-origin frontend:** The multi-stage `Dockerfile` builds the React bundle with Node, copies `frontend/dist` into `/app/frontend_dist`, and `collectstatic` pulls it into `STATIC_ROOT` via `STATICFILES_DIRS`. `config/urls.py` ends with a `re_path(r"^.*$", spa_view)` catch-all that returns the built `index.html` for any non-API route — React Router handles the rest in the browser. `frontend/vite.config.js` sets `base: '/static/'` for build mode so bundled asset references resolve through WhiteNoise. The API client in `frontend/src/api/client.js` uses relative `/api` URLs. No `VITE_API_URL` env var in production; no separate frontend container.
- **CSRF/proxy:** `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST=True`, and `CSRF_TRUSTED_ORIGINS` needed behind Traefik/Caddy.
- **Ingestion pipeline** (`apps/projects/ingestion/`): Scrapy-style `Pipeline` of ordered `Stage`s assembled by `default_pipeline()` in `pipeline.py` and executed from `runner.py` (which `tasks.run_ingestion_job` calls). `detect.route_source` picks the per-source ingestor (`instructables.py`, `pdf.py`, `generic_url.py`) which becomes the `ParseStage`. Default stages: `ParseStage → NormalizeStage → MarkdownStage → EnrichStage`. `IngestionItem` (alias of `IngestionResult`) carries additive `raw_html`, `markdown`, `ai_suggestions`, `pipeline_warnings` fields — `result_json` shape is additive-only so the frontend poller is unchanged. Instructables scrapes cached in Redis 24h via `fetch_cached()`. Async job tracked in `ProjectIngestionJob` (UUID pk). Tests live in `apps/projects/tests/test_ingestion.py`.
- **AI enrichment** (`ingestion/enrich.py`): `EnrichStage` is a no-op without `ANTHROPIC_API_KEY`. When set, calls Claude (`CLAUDE_MODEL`, default `claude-haiku-4-5-20251001`) with the item's markdown and writes `{category, difficulty, skill_tags, extra_materials, summary}` to `item.ai_suggestions`. Rendered as opt-in chips on the `ProjectIngest` preview — never mutates title/description/milestones/materials automatically. Markdown conversion (`ingestion/markdown.py`) prefers `crawl4ai`, falls back to `markdownify`, then synthesizes from title+description.
- **Clock-in rules:** quiet hours 10pm–7am; max 8h single entry; auto clock-out via Celery every 30 min; >4h flagged for review. DB constraint: one active `TimeEntry` per user (partial unique index on `status="active"`). Entries support a `voided` status — parents can void a completed entry via `POST /api/time-entries/{id}/void/`.
- **Weekly timecards** auto-generated Sunday 23:55 local via Celery Beat; weekly email summaries fire Sunday 08:00. Uses `project.hourly_rate_override` or `user.hourly_rate`. `Timecard.mark_approved(by_user, notes)` centralizes the approved-state transition.
- **Skill tree hierarchy:** `SkillCategory → Subject → Skill → Badge`. Subjects group related Skills inside a Category (SkillTree-platform model). `Skill.subject` is nullable; a data migration backfills one "General" Subject per Category. `SkillTreeView` response includes both nested `subjects` (new) and flat `skills` (legacy) for backward compatibility. `SkillPrerequisite` allows cross-category and cross-subject requirements.
- **XP/Badges:** clock-out distributes 10 XP/hour across project skill tags (`ProjectSkillTag.xp_weight`); milestone completion awards `MilestoneSkillTag.xp_amount`. Triggers badge evaluation across 17 criterion types (`projects_completed`, `hours_worked`, `category_projects`, `streak_days`, `first_project`, `first_clock_in`, `materials_under_budget`, `perfect_timecard`, `skill_level_reached`, `skills_unlocked`, `skill_categories_breadth`, `subjects_completed`, `hours_in_day`, `photos_uploaded`, `total_earned`, `days_worked`, `cross_category_unlock`). Badges also award rarity-scaled Coins.
- **Project payment kinds:** `Project.payment_kind` is `required` (counts toward allowance) or `bounty` (up-for-grabs cash reward). On completion, the signal posts either `project_bonus` or `bounty_payout` to `PaymentLedger` — the Payments UI renders them as separate breakdown tiles.
- **Steps vs. Milestones:** `ProjectMilestone` are the *chapters* of a project — parent-authored, optional `bonus_amount` that hits `PaymentLedger.milestone_bonus` via `apps/projects/signals.py:85-125` on completion, optional `MilestoneSkillTag` XP. `ProjectStep` are the *tasks inside a chapter* — instructional walkthrough rows that never award XP, coins, or money. `ProjectStep.milestone` is a nullable FK (`SET_NULL`) so a step can either be grouped under a milestone or "loose" (ungrouped). Deleting a milestone un-groups its steps rather than cascading. The frontend's unified **Plan** tab (`frontend/src/pages/ProjectDetail.jsx`) renders milestones as accordions with their nested steps + a per-phase progress bar; projects with zero milestones fall back to a flat step list. **Milestone completion is not auto-triggered** when the last step is checked — parents control bonus payouts manually because the milestone-complete signal posts to PaymentLedger. Templates mirror the same shape (`TemplateStep.milestone` → `TemplateMilestone`); both clone directions (`POST /api/templates/from-project/`, `POST /api/templates/{id}/create-project/`) preserve the step→milestone linkage by rebuilding `ms_id_map` on each side.
- **Project resources:** `ProjectResource` is a reference link (video / doc / image / link) attached either to a project (`step__isnull=True`) or to a specific `ProjectStep` via FK. The detail serializer's top-level `resources` only returns project-level rows; step-scoped resources are nested inside each step to avoid double-counting. Ingestion `ResourceDraft.step_index` (and the MCP `NewResource.step_index`) are 0-based indices into the same payload's `steps` list — both `ProjectIngestViewSet.commit` and the MCP `create_project` tool resolve them to real FKs after creating the steps.
- **Project ingestion preview:** `frontend/src/pages/ProjectIngest.jsx` lets parents author **Milestones** (chapters) above **Steps** (tasks) before commit. Each step row carries a milestone dropdown that writes `milestone_index` (0-based) into the staged payload; deleting a milestone shifts every step's `milestone_index` down so post-commit FKs don't dangle. The commit endpoint silently falls back to `milestone=None` when an index is out of range — never 500.
- **Coins economy** (`apps/rewards/`): non-monetary progression currency parallel to `PaymentLedger`. `CoinLedger` is append-only with reasons `hourly|project_bonus|bounty_bonus|milestone_bonus|badge_bonus|redemption|refund|adjustment`. Earn hooks: clock-out awards `settings.COINS_PER_HOUR × hours` (default 5), project completion awards flat×difficulty (bounty pays 2.5×), badge earn awards `settings.COINS_PER_BADGE_RARITY[rarity]`. Spend happens through `RewardService.request_redemption`, which deducts coins immediately into a "held" debit tied to the `RewardRedemption` row. Parents can make manual adjustments through `POST /api/coins/adjust/` (validates balance on negative amounts).
- **Reward shop** (`apps/rewards/`): Parent-approved redemption flow mirroring timecard approval. Child requests a `Reward` → `RewardRedemption` status `pending` + coins held → parent approves (`fulfilled`) or denies (refund via `CoinLedger.Reason.REFUND`, stock restored). Rewards have rarity tiers and optional stock. Parents can CRUD `Reward` rows (uses `RewardWriteSerializer` + multipart for image upload). Routes: `/api/rewards/`, `/api/rewards/{id}/redeem/`, `/api/redemptions/` with `approve`/`deny` actions, `/api/coins/` for balance + recent ledger, `/api/coins/adjust/` for parent adjustments. Frontend page: `/rewards`. Parent approval queue rendered inline.
- **Parent data management:** The `/manage` page (`frontend/src/pages/Manage.jsx`) houses parent CRUD for Children, Project Templates, Rewards, Categories, Subjects, Skills, and Badges. Parents can also:
  - edit child hourly rate via `PATCH /api/children/{id}/` (`ChildViewSet`, `IsParent`, `get/patch` only).
  - adjust coin balances (`POST /api/coins/adjust/`) and payment ledger (`POST /api/payments/adjust/`).
  - void completed time entries (`POST /api/time-entries/{id}/void/`).
  - save a completed `Project` as a reusable `ProjectTemplate` (copies milestones + materials) and later spin a new project from a template for any child.
- **Project templates** (`apps/projects/models.py`: `ProjectTemplate`, `TemplateMilestone`, `TemplateMaterial`): cloned from a completed project via `POST /api/templates/from-project/`; materialized into a new `Project` via `POST /api/templates/{id}/create-project/` with `assigned_to_id`. Optional `is_public` flag.
- **Savings goals** (`apps/projects/models.py`: `SavingsGoal`): child-set targets with `target_amount`/`current_amount` and `percent_complete` property. Endpoints under `/api/savings-goals/`; `update_amount` action recomputes against current balance.
- **Collaborators** (`apps/projects/models.py`: `ProjectCollaborator`): additional child assigned to a project with a `pay_split_percent`. Managed via `/api/projects/{project_pk}/collaborators/`.
- **Notifications:** `apps.projects.Notification` with 9 `NotificationType`s (incl. `redemption_requested`). Routes under `/api/notifications/` with `unread_count`, `mark_all_read`, and per-item `mark_read` actions.
- **Email:** console backend in dev; `DEFAULT_FROM_EMAIL=noreply@summerforge.local`.
- **Timezone:** `America/Phoenix`.

## Env vars (see `.env.example`)
`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CORS_ALLOWED_ORIGINS` (dev-server only), `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PARENT_PASSWORD`, `CHILD_PASSWORD` (seed), `ANTHROPIC_API_KEY` (optional — enables Claude-based project suggestions AND the ingestion `EnrichStage`), `CLAUDE_MODEL` (optional, default `claude-haiku-4-5-20251001`).

### Tunable settings (`config/settings.py`)
- `COINS_PER_HOUR` (default `5`) — coins awarded per clock-out hour.
- `COINS_PER_BADGE_RARITY` — per-rarity coin bonus map (common 5 → legendary 150).
- `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` — 25 MB each, sized for PDF ingestion and photo uploads.
- `CELERY_BEAT_SCHEDULE`: `auto-clock-out` every 30 min; `weekly-timecards` Sun 23:55; `weekly-email-summaries` Sun 08:00.

## Conventions
- Inherit concrete models from `config.base_models.{CreatedAtModel,TimestampedModel}` instead of hand-rolling `created_at`/`updated_at`.
- Subclass `config.services.BaseLedgerService` for any new append-only ledger.
- For new parent-only endpoints: use `IsParent` from `config.permissions`. For parent-targets-child actions, accept `user_id` in the body and use `get_child_or_404` + `child_not_found_response`.
- For querysets that should be self-scoped for children but full for parents: use `RoleFilteredQuerySetMixin` and override `get_queryset` to call `get_role_filtered_queryset(super().get_queryset())`.
- Frontend: import endpoint functions from `frontend/src/api/index.js` (single source of truth) rather than calling `api.get`/`api.post` directly in pages. Use shared components/helpers from `components/`, `constants/`, `utils/` rather than duplicating.
- Settings values that belong in Django settings (e.g. `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `COINS_PER_HOUR`) should be read via `from django.conf import settings`, not `os.environ`.

## Key entry points
- `manage.py`, `config/wsgi.py`, `config/urls.py`, `config/celery.py`, `config/settings.py`
- `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/vite.config.js`
- Seed: `apps/projects/management/commands/seed_data.py`
- Ingestion: `apps/projects/ingestion/pipeline.py`, `runner.py`, `tasks.py`
- Signals: `apps/projects/signals.py` (project completion → ledger + coin hooks)
