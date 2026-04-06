# SummerForge

A project management, timecard, and payment tracking system for summer maker projects. Ties Instructables project guides to tracked work hours and earnings, paid out via Greenlight.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.1 + Django REST Framework |
| Frontend | React 18 (Vite) + Tailwind CSS + Framer Motion |
| Database | PostgreSQL 16 |
| Cache/Broker | Redis 7 |
| Task Queue | Celery (with django-celery-beat) |
| Reverse Proxy | Nginx |
| Containerization | Docker Compose |

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your values

# Start all services
docker compose up --build

# In another terminal, run migrations and seed data
docker compose exec django python manage.py migrate
docker compose exec django python manage.py seed_data --noinput

# Create a superuser (optional)
docker compose exec django python manage.py createsuperuser
```

The app will be available at:
- **Frontend**: http://localhost/ (via nginx) or http://localhost:3000/ (Vite dev)
- **API**: http://localhost/api/
- **Admin**: http://localhost/admin/
- **Django direct**: http://localhost:8000/

## Default Accounts (from seed data)

| Username | Password | Role |
|----------|----------|------|
| `dad` | `summerforge2025` | Parent |
| `abby` | `summerforge2025` | Child |

Passwords are configurable via `PARENT_PASSWORD` and `CHILD_PASSWORD` env vars.

## Project Structure

```
the-abby-project/
├── config/                  # Django project settings, URLs, WSGI/ASGI, Celery
├── apps/
│   ├── projects/            # User, SkillCategory, Project, Milestone, MaterialItem, Notification
│   │   ├── scraper.py       # Instructables URL preview scraper
│   │   ├── suggestions.py   # AI project suggestions (Claude API + fallback)
│   │   ├── notifications.py # Notification helper
│   │   └── signals.py       # Status change, milestone, and notification triggers
│   ├── timecards/           # TimeEntry, Timecard, ClockService, TimecardService
│   │   ├── export.py        # CSV export for timecards and time entries
│   │   └── tasks.py         # Celery tasks (auto clock-out, weekly timecards, email summaries)
│   ├── payments/            # PaymentLedger, PaymentService
│   ├── achievements/        # Skill tree, Badges, SkillService, BadgeService
│   └── portfolio/           # ProjectPhoto, ZIP export
├── frontend/                # React 18 + Vite + Tailwind CSS frontend
│   ├── src/
│   │   ├── api/             # API client and endpoint functions
│   │   ├── components/      # Layout, Card, StatusBadge, Loader, NotificationBell
│   │   ├── hooks/           # useApi, useAuth
│   │   └── pages/           # Dashboard, Projects, Clock, Timecards, Payments, Achievements, Portfolio, Settings, Login
│   └── Dockerfile
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
└── requirements.txt
```

## Data Models

### Core Models

- **User** — Custom auth user with `parent`/`child` roles, hourly rate, avatar
- **SkillCategory** — Woodworking, Electronics, Cooking, Art & Crafts, Coding, Outdoors, Sewing & Textiles, Science
- **Project** — Assigned work with status workflow (draft -> active -> in_progress -> in_review -> completed -> archived), difficulty, bonuses, materials budget
- **ProjectMilestone** — Ordered subtasks within a project, each with optional bonus
- **MaterialItem** — Tracked materials with estimated/actual costs and receipt photos
- **Notification** — In-app notifications (8 types: timecard_ready, timecard_approved, badge_earned, project_approved, project_changes, payout_recorded, skill_unlocked, milestone_completed)

### Time & Pay

- **TimeEntry** — Clock in/out records with a DB constraint ensuring one active entry per user
- **Timecard** — Weekly aggregation of time entries with hourly + bonus earnings
- **PaymentLedger** — Full financial ledger (hourly, project_bonus, milestone_bonus, materials_reimbursement, payout, adjustment)

### Skill Tree

- **Skill** — ~50 specific skills (e.g., "Through-Hole Soldering") within categories, with level names and lock/unlock mechanics
- **SkillPrerequisite** — Prerequisites between skills (including cross-category, e.g., Building & Construction requires Woodworking's Measuring & Marking)
- **SkillProgress** — Per-user, per-skill XP and level tracking
- **ProjectSkillTag** / **MilestoneSkillTag** — Tag projects/milestones with skills and XP weights

### Achievements

- **Badge** — 35+ badges with 16 criteria types and 5 rarity levels (common -> legendary)
- **UserBadge** — Earned badges per user

### XP / Level Thresholds

| Level | XP Required | Title |
|-------|------------|-------|
| 0 | 0 | Not Started |
| 1 | 100 | Beginner |
| 2 | 300 | Apprentice |
| 3 | 600 | Journeyman |
| 4 | 1000 | Craftsman |
| 5 | 1500 | Expert |
| 6 | 2500 | Master |

XP is earned through hours worked (10 XP/hr), project completion (50 x difficulty), milestone completion (15 XP), and badge bonuses. XP is distributed across tagged skills by weight.

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/` | Login (`{"action": "login", "username": "...", "password": "..."}`) or logout (`{"action": "logout"}`) |
| GET | `/api/auth/me/` | Current user info |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/` | Role-aware summary: active timer, balance, weekly stats, projects, badges, streak |

### Projects
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/projects/` | List / create projects |
| GET/PATCH/DELETE | `/api/projects/{id}/` | Project detail |
| POST | `/api/projects/{id}/submit/` | Child submits for review |
| POST | `/api/projects/{id}/approve/` | Parent approves (-> completed) |
| POST | `/api/projects/{id}/request-changes/` | Parent sends back |
| GET/POST | `/api/projects/{id}/milestones/` | List / create milestones |
| POST | `/api/projects/{id}/milestones/{id}/complete/` | Mark milestone complete |
| GET/POST | `/api/projects/{id}/materials/` | List / create materials |
| POST | `/api/projects/{id}/materials/{id}/mark-purchased/` | Mark material purchased |

### Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notifications/` | List all notifications |
| GET | `/api/notifications/unread_count/` | Unread notification count |
| POST | `/api/notifications/mark_all_read/` | Mark all as read |
| POST | `/api/notifications/{id}/mark_read/` | Mark one as read |

### Time Tracking
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/clock/` | Current active timer status |
| POST | `/api/clock/` | Clock in (`{"action": "in", "project_id": 1}`) or out (`{"action": "out", "notes": "..."}`) |
| GET | `/api/time-entries/` | List time entries |
| POST | `/api/time-entries/{id}/void/` | Parent voids an entry |

### Timecards
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/timecards/` | List weekly timecards |
| GET | `/api/timecards/{id}/` | Detail with entries |
| POST | `/api/timecards/{id}/approve/` | Parent approves |
| POST | `/api/timecards/{id}/dispute/` | Either role disputes |
| POST | `/api/timecards/{id}/mark-paid/` | Parent marks as paid |

### Payments
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/balance/` | Current balance + breakdown |
| GET | `/api/payments/` | Full ledger |
| POST | `/api/payments/payout/` | Parent records Greenlight payout |

### Achievements
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/badges/` | All available badges |
| GET | `/api/badges/earned/` | User's earned badges |
| GET | `/api/skills/` | All skills |
| GET | `/api/skills/tree/{category_id}/` | Skill tree for a category with user progress |
| GET | `/api/skill-progress/` | User's skill progress |
| GET | `/api/achievements/summary/` | Combined badges + skills overview |

### Portfolio
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/photos/` | List / upload photos |
| GET | `/api/portfolio/` | Photos grouped by project |

### Instructables
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/instructables/preview/?url=...` | Scrape Instructables URL for title, thumbnail, steps (cached 24h in Redis) |

### Data Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/export/timecards/` | Download timecards as CSV |
| GET | `/api/export/time-entries/` | Download time entries as CSV |
| GET | `/api/export/portfolio/` | Download all project photos as ZIP |

## Business Logic

### Clock In/Out
- One active clock-in at a time (enforced by DB constraint)
- Quiet hours: 10 PM - 7 AM (no clock-in allowed)
- Auto clock-out after 8 hours (Celery task, runs every 30 min)
- Entries > 4 hours flagged for parent review

### Weekly Timecards
- Auto-generated every Sunday at midnight via Celery Beat
- Calculates hourly earnings per project (hours x rate, respecting per-project rate overrides)
- Includes any bonuses earned that week
- Parent approval workflow: pending -> approved -> paid

### Pay Calculation
```
hourly_rate = project.hourly_rate_override or user.hourly_rate  # default $8/hr
hourly_earnings = total_hours * hourly_rate
bonus = project.bonus_amount (on completion)
balance = sum(all ledger entries)  # positive = owed, negative = paid out
```

### Skill Tree & XP
- Projects are tagged with skills and XP weights
- On clock-out: time-based XP distributed across project's skill tags by weight
- On milestone completion: XP from milestone skill tags (or fallback to project tags)
- On project completion: difficulty-based XP distributed across skill tags
- Locked skills unlock when all prerequisites are met
- Cross-category prerequisites create interesting progression paths

### Badge Evaluation
Triggered on: project completion, milestone completion, clock-out, timecard approval. Checks all unearned badges against current stats.

### Notifications
Auto-created via Django signals on:
- Project approved / changes requested
- Milestone completed
- Badge earned
- Payout recorded

Frontend polls for unread count every 30 seconds. Bell icon in the top bar shows unread badge with dropdown panel.

