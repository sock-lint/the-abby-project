# CLAUDE.md

## Project
SummerForge — Django + React app for tracking summer maker projects: time tracking, weekly timecards, payment ledger (Greenlight), skill tree/badges, and Instructables/PDF project ingestion.

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
  projects/        Users, Project, Milestone, Notification, Skill, Badge,
                   Instructables scraper, ingestion/ pipeline, AI suggestions
  timecards/       TimeEntry, Timecard, ClockService, TimecardService, Celery tasks
  payments/        PaymentLedger, PaymentService, Greenlight CSV import
  achievements/    Skill/Badge models, SkillService, BadgeService
  portfolio/       ProjectPhoto, ZIP export
frontend/src/
  api/client.js    Fetch wrapper with token auth
  hooks/           useAuth, useApi
  pages/           Dashboard, ProjectNew, ProjectIngest, ClockPage, Timecards,
                   Payments, Achievements, Portfolio
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
- **Ingestion pipeline** (`apps/projects/ingestion/`): `detect.py` auto-routes URL/PDF to `instructables.py`, `pdf.py`, or `generic_url.py`. Instructables scrapes cached in Redis 24h. Async job tracked in `ProjectIngestionJob`.
- **Clock-in rules:** quiet hours 10pm–7am; max 8h single entry; auto clock-out via Celery every 30 min; >4h flagged for review. DB constraint: one active `TimeEntry` per user.
- **Weekly timecards** auto-generated Sunday midnight via Celery Beat; uses `project.hourly_rate_override` or `user.hourly_rate`.
- **XP/Badges:** clock-out distributes 10 XP/hour across project skill tags; triggers badge evaluation (16 criterion types). Cross-category skill prerequisites supported.
- **Email:** console backend in dev.
- **Timezone:** America/Phoenix.

## Env vars (see `.env.example`)
`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `VITE_API_URL` (build-time), `PARENT_PASSWORD`, `CHILD_PASSWORD`, `ANTHROPIC_API_KEY` (optional — enables Claude-based suggestions).

## Key entry points
- `manage.py`, `config/wsgi.py`, `config/urls.py`, `config/celery.py`
- `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/vite.config.js`
- Seed: `apps/projects/management/commands/seed_data.py`
