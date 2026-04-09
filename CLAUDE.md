# CLAUDE.md

## Project
The Abby Project — Django + React app for tracking summer maker projects: time tracking, weekly timecards, payment ledger (Greenlight), non-monetary Coins economy + reward shop, skill tree (Category → Subject → Skill) with badges, and Instructables/PDF project ingestion with an AI enrichment pipeline.

## Stack
- **Backend:** Django 5.1, DRF 3.15, PostgreSQL 16, Redis 7, Celery 5.4 + Beat, Gunicorn, Python 3.12
- **Frontend:** React 19, Vite 8, Tailwind 4, Framer Motion, React Router 7
- **Deploy:** Docker Compose (db, redis, django, celery_worker, celery_beat, react/nginx); Coolify via `.deploy.yml`

## Commands
```bash
# Full stack
docker compose up --build
docker compose exec django python manage.py migrate --noinput
docker compose exec django python manage.py seed_data --noinput
docker compose exec django python manage.py createsuperuser

# Frontend (local)
cd frontend && npm run dev       # :3000 with /api proxy
npm run build
npm run lint
```

## Architecture
```
config/            Django project (settings.py, urls.py, celery.py, health.py)
apps/
  projects/        Users, Project (payment_kind: required|bounty), Milestone,
                   Notification, Instructables scraper,
                   ingestion/ Scrapy-style Item Pipeline, AI suggestions
  timecards/       TimeEntry, Timecard, ClockService, TimecardService, Celery tasks
  payments/        PaymentLedger (hourly/project_bonus/bounty_payout/...),
                   PaymentService, Greenlight CSV import
  achievements/    Subject → Skill → Badge models (17 criterion types incl.
                   subjects_completed), SkillService, BadgeService
  rewards/         CoinLedger, Reward, RewardRedemption, CoinService,
                   RewardService (parent-approved redemption flow)
  portfolio/       ProjectPhoto, ZIP export
frontend/src/
  api/client.js    Fetch wrapper with token auth
  hooks/           useAuth, useApi
  pages/           Dashboard, ProjectNew, ProjectIngest, ClockPage, Timecards,
                   Payments, Rewards, Achievements, Portfolio
  themes.js        Seasonal theme switching
```

## Auth (important)
- API uses DRF **TokenAuthentication** (not session).
- Login: `POST /api/auth/` with `{action: "login", ...}` → returns `{token}`.
- Frontend stores token in `localStorage` key `abby_auth_token`, sends `Authorization: Token <key>`.
- Django admin still uses session auth at `/admin/`.

## Gotchas
- **`VITE_API_URL` is build-time only** — baked into the React bundle via Docker `ARG`. In Coolify, set it as a BUILD variable. No trailing slash. Defaults to empty (relative URLs).
- **CSRF/proxy:** `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST=True`, and `CSRF_TRUSTED_ORIGINS` needed behind Traefik/Caddy.
- **Ingestion pipeline** (`apps/projects/ingestion/`): Scrapy-style `Pipeline` of ordered `Stage`s assembled by `default_pipeline()` in `pipeline.py` and executed from `runner.py` (which `tasks.run_ingestion_job` calls). `detect.route_source` picks the per-source ingestor (`instructables.py`, `pdf.py`, `generic_url.py`) which becomes the `ParseStage`. Default stages: `ParseStage → NormalizeStage → MarkdownStage → EnrichStage`. `IngestionItem` (alias of `IngestionResult`) carries additive `raw_html`, `markdown`, `ai_suggestions`, `pipeline_warnings` fields — `result_json` shape is additive-only so the frontend poller is unchanged. Instructables scrapes cached in Redis 24h via `fetch_cached()`. Async job tracked in `ProjectIngestionJob`.
- **AI enrichment** (`ingestion/enrich.py`): `EnrichStage` is a no-op without `ANTHROPIC_API_KEY`. When set, calls Claude Haiku with the item's markdown and writes `{category, difficulty, skill_tags, extra_materials, summary}` to `item.ai_suggestions`. Rendered as opt-in chips on the `ProjectIngest` preview — never mutates title/description/milestones/materials automatically. Markdown conversion (`ingestion/markdown.py`) prefers `crawl4ai`, falls back to `markdownify`, then synthesizes from title+description.
- **Clock-in rules:** quiet hours 10pm–7am; max 8h single entry; auto clock-out via Celery every 30 min; >4h flagged for review. DB constraint: one active `TimeEntry` per user.
- **Weekly timecards** auto-generated Sunday midnight via Celery Beat; uses `project.hourly_rate_override` or `user.hourly_rate`.
- **Skill tree hierarchy:** `SkillCategory → Subject → Skill → Badge`. Subjects group related Skills inside a Category (SkillTree-platform model). `Skill.subject` is nullable; a data migration backfills one "General" Subject per Category. `SkillTreeView` response includes both nested `subjects` (new) and flat `skills` (legacy) for backward compatibility.
- **XP/Badges:** clock-out distributes 10 XP/hour across project skill tags; triggers badge evaluation (17 criterion types incl. `subjects_completed`). Cross-category and cross-subject skill prerequisites supported. Badges also award rarity-scaled Coins (see below).
- **Project payment kinds:** `Project.payment_kind` is `required` (counts toward allowance) or `bounty` (up-for-grabs cash reward). On completion, the signal posts either `project_bonus` or `bounty_payout` to `PaymentLedger` — the Payments UI renders them as separate breakdown tiles.
- **Coins economy** (`apps/rewards/`): non-monetary progression currency parallel to `PaymentLedger`. `CoinLedger` is append-only with reasons `hourly|project_bonus|bounty_bonus|milestone_bonus|badge_bonus|redemption|refund|adjustment`. Earn hooks: clock-out awards `settings.COINS_PER_HOUR × hours` (default 5), project completion awards flat×difficulty (bounty pays 2.5×), badge earn awards `settings.COINS_PER_BADGE_RARITY[rarity]`. Spend happens through `RewardService.request_redemption`, which deducts coins immediately into a "held" debit tied to the `RewardRedemption` row.
- **Reward shop** (`apps/rewards/`): Parent-approved redemption flow mirroring timecard approval. Child requests a `Reward` → `RewardRedemption` status `pending` + coins held → parent approves (`fulfilled`) or denies (refund via `CoinLedger.Reason.REFUND`, stock restored). Rewards have rarity tiers and optional stock. Routes: `/api/rewards/`, `/api/rewards/{id}/redeem/`, `/api/redemptions/` with `approve`/`deny` actions, `/api/coins/` for balance + recent ledger. Frontend page: `/rewards`. Parent approval queue rendered inline.
- **Email:** console backend in dev.
- **Timezone:** America/Phoenix.

## Env vars (see `.env.example`)
`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `VITE_API_URL` (build-time), `PARENT_PASSWORD`, `CHILD_PASSWORD`, `ANTHROPIC_API_KEY` (optional — enables Claude-based project suggestions AND the ingestion `EnrichStage`).

### Tunable settings (`config/settings.py`)
- `COINS_PER_HOUR` (default `5`) — coins awarded per clock-out hour.
- `COINS_PER_BADGE_RARITY` — per-rarity coin bonus map (common 5 → legendary 150).

## Key entry points
- `manage.py`, `config/wsgi.py`, `config/urls.py`, `config/celery.py`
- `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/vite.config.js`
- Seed: `apps/projects/management/commands/seed_data.py`