### Weekly Email Summary
Celery task (`send_weekly_email_summaries`) sends:
- **Child**: hours worked, badges earned, current balance
- **Parent**: per-child activity summary, pending timecard count

Uses console email backend in development.

### Instructables Integration
When creating a project, pasting an Instructables URL triggers a backend scraper that extracts:
- Title, author, thumbnail URL, step count, category
- Results cached in Redis for 24 hours
- Frontend shows a live preview card with the extracted metadata

## v2 Features

### Project Templates
- Save any completed project as a reusable template (with milestones and materials)
- Create new projects from templates with one click
- Public templates enable parent co-op sharing between families
- API: `GET /api/templates/`, `POST /api/templates/from-project/`, `POST /api/templates/{id}/create-project/`, `GET /api/templates/shared/`

### Collaborative Projects
- Add multiple children to a project with configurable pay split percentages
- `ProjectCollaborator` model tracks per-child participation
- API: `GET/POST /api/projects/{id}/collaborators/`

### Savings Goals
- Children set savings targets (e.g., "New bike - $200") with custom icons
- Progress bar on dashboard auto-updates from current balance
- Completion tracking with timestamps
- API: `GET/POST /api/savings-goals/`, `POST /api/savings-goals/{id}/update_amount/`

### AI Project Suggestions
- Claude API (Haiku) analyzes completed projects and skill levels to recommend next projects
- Considers skill gaps, category breadth, and difficulty progression
- Curated fallback suggestions when `ANTHROPIC_API_KEY` is not set
- Frontend: suggestions section on Projects page with category tags and rationale
- API: `GET /api/projects/suggestions/`

### QR Code Clock-In
- Generate printable QR codes for each project (amber on black, workshop themed)
- Scan with phone camera to quick-clock-in from the workshop
- QR data includes project ID and title as JSON
- API: `GET /api/projects/{id}/qr/` returns PNG image

### Time-Lapse Integration
- `video_url` field on ProjectPhoto supports YouTube/external video links
- `is_timelapse` flag for marking time-lapse recordings
- Encourages capturing the making process on camera

### Seasonal Themes
- 4 color themes: Summer (amber), Winter Break (blue), Spring Break (green), Autumn (orange)
- Theme preference saved per-user on the backend
- CSS custom properties swapped at runtime for instant switching
- Theme picker with color swatches on Settings page

### Greenlight CSV Import
- Import Greenlight transaction CSV data for payout reconciliation
- Parses Amount and Description columns, creates payout ledger entries
- API: `POST /api/greenlight/import/` with `user_id` and `csv_data`

### Parent Co-Op Mode
- Public project templates shared between families
- Browse community templates via `GET /api/templates/shared/`
- One-click create project from any shared template

## Frontend

### Design
- Dark mode workshop aesthetic with seasonal theme switching
- Space Mono for headings/numbers, DM Sans for body text
- Framer Motion micro-animations on interactions
- Mobile-first with sidebar nav (desktop) and bottom nav (mobile)

### Pages
| Page | Route | Description |
|------|-------|-------------|
| Login | -- | Session auth form |
| Dashboard | `/` | Active timer hero, balance, weekly stats, projects, badges, streak, savings goals |
| Projects | `/projects` | Card grid with status badges, progress bars, AI suggestions section |
| Project Detail | `/projects/:id` | Tabbed view with workflow actions, QR code, save-as-template |
| New Project | `/projects/new` | Create form with Instructables URL preview (parent only) |
| Clock | `/clock` | Large circular timer, project selector, one-tap clock in/out |
| Timecards | `/timecards` | Weekly cards, expandable detail, approve/dispute/pay, CSV export |
| Payments | `/payments` | Large balance, breakdown by type, transaction history |
| Achievements | `/achievements` | Badge collection grid + interactive skill tree by category |
| Portfolio | `/portfolio` | Photo + video gallery grouped by project, ZIP download |
| Settings | `/settings` | Profile info, theme picker (4 seasonal themes) |

## Development

```bash
# Start all services
docker compose up

# Tail Django logs
docker compose logs -f django

# Frontend only (with API proxy to Django)
cd frontend && npm run dev

# Django shell
docker compose exec django python manage.py shell_plus

# Reset everything
docker compose down -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (insecure dev key) | Django secret key |
| `DEBUG` | `True` | Debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `DATABASE_URL` | `postgres://summerforge:summerforge@db:5432/summerforge` | Database connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis cache URL |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery broker URL |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:3000` | CORS origins |
| `PARENT_PASSWORD` | `summerforge2025` | Seed data parent password |
| `CHILD_PASSWORD` | `summerforge2025` | Seed data child password |
| `ANTHROPIC_API_KEY` | (empty) | Optional — enables AI project suggestions via Claude API |
