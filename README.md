# The Abby Project

A family-focused Django + React app for managing kids' projects, chores, and homework with real-money allowance tracking, a non-monetary Coins economy with a reward shop, a skill tree with badges, AI-powered project ingestion from Instructables/PDFs, and an MCP server for Claude tool use.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.1 + Django REST Framework 3.15 |
| Frontend | React 19 (Vite 8) + Tailwind 4 + Framer Motion + `vite-plugin-pwa` |
| Database | PostgreSQL 16 |
| Cache/Broker | Redis 7 |
| Task Queue | Celery 5.4 (with django-celery-beat) |
| MCP Server | FastMCP (Streamable HTTP, mounted inside Django ASGI at `/mcp`) |
| Observability | Sentry (self-hosted) — error tracking, performance, release automation |
| Image generation | Google Gemini 3 Pro Image ("Nano Banana Pro") for runtime sprite authoring |
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
- **App** (Django + React SPA): http://localhost:8000/ — single origin via WhiteNoise
- **API**: http://localhost:8000/api/
- **MCP endpoint**: http://localhost:8000/mcp/
- **Admin**: http://localhost:8000/admin/
- **Frontend dev server** (optional): http://localhost:3000/ — Vite with `/api` proxy to :8000

## Deployment (Coolify)

Everything ships as a single image. The multi-stage `Dockerfile` builds the
React bundle with Node, then copies it into a Django image that serves both
the SPA and the API from the same origin via WhiteNoise. The MCP server is
mounted inside Django ASGI at `/mcp` — no additional container or port. The
deployable `docker-compose.yml` has `django`, `celery_worker`, `celery_beat`,
`db`, and `redis`.

TLS and routing are handled by Coolify's built-in Traefik. Point one
domain at the `django` service:

| Service | Domain | Container port |
|---|---|---|
| `django` | `abby.bos.lol` | 8000 |

Celery workers are background-only and should have no public domain.

### Required Coolify environment variables

See `.env.example` for the full list. At minimum:

- `SECRET_KEY`, `DEBUG=False`
- `ALLOWED_HOSTS=abby.bos.lol,...`
- `CSRF_TRUSTED_ORIGINS=https://abby.bos.lol`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DATABASE_URL` — URL-encode special chars in the password (`@` → `%40`, etc.)
- `REDIS_URL=redis://redis:6379/0`
- `CELERY_BROKER_URL=redis://redis:6379/1`

After a first deploy, run migrations once from the Coolify host:

```bash
docker exec <django-container> python manage.py migrate
docker exec <django-container> python manage.py seed_data --noinput  # optional
```

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
│   ├── settings.py          # Single settings module, env-driven
│   ├── urls.py              # API includes + SPA catch-all
│   ├── asgi.py              # ASGI app (MCP mounted here)
│   ├── celery.py            # Celery app factory
│   ├── base_models.py       # Abstract CreatedAtModel, TimestampedModel
│   ├── permissions.py       # Shared IsParent DRF permission
│   ├── services.py          # BaseLedgerService (PaymentService, CoinService)
│   └── viewsets.py          # RoleFilteredQuerySetMixin, NestedProjectResourceMixin
├── apps/
│   ├── accounts/            # Custom User (parent/child role, AUTH_USER_MODEL), avatars
│   ├── projects/            # Project, Milestone, Step, Resource, MaterialItem,
│   │   │                    #   ProjectTemplate, SavingsGoal, Collaborator,
│   │   │                    #   priority.py (next-action scorer for the dashboard feed)
│   │   ├── scraper.py       # Instructables URL preview
│   │   ├── suggestions.py   # AI project suggestions (Claude API + fallback)
│   │   └── signals.py       # Status change, milestone, and notification triggers
│   ├── notifications/       # Notification model + NotificationType, notify() helpers
│   ├── ingestion/           # Scrapy-style pipeline (parse → normalize → markdown → enrich)
│   │                        #   + ProjectIngestionJob model + Celery task
│   ├── timecards/           # TimeEntry, Timecard, ClockService, CSV export, Celery tasks
│   ├── payments/            # PaymentLedger, PaymentService
│   ├── achievements/        # SkillCategory → Subject → Skill → Badge, SkillProgress,
│   │                        #   AwardService, BadgeService, criterion checkers
│   ├── rewards/             # CoinLedger, Reward, RewardRedemption, ExchangeRequest
│   ├── chores/              # Chore (recurring tasks), ChoreCompletion (submit→approve)
│   ├── homework/            # HomeworkAssignment, Submission, Proof, Template
│   ├── chronicle/           # ChronicleEntry (lifelong timeline — births, chapters,
│   │                        #   journal entries, milestones, recaps), ChronicleService
│   ├── creations/           # Creation ("I made a thing" entries — photo + audio +
│   │                        #   skill tags + parent-bonus track), CreationService
│   ├── habits/              # Habit, HabitLog, HabitService (positive/negative taps,
│   │                        #   strength color bar, daily decay)
│   ├── portfolio/           # ProjectPhoto, ZIP export
│   ├── rpg/                 # CharacterProfile, ItemDefinition, UserInventory, DropTable,
│   │                        #   DropLog, SpriteAsset (runtime-authored sprites);
│   │                        #   StreakService, DropService, CosmeticService,
│   │                        #   ConsumableService, GameLoopService (orchestrator),
│   │                        #   sprite_generation.py (Gemini-backed sprite-sheet maker)
│   ├── pets/                # PetSpecies, PotionType, UserPet, UserMount, PetService
│   │                        #   (hatch, feed, evolve, breed mounts, happiness)
│   ├── quests/              # QuestDefinition, Quest, QuestParticipant, QuestRewardItem,
│   │                        #   QuestService, DailyChallenge (one-per-day micro-quests)
│   ├── google_integration/  # OAuth2, GoogleAccount, CalendarEventMapping
│   ├── activity/            # Cross-app activity feed
│   ├── movement/            # Step counts / wearable integration scaffolding
│   ├── lorebook/            # Static mechanics explainer API backed by
│   │                        #   content/lorebook/entries.yaml
│   └── mcp_server/          # FastMCP server with 14+ tool modules
├── content/
│   ├── lorebook/            # Dual-audience mechanics explainer entries
│   └── rpg/                 # YAML-authored RPG catalog and content packs
├── frontend/                # React 19 + Vite 8 + Tailwind 4 frontend
│   └── src/
│       ├── api/             # API client and endpoint functions
│       ├── components/      # Primitives (Button, IconButton, Form fields, BottomSheet,
│       │                    #   ConfirmDialog, Loader, ProgressBar, NotificationBell, …)
│       ├── pwa/             # vite-plugin-pwa providers + UpdateBanner + InstallCard +
│       │                    #   OfflineReadyToast (see CLAUDE.md PWA gotcha)
│       ├── providers/       # SpriteCatalogProvider (runtime sprite catalog + ETag cache)
│       ├── hooks/           # useApi, useAuth, useParentDashboard, useDropToasts, …
│       └── pages/           # Dashboard router (Child/ParentDashboard), QuestsHub,
│                            #   AtlasHub (Skills/Badges/Sketchbook/Yearbook), BestiaryHub
│                            #   (Inventory/Stable), TreasuryHub (Payments/Timecards/
│                            #   Rewards), Atlas Lorebook mechanics guide,
│                            #   Trials, Character (Sigil Frontispiece),
│                            #   ClockPage, Manage, SettingsPage, Login, …
├── Dockerfile               # Multi-stage: Node build → Python + Django + WhiteNoise
├── docker-compose.yml       # db, redis, django, celery_worker, celery_beat
└── requirements.txt
```

## Data Models

### Core Models

- **User** — Custom auth user with `parent`/`child` roles, hourly rate, avatar, theme
- **SkillCategory** — Top-level groupings (Woodworking, Electronics, Cooking, etc.)
- **Project** — Assigned work with status workflow (draft → active → in_progress → in_review → completed → archived), difficulty (1-5), payment kind (`required` or `bounty`)
- **ProjectMilestone** — Ordered "chapters" within a project (parent-authored, optional `bonus_amount` → PaymentLedger). Completion is parent-controlled.
- **ProjectStep** — Ordered walkthrough instructions inside a project, optionally grouped under a `ProjectMilestone` via nullable FK. Steps never award XP, coins, or money.
- **ProjectResource** — Reference link (video / doc / image / link) attached to a project or a specific step
- **MaterialItem** — Tracked materials with estimated/actual costs and receipt photos
- **ProjectTemplate** — Reusable templates created from completed projects (with milestones + materials)
- **ProjectCollaborator** — Additional child on a project with configurable `pay_split_percent`
- **SavingsGoal** — Child-set targets with `target_amount` / `current_amount` and progress tracking
- **ProjectIngestionJob** — Async job for importing projects from URLs or PDFs via AI pipeline
- **Notification** — In-app notifications. Types include the approval/workflow set (timecard_ready/approved, project_approved/changes, payout_recorded, redemption_requested, chore_submitted/approved, exchange_requested/approved/denied, homework_created/submitted/approved/rejected), reminder set (project_due_soon, chore_reminder, approval_reminder, homework_due_soon), and the engagement set (badge_earned, skill_unlocked, milestone_completed, streak_milestone, perfect_day, daily_check_in).

### Time & Pay

- **TimeEntry** — Clock in/out records with a DB constraint ensuring one active entry per user. Supports `voided` status.
- **Timecard** — Weekly aggregation of time entries with hourly + bonus earnings and approval workflow
- **PaymentLedger** — Append-only financial ledger with 9 entry types: hourly, project_bonus, bounty_payout, milestone_bonus, materials_reimbursement, payout, adjustment, chore_reward, coin_exchange

### Skill Tree

- **Subject** — Intermediate grouping between SkillCategory and Skill (e.g., "Soldering" under "Electronics")
- **Skill** — Specific skills with level names and lock/unlock mechanics
- **SkillPrerequisite** — Prerequisites between skills (including cross-category)
- **SkillProgress** — Per-user, per-skill XP and level tracking
- **ProjectSkillTag** / **MilestoneSkillTag** / **HomeworkSkillTag** — Tag projects, milestones, and homework with skills and XP weights

### Achievements

- **Badge** — 170+ badges (`content/rpg/initial/badges.yaml`) with 48 criterion types and 5 rarity levels (common → legendary). Criterion families: time (`hours_worked`, `days_worked`, `early_bird`, `late_night`), projects/milestones (`projects_completed`, `co_op_project_completed`, `bounty_completed`), skills (`skill_level_reached`, `category_mastery`, `subjects_completed`), economy (`total_earned`, `total_coins_earned`, `savings_goal_completed`), homework (`homework_planned_ahead`, `homework_on_time_count`), creations (`creations_logged`, `creations_approved`, `creation_skill_breadth`), RPG progression (`streak_days`, `perfect_days_count`, `streak_freeze_used`, `pets_hatched`, `mounts_evolved`, `quest_completed`), journal (`journal_entries_written`, `journal_streak_days`), and meta (`badges_earned_count`, `cosmetic_set_owned`, `chronicle_milestones_logged`, `grade_reached`, `birthdays_logged`).
- **UserBadge** — Earned badges per user.

### Rewards / Coins

- **CoinLedger** — Append-only non-monetary currency ledger with 10 reason types: hourly, project_bonus, bounty_bonus, milestone_bonus, badge_bonus, redemption, refund, adjustment, chore_reward, exchange
- **Reward** — Items/privileges in the reward shop with rarity, coin cost, optional stock limits, and optional parent approval
- **RewardRedemption** — Submit-then-approve workflow: coins held at request, refunded on denial, consumed on fulfillment
- **ExchangeRequest** — Money-to-coins conversion at `COINS_PER_DOLLAR` rate (default 10) with parent approval. Balance re-verified at approval time.

### Chores

- **Chore** — Recurring household tasks (daily / weekly / one_time) with money + coin rewards. Supports shared-custody alternating-week schedules via `week_schedule` and ISO week parity.
- **ChoreCompletion** — Submit-then-approve workflow. Reward values snapshotted at submission. `UniqueConstraint` prevents duplicate completions per chore per day.

### Homework

Homework pays **no money and no coins** — it's positioned as school duty, not work-for-hire. Rewards come from XP, RPG drops, streaks, and quest progress.

- **HomeworkAssignment** — School assignments with subject, effort level (1-5, XP-weighting hint only), due date. Both parents and children can create assignments. Creating fires a `homework_created` RPG trigger (streak + quests + one drop roll per day).
- **HomeworkSubmission** — Submit-then-approve with a `Timeliness` label (early / on_time / late / beyond_cutoff) recorded for badge + quest gating. No reward snapshot.
- **HomeworkProof** — Required image uploads with captions and ordering.
- **HomeworkTemplate** — Reusable assignment configs with skill tag presets.
- **HomeworkSkillTag** — XP awarded on approval, triggering badge evaluation (incl. `HOMEWORK_PLANNED_AHEAD` / `HOMEWORK_ON_TIME_COUNT` Scholar badges).

### RPG: Character, Habits, Drops, Cosmetics (`apps/rpg/`)

- **CharacterProfile** — Auto-created OneToOne with User. Tracks `level`, `login_streak`, `longest_login_streak`, `last_active_date`, `perfect_days_count`, `streak_freeze_expires_at` (one-shot grace set by consuming a Streak Freeze), and 4 cosmetic equip slots (`active_frame`, `active_title`, `active_theme`, `active_pet_accessory`) with type-constrained FKs to `ItemDefinition`.
- **Habit / HabitLog** — Micro-behaviors with `+/-` taps (positive / negative / both). Tracks `strength` (decays daily if untapped). No approval flow — self-reported.
- **ItemDefinition** — Master catalog. 10 item types (egg, potion, food, cosmetic_frame, cosmetic_title, cosmetic_theme, cosmetic_pet_accessory, quest_scroll, coin_pouch, consumable), 5 rarities (common → legendary), `coin_value` (salvage value), `metadata` JSONField for type-specific data. `consumable` items fire a one-shot effect on use (dispatched by `ConsumableService._apply_effect` keyed by `metadata.effect`) — currently `streak_freeze`.
- **UserInventory** — Per-user item quantities with `unique_together=(user, item)`.
- **DropTable** — Trigger → Item mapping with `weight` and `min_level`. Triggers: clock_out, chore_complete, homework_complete, homework_created, milestone_complete, badge_earned, quest_complete, perfect_day, habit_log.
- **DropLog** — Audit trail with `was_salvaged` flag (duplicate cosmetics auto-convert to coins).

### RPG: Pets & Mounts (`apps/pets/`)

- **PetSpecies** — Base creature (17 species shipped — original 8 plus dragon, fox, owl, cat, bear, phoenix, unicorn, koi, companion, etc.) with `food_preference` FK and `available_potions` M2M for valid hatch combos.
- **PotionType** — Variant modifier (Base, Fire, Ice, Shadow, Golden, Cosmic) with rarity and color. 17 species × 6 potions = up to 102 hatchable combinations.
- **UserPet** — `unique_together=(user, species, potion)`. Tracks `growth_points` (0-100), `is_active`, `evolved_to_mount`, `last_fed_at` (drives the visual happiness state), and `consumable_growth_today` / `consumable_growth_date` (per-day cap on direct-grant growth from `growth_surge` / `feast_platter` consumables — see `CONSUMABLE_GROWTH_DAILY_CAP` in pet services).
- **UserMount** — Evolved form created at 100 growth. Tracks `last_bred_at` for the breeding cooldown (`MOUNT_BREEDING_COOLDOWN_DAYS=7`).

### Chronicle, Creations, Daily Challenges, Sprites

- **ChronicleEntry** (`apps/chronicle/`) — Lifelong timeline rendered on the Yearbook page. Kinds: `birthday`, `chapter_start`, `chapter_end`, `first_ever`, `milestone`, `recap`, `manual`, `journal` (child-authored, one per local day, `is_private=True`), `creation` (auto-emitted from Creations).
- **Creation** (`apps/creations/`) — Child-authored "I made a thing" entries — required photo + optional audio + caption + child-picked primary/secondary creative skill. Anti-farm: `CreationDailyCounter` caps XP rewards to the first 2 logs per local day and survives hard deletes. Parent bonus track via `CreationBonusSkillTag`.
- **DailyChallenge** (`apps/quests/`) — Lightweight once-per-day micro-quest separate from the regular `Quest` slot. Five challenge types (`clock_hour`, `chores`, `habits`, `homework`, `milestone`); rotated nightly by `rotate_daily_challenges_task` Celery beat.
- **SpriteAsset** (`apps/rpg/`) — Runtime-authored pixel-art sprites with slug, ImageField, animation metadata (`frame_count`, `fps`, layout) and authoring inputs (`prompt`, `motion`, `style_hint`, `tile_size`, `reference_image_url`) persisted for one-click reroll. Served from a dedicated `abby-sprites` Ceph bucket (public-read, content-hash filenames, immutable cache headers). Generation backed by Google Gemini 3 Pro Image via `apps/rpg/sprite_generation.py`.

### RPG: Quests (`apps/quests/`)

- **QuestDefinition** — Template: `quest_type` (boss / collection), `target_value` (HP or item count), `duration_days`, `trigger_filter` JSONField (allowed_triggers, project_id, skill_category_id, chore_ids, etc.), optional `required_badge` FK, `coin_reward` / `xp_reward`, `is_system` / `is_repeatable`.
- **QuestRewardItem** — M2M link from `QuestDefinition` to `ItemDefinition` with `quantity`.
- **Quest** — Active instance. Status (active / completed / failed / expired), `current_progress`, `rage_shield` (boss-only), `start_date` / `end_date`.
- **QuestParticipant** — Per-user contribution. Multi-player-ready (solo in current UI).

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

XP is earned through hours worked (10 XP/hr), project completion (50 x difficulty), milestone completion (15 XP), homework approval (per skill tag), and badge bonuses. XP is distributed across tagged skills by weight.

## API Endpoints

### Auth

Authentication uses DRF **TokenAuthentication**. Login returns a token which
the frontend stores in `localStorage` and sends on every request as:

```
Authorization: Token <key>
```

If any API call returns `401` on a request that carried an `Authorization`
header, the frontend fetch wrapper clears the stored token and reloads the
page. This self-heal routes the user back to the Login screen automatically
when a stored token has gone stale, rather than leaving the SPA stuck sending
an invalid header. Login attempts and anonymous requests (no `Authorization`
header sent) are exempt — they surface the 401 as a normal error.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/` | Login (`{"action": "login", "username": "...", "password": "..."}`) — returns `{...user, "token": "<key>"}`. Logout (`{"action": "logout"}`) — revokes the caller's token. |
| GET | `/api/auth/me/` | Current user info (requires `Authorization: Token <key>`) |

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
| POST | `/api/projects/{id}/approve/` | Parent approves (→ completed) |
| POST | `/api/projects/{id}/request-changes/` | Parent sends back |
| GET/POST | `/api/projects/{id}/milestones/` | List / create milestones |
| GET/PATCH/DELETE | `/api/projects/{id}/milestones/{id}/` | Milestone detail |
| POST | `/api/projects/{id}/milestones/{id}/complete/` | Mark milestone complete (posts `milestone_bonus` to PaymentLedger) |
| GET/POST | `/api/projects/{id}/steps/` | List / create walkthrough steps |
| GET/PATCH/DELETE | `/api/projects/{id}/steps/{id}/` | Step detail |
| POST | `/api/projects/{id}/steps/{id}/complete/` | Mark step complete (no payout) |
| POST | `/api/projects/{id}/steps/{id}/uncomplete/` | Reopen a completed step |
| POST | `/api/projects/{id}/steps/reorder/` | Atomically renumber steps |
| GET/POST | `/api/projects/{id}/resources/` | List / create reference links (project- or step-scoped) |
| GET/PATCH/DELETE | `/api/projects/{id}/resources/{id}/` | Resource detail |
| GET/POST | `/api/projects/{id}/materials/` | List / create materials |
| GET/PATCH/DELETE | `/api/projects/{id}/materials/{id}/` | Material detail |
| POST | `/api/projects/{id}/materials/{id}/mark-purchased/` | Mark material purchased |
| GET/POST | `/api/projects/{id}/collaborators/` | List / add collaborators |
| DELETE | `/api/projects/{id}/collaborators/{id}/` | Remove collaborator |
| GET | `/api/projects/{id}/qr/` | QR code PNG for quick clock-in |
| GET | `/api/projects/suggestions/` | AI project suggestions (Claude API + fallback) |

### Ingestion
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects/ingest/` | Start ingestion job from URL or PDF upload |
| GET | `/api/projects/ingest/{uuid}/` | Poll job status + preview data |
| POST | `/api/projects/ingest/{uuid}/commit/` | Commit staged project |

### Templates
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/templates/` | List templates |
| GET | `/api/templates/{id}/` | Template detail |
| POST | `/api/templates/from-project/` | Save completed project as template |
| POST | `/api/templates/{id}/create-project/` | Create new project from template |
| GET | `/api/templates/shared/` | Browse public templates |

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
| GET/POST | `/api/clock/` | Clock in (`{"action": "in", "project_id": 1}`) or out (`{"action": "out", "notes": "..."}`) |
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
| POST | `/api/payments/adjust/` | Parent adjusts payment ledger |

### Coins & Rewards
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/coins/` | Coin balance + recent ledger |
| POST | `/api/coins/adjust/` | Parent adjusts coin balance |
| POST | `/api/coins/exchange/` | Child requests money→coins exchange |
| GET | `/api/coins/exchange/rate/` | Current exchange rate |
| GET | `/api/coins/exchange/list/` | Exchange request history (role-filtered) |
| POST | `/api/coins/exchange/{id}/approve/` | Parent approves exchange |
| POST | `/api/coins/exchange/{id}/reject/` | Parent rejects exchange |
| GET/POST | `/api/rewards/` | List / create rewards (parent CRUD) |
| GET/PATCH/DELETE | `/api/rewards/{id}/` | Reward detail |
| POST | `/api/rewards/{id}/redeem/` | Child requests redemption |
| GET | `/api/redemptions/` | List redemptions (role-filtered) |
| POST | `/api/redemptions/{id}/approve/` | Parent approves redemption |
| POST | `/api/redemptions/{id}/reject/` | Parent rejects redemption |

### Chores
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/chores/` | List / create chores (parent CRUD) |
| GET/PATCH/DELETE | `/api/chores/{id}/` | Chore detail |
| POST | `/api/chores/{id}/complete/` | Child submits completion |
| GET | `/api/chore-completions/` | List completions (role-filtered) |
| POST | `/api/chore-completions/{id}/approve/` | Parent approves |
| POST | `/api/chore-completions/{id}/reject/` | Parent rejects |

### Homework
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/homework/` | List / create assignments |
| GET/PATCH/DELETE | `/api/homework/{id}/` | Assignment detail |
| POST | `/api/homework/{id}/submit/` | Submit with proof images |
| POST | `/api/homework/{id}/save-template/` | Save as reusable template |
| POST | `/api/homework/{id}/plan/` | Trigger AI planning (creates linked Project) |
| GET | `/api/homework/dashboard/` | Role-aware dashboard (today/upcoming/overdue/stats) |
| GET | `/api/homework-submissions/` | List submissions (role-filtered) |
| POST | `/api/homework-submissions/{id}/approve/` | Parent approves |
| POST | `/api/homework-submissions/{id}/reject/` | Parent rejects |
| GET/POST | `/api/homework-templates/` | List / create templates |
| GET/PATCH/DELETE | `/api/homework-templates/{id}/` | Template detail |
| POST | `/api/homework-templates/{id}/create-assignment/` | Create assignment from template |

### Achievements
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/badges/` | All available badges |
| GET | `/api/badges/earned/` | User's earned badges |
| GET | `/api/subjects/` | All subjects |
| GET | `/api/skills/` | All skills |
| GET | `/api/skills/tree/{category_id}/` | Skill tree for a category with user progress |
| GET | `/api/skill-progress/` | User's skill progress |
| GET | `/api/achievements/summary/` | Combined badges + skills overview |

### Portfolio
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/photos/` | List / upload photos |
| GET | `/api/portfolio/` | Photos grouped by project (includes homework proofs) |

### Children / Manage
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/children/` | List child users (parent only) |
| GET/PATCH | `/api/children/{id}/` | Child detail — edit hourly rate |
| GET/POST | `/api/categories/` | List / create skill categories |
| GET/PATCH/DELETE | `/api/categories/{id}/` | Category detail |
| GET/POST | `/api/subjects/` | List / create subjects |
| GET/PATCH/DELETE | `/api/subjects/{id}/` | Subject detail |
| GET/POST | `/api/savings-goals/` | List / create savings goals |
| POST | `/api/savings-goals/{id}/update_amount/` | Update goal progress |

### Google Calendar
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/google/` | Initiate OAuth2 flow (returns auth URL) |
| POST | `/api/auth/google/login/` | Exchange auth code for tokens |
| GET | `/api/auth/google/callback/` | OAuth2 callback handler |
| GET/DELETE | `/api/auth/google/account/` | View / unlink Google account |
| GET/PATCH | `/api/auth/google/calendar/` | Calendar sync settings |
| POST | `/api/auth/google/calendar/sync/` | Trigger manual calendar sync |

### Instructables
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/instructables/preview/?url=...` | Scrape Instructables URL for title, thumbnail, steps (cached 24h in Redis) |

### Greenlight
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/greenlight/import/` | Import Greenlight CSV for payout reconciliation |

### Data Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/export/timecards/` | Download timecards as CSV |
| GET | `/api/export/time-entries/` | Download time entries as CSV |
| GET | `/api/export/portfolio/` | Download all project photos as ZIP |

### RPG: Character, Streaks, Habits
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/character/` | Current user's character profile (level, streak, equipped cosmetics) |
| GET | `/api/streaks/` | Login streak, longest streak, perfect day count |
| GET | `/api/habits/` | List habits (parents see all, children see own) |
| POST | `/api/habits/` | Create habit (parents or self) |
| PATCH | `/api/habits/{id}/` | Update habit (parent-only) |
| DELETE | `/api/habits/{id}/` | Delete habit (parent-only) |
| POST | `/api/habits/{id}/log/` | Log a +1 or -1 tap on a habit |

### RPG: Inventory, Drops, Cosmetics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/inventory/` | Owned items grouped by type |
| GET | `/api/drops/recent/` | Last 10 drops for the user |
| GET | `/api/cosmetics/` | Owned cosmetics grouped by slot (frame, title, theme, pet_accessory) |
| POST | `/api/character/equip/` | Equip a cosmetic item (body: `{item_id}`) |
| POST | `/api/character/unequip/` | Clear a cosmetic slot (body: `{slot}`) |

### Pets & Mounts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/pets/stable/` | Full pet + mount collection with stats |
| POST | `/api/pets/hatch/` | Hatch an egg + potion (body: `{egg_item_id, potion_item_id}`) |
| POST | `/api/pets/{id}/feed/` | Feed a food item to a pet (body: `{food_item_id}`) — auto-evolves at 100 growth |
| POST | `/api/pets/{id}/activate/` | Set pet as active (only one at a time) |
| GET | `/api/mounts/` | User's mount collection |
| POST | `/api/mounts/{id}/activate/` | Set mount as active |

### Quests
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/quests/active/` | Current active quest with progress, or null |
| GET | `/api/quests/available/` | System quest catalog |
| POST | `/api/quests/start/` | Start a quest (body: `{definition_id, scroll_item_id?}`) |
| GET | `/api/quests/history/` | Past quests (completed / failed / expired) |
| POST | `/api/quests/` | Parent creates a custom quest |
| POST | `/api/quests/{id}/assign/` | Parent assigns a quest to a child (body: `{user_id}`) |

### Daily Challenges
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/challenges/daily/` | Today's daily challenge for the user (idempotent — creates on first access) |
| POST | `/api/challenges/daily/claim/` | Claim the reward once the challenge target is met (idempotent) |

### Chronicle (lifelong timeline)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/chronicle/` | Timeline entries (parent CRUD + read; child read-only of own entries except journal write) |
| GET | `/api/chronicle/summary/` | Counts, current chapter, age & grade strings |
| GET | `/api/chronicle/pending-celebration/` | Unviewed BIRTHDAY entry, or 204 |
| POST | `/api/chronicle/{id}/mark-viewed/` | Dismiss the birthday celebration modal |
| POST | `/api/chronicle/journal/` | Write today's journal entry (self-scoped; 409 if already written today) |
| PATCH | `/api/chronicle/{id}/journal/` | Edit today's journal entry — owner-only, same-local-day only |
| GET | `/api/chronicle/journal/today/` | Today's journal entry for the caller, or 204 |

### Creations
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/creations/` | List creations (role-filtered) |
| POST | `/api/creations/` | Log a creation (multipart, photo required) |
| DELETE | `/api/creations/{id}/` | Delete (owner or parent, blob-first) |
| POST | `/api/creations/{id}/submit/` | Submit for parent bonus XP |
| POST | `/api/creations/{id}/approve/` | Parent grants bonus XP (default +15) |
| POST | `/api/creations/{id}/reject/` | Parent rejects bonus (no reversal of baseline XP) |
| GET | `/api/creations/pending/` | Parent approval queue |

### Character & Trophy
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/character/` | Profile, level, streak, equipped cosmetics, active trophy badge |
| POST | `/api/character/equip/` | Equip a cosmetic (body: `{item_id}`) |
| POST | `/api/character/unequip/` | Clear a cosmetic slot (body: `{slot}`) |
| POST | `/api/character/trophy/` | Set or clear the displayed hero badge (must be earned) |

### Cosmetics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cosmetics/` | Owned cosmetics grouped by slot |
| GET | `/api/cosmetics/catalog/` | Every authored cosmetic (for the Frontispiece's locked intaglios) |

### Mounts (breeding)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mounts/breed/` | Breed two owned mounts → hybrid egg + potion (body: `{mount_a_id, mount_b_id}`); 7-day per-mount cooldown |

### Consumables
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/inventory/{item_id}/use/` | Apply a consumable's one-shot effect (14 effects: streak_freeze, xp_boost, coin_boost, drop_boost, growth_tonic, rage_breaker, growth_surge, feast_platter, mystery_box, lucky_dip, quest_reroll, morale_tonic, skill_tonic, food_basket) |

### Sprites
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sprites/catalog/` | Public, ETag-cached sprite catalog (the only `/api/` endpoint that opts out of `Cache-Control: no-store`) |
| GET | `/api/sprites/admin/` | Parent-only full catalog with authoring inputs |
| POST | `/api/sprites/admin/generate/` | Parent-only — generate a sprite sheet via Gemini 3 Pro Image (requires `GEMINI_API_KEY`) |
| POST | `/api/sprites/admin/{slug}/reroll/` | Replay stored authoring inputs with `overwrite=True` |
| PATCH | `/api/sprites/admin/{slug}/` | Edit `fps` / `pack` only — no image regeneration |
| DELETE | `/api/sprites/admin/{slug}/` | Blob-first delete |

## Business Logic

### Clock In/Out
- One active clock-in at a time (enforced by DB constraint)
- Quiet hours: 10 PM – 7 AM (no clock-in allowed)
- Auto clock-out after 8 hours (Celery task, runs every 30 min)
- Entries > 4 hours flagged for parent review

### Weekly Timecards
- Auto-generated every Sunday at 23:55 local via Celery Beat
- Calculates hourly earnings per project (hours x rate, respecting per-project rate overrides)
- Includes any bonuses earned that week
- Parent approval workflow: pending → approved → paid

### Pay Calculation
```
hourly_rate = project.hourly_rate_override or user.hourly_rate  # default $8/hr
hourly_earnings = total_hours * hourly_rate
bonus = project.bonus_amount (on completion)
balance = sum(all ledger entries)  # positive = owed, negative = paid out
```

### Coins Economy
- Non-monetary progression currency parallel to PaymentLedger
- **Earning:** clock-out (5 coins/hr), project completion (flat x difficulty, bounty pays 2.5x), badge earn (rarity-scaled: common 5 → legendary 150), chore/homework approval
- **Spending:** reward shop redemptions (coins held at request, refunded on denial)
- **Money→Coins exchange:** child requests at `COINS_PER_DOLLAR` rate (default 10), parent approves/denies, balance re-verified at approval time

### Chores
- Recurring tasks (daily / weekly / one_time) with money + coin rewards
- Submit-then-approve workflow: child submits completion, parent approves or rejects
- Shared-custody support: `week_schedule` can be `alternating` with ISO week parity check against a reference date
- No Celery — availability computed on-the-fly from recurrence rules
- `UniqueConstraint` prevents duplicate completions per chore per day

### Homework
- No money, no coins — homework is school duty, not work-for-hire. Rewards are XP, drops, streaks, quests, and Scholar badges.
- `effort_level` (1-5) is a hint that only weights how XP distributes across skill tags; children set their own.
- Creating an assignment fires `homework_created` RPG trigger — drop roll capped to the first log per day, streak + quest progress fire on every create.
- Submission records a `Timeliness` label (early/on_time/late/beyond_cutoff via `HOMEWORK_LATE_CUTOFF_DAYS`); no reward snapshot.
- On approval: XP from skill tags, badges re-evaluated (incl. `HOMEWORK_ON_TIME_COUNT`), `homework_complete` trigger fires with `on_time` context for quest filtering.
- Proof image uploads required — ordered gallery with captions.
- Scholar track content lives in YAML: Planner / Punctual badges, Scholar-themed cosmetics, Scholar's Week / On-Time Streak / Midnight Oil quests.
- AI-planned long-form homework: `POST /api/homework/{id}/plan/` generates a linked Project via Claude + MCP.

### Skill Tree & XP
- Hierarchy: SkillCategory → Subject → Skill
- Projects, milestones, and homework are tagged with skills and XP weights
- On clock-out: time-based XP distributed across project's skill tags by weight
- On milestone completion: XP from milestone skill tags (or fallback to project tags)
- On project completion: difficulty-based XP distributed across skill tags
- On homework approval: XP from homework skill tags
- Locked skills unlock when all prerequisites are met
- Cross-category prerequisites create interesting progression paths

### Badge Evaluation
Triggered on: project completion, milestone completion, clock-out, timecard approval, homework creation + approval. Checks all unearned badges against current stats across 19 criteria types (incl. `HOMEWORK_PLANNED_AHEAD` and `HOMEWORK_ON_TIME_COUNT` for the Scholar track). Badges award rarity-scaled Coins.

### Notifications
Auto-created via Django signals on: project approved/changes requested, milestone completed, badge earned, payout recorded, chore submitted/approved, redemption requested, exchange requested/approved/denied, homework created/submitted/approved/rejected, due-soon reminders.

Frontend polls for unread count every 30 seconds. Bell icon in the top bar shows unread badge with dropdown panel.

### Weekly Email Summary
Celery task (`send_weekly_email_summaries`) fires Sunday at 08:00 and sends:
- **Child**: hours worked, badges earned, current balance
- **Parent**: per-child activity summary, pending timecard count

Uses console email backend in development.

### Ingestion Pipeline
Four-stage Scrapy-style pipeline for importing projects from external sources:
1. **ParseStage** — source-specific ingestor (Instructables scraper, PDF extractor, generic URL)
2. **NormalizeStage** — standardizes fields across sources
3. **MarkdownStage** — converts to markdown (crawl4ai → markdownify → synthesis fallback)
4. **EnrichStage** — AI enrichment via Claude (category, difficulty, skill tags, extra materials, summary). No-op without `ANTHROPIC_API_KEY`.

Async job tracked in `ProjectIngestionJob` (UUID pk). Frontend preview page lets parents edit milestones and steps before committing. Instructables scrapes cached in Redis 24h.

### MCP Server
FastMCP server mounted inside Django ASGI at `/mcp` with 14 tool modules:
achievements, chores, dashboard, homework, ingestion, notifications, payments, portfolio, projects, rewards, savings, timecards, users, plus transport configuration.

Uses DRF TokenAuthentication, DNS rebinding protection, stateless HTTP transport for horizontal scaling, and `sync_to_async` for Django ORM access.

### Google Calendar Integration
OAuth2 flow for linking Google accounts. Syncs app events (project due dates, chores, time entries) to Google Calendar. `CalendarEventMapping` tracks synced events. Encrypted credential storage via Fernet. Parent-initiated linking for child accounts.

### Project Templates
- Save any completed project as a reusable template (copies milestones, steps, materials)
- Create new projects from templates with one click, assigned to any child
- Public templates enable sharing between families (`GET /api/templates/shared/`)

### Savings Goals
- Children set savings targets (e.g., "New bike — $200") with custom icons
- Progress bar auto-updates from current balance
- API: `/api/savings-goals/` with `update_amount` action

### Collaborative Projects
- Add multiple children to a project with configurable pay split percentages
- `ProjectCollaborator` model tracks per-child participation

### QR Code Clock-In
- Generate printable QR codes for each project (amber on black, workshop themed)
- Scan with phone camera to quick-clock-in from the workshop
- API: `GET /api/projects/{id}/qr/` returns PNG image

### Journal Covers (theming)
- 6 journal-cover palettes — Hyrule, Vigil (the only dark cover), Sunlit, Snowquill, Verdant, Harvest. Legacy `summer/winter/spring/autumn` values map forward via `LEGACY_THEME_ALIASES`.
- Each cover ships a tuned `tones` block (`goldLeaf`, `moss`, `mossDeep`, `emberDeep`, `royal`, `rose`) that passes WCAG AA on its `page` / `pageAged` / `pageGlow` surfaces. The contrast gate in `frontend/src/test/themeContrast.test.js` runs 216 assertions per cover and refuses palette edits that drop below 4.5:1 (body) / 3:1 (chip text).
- Theme preference saved per-user on the backend; `applyTheme()` swaps CSS custom properties at runtime for instant switching with a live preview on the Settings picker.

### Greenlight CSV Import
- Import Greenlight transaction CSV data for payout reconciliation
- Parses Amount and Description columns, creates payout ledger entries
- API: `POST /api/greenlight/import/` with `user_id` and `csv_data`

### RPG Gamification Layer
Habitica-inspired RPG system layered on top of existing productivity features. Every task completion flows through `GameLoopService.on_task_completed` in `apps/rpg/services.py`, which orchestrates streak tracking, item drops, and quest progress.

- **Streaks & daily check-in** — `CharacterProfile.login_streak` increments on consecutive active days, resets on gaps > 1 day. First action each day awards streak-scaled coins: `5 × min(1 + streak × 0.10, 3.0)` (5c at day 1, 15c cap at day 20+). Milestone notifications fire at streaks of 3, 7, 14, 30, 60, 100. `longest_login_streak` tracks the all-time record.
- **Perfect Day** — Nightly Celery task awards `perfect_days_count += 1` and 15 bonus coins to any child who was active AND completed all daily chores. Gentle-nudge design: missed days dim the streak flame visually but never destroy earned rewards.
- **Habits** — `/api/habits/` — Micro-behaviors distinct from chores (no approval, multiple taps/day allowed). `strength` increments on `+1` taps, decrements on `-1`, and decays by 1 daily if untapped (Celery task at 00:05 local). Strength drives a color scale (red → yellow → green → blue). Positive habit taps trigger the full game loop (drops, quest progress).
- **Drops & Inventory** — Every task completion rolls against `BASE_DROP_RATES[trigger_type]` (e.g., clock_out 40%, chore 30%, milestone 80%, badge 100%) + streak bonus (`+5%/day`, capped at +50%). Weighted random from `DropTable` entries filtered by `min_level`. 23+ items across eggs, potions, food, cosmetics, and coin pouches. Already-owned cosmetics auto-salvage to coins. Frontend `useDropToasts` hook polls every 20s and emits rarity-colored toast celebrations via `DropToastStack`.
- **Pets & Mounts** — `/bestiary` (split across **Companions**, **Mounts**, and **Hatchery** tabs) — 17 species × 6 potion variants (gated per species via `available_potions`). Lifecycle: hatch on the Hatchery tab (consumes 1 egg + 1 potion, species/potion looked up from typed FKs on `ItemDefinition`) → feed food items on Companions (+15 growth for preferred food, +5 otherwise; mounts can also be **bred** for hybrid eggs after a 7-day per-mount cooldown) → auto-evolve at 100 growth into a matching `UserMount`. Each tab carries filter pills (Companions: `All / Active / Hungry / Ready to evolve`; Mounts: `All / Active / Ready to breed / On cooldown`). Direct-grant growth from consumables is daily-capped per pet (`CONSUMABLE_GROWTH_DAILY_CAP=50`). A purely visual `happiness_for_pet` state (`happy`/`bored`/`stale`/`away`, derived from `last_fed_at`) dims the sprite without penalizing rewards. Only one active pet and one active mount at a time.
- **Quests** — `/quests` — Two types: **boss** (damage-based HP pool) and **collection** (item count target). One active quest per user at a time. Damage scales per trigger (clock_out 10/hr, chore 15, homework 25, milestone 50, badge 30, project 75, habit 5). `QuestDefinition.trigger_filter` supports filtering by `allowed_triggers`, `project_id`, `skill_category_id`, `chore_ids`, `savings_goal_id`, `streak_target`, `perfect_day_target`. Rage mechanic: if no participant makes progress in a full day, the boss gains a 20-point shield (visual urgency, easily recoverable). On completion: coin + XP + item rewards auto-distributed; status → `completed`. Past end_date without completion → `expired` (no rewards, no penalty). Parents can create custom quests or assign to children.
- **Cosmetics** — `/character` — 4 equip slots (frame, title, theme, pet accessory). `CharacterProfile` has nullable FKs with `limit_choices_to` enforcing type safety. Cosmetics are NOT consumed on equip (unlike eggs/potions/food). Drop from high-value triggers (milestone, badge, perfect day, quest complete). Duplicates salvage for coins. Avatar frame renders as a colored border; title renders as a chip under the display name.

## Frontend

### Design
- Dark mode workshop aesthetic with seasonal theme switching
- Space Mono for headings/numbers, DM Sans for body text
- Framer Motion micro-animations on interactions
- Mobile-first with sidebar nav (desktop) and bottom nav (mobile)

### Pages

The app organizes pages into five "chapter" hubs plus utility routes. The legacy flat routes (`/projects`, `/chores`, `/homework`, `/habits`, `/inventory`, `/stable`, `/character`, `/rewards`, `/achievements`, `/portfolio`, `/payments`, `/timecards`) all redirect to their hub-with-tab equivalents so old bookmarks keep working.

| Page | Route | Description |
|------|-------|-------------|
| Login | -- | Token auth form |
| Today (Dashboard) | `/` | Role-routed: child sees contextual hero (clocked / next-action / quest / idle), vital pip strip, quest log, loot rail; parent sees aggregated approval queue + week-at-a-glance |
| Quests Hub | `/quests` | Tabs: Ventures (Projects), Duties (Chores), Study (Homework), Rituals (Habits) |
| Project Detail | `/quests/ventures/:id` | Plan tab (milestones + steps), Materials, Photos, QR code, save-as-template |
| New Project | `/quests/ventures/new` | Create form with Instructables URL preview (parent only) |
| Project Ingest | `/quests/ventures/ingest` | AI import preview — edit milestones, steps, materials before commit |
| Trials | `/trials` | Time-boxed boss/collection quests overlay (separate from the regular-cadence Quests hub) |
| Atlas Hub | `/atlas` | Tabs: Skills (Illuminated Atlas tome shelf), Badges (Reliquary Codex sigil case), Sketchbook (project + homework gallery), Yearbook (lifelong chronicle timeline) |
| Bestiary Hub | `/bestiary` | Tabs: Satchel (Inventory), Party (Pet + Mount stable with breeding) |
| Treasury Hub | `/treasury` | Tabs: Coffers (Payments), Wages (Timecards), Bazaar (Rewards + coin balance + exchange) |
| Sigil (Character) | `/sigil` | Frontispiece — illuminated initial, trophy badge picker, four cosmetic chapters with locked intaglios + live theme preview |
| Clock | `/clock` | Large circular timer, project selector, one-tap clock in/out |
| Manage | `/manage` | Parent CRUD for children, templates, rewards, categories, subjects, skills, badges, sprites (Codex authoring surface) |
| Activity | `/activity` | Cross-cutting activity feed |
| Settings | `/settings` | Profile, journal cover picker, Google account linking, PWA install card |

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

# Run backend tests
docker compose exec django python manage.py test

# Run frontend tests (Vitest + RTL + MSW; coverage gate enforced in CI)
cd frontend && npm run test:coverage

# Reset everything
docker compose down -v
```

## Environment Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (insecure dev key) | Django secret key |
| `DEBUG` | `True` | Debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `CSRF_TRUSTED_ORIGINS` | — | Required behind reverse proxy |
| `DATABASE_URL` | `postgres://summerforge:summerforge@db:5432/summerforge` | Database connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis cache URL |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery broker URL |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:3000` | CORS origins (dev only) |
| `PARENT_PASSWORD` | `summerforge2025` | Seed data parent password |
| `CHILD_PASSWORD` | `summerforge2025` | Seed data child password |

### Optional Features

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (empty) | Enables AI project suggestions + ingestion enrichment + AI-planned long-form homework |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model for AI features |
| `GEMINI_API_KEY` | (empty) | Enables the `generate_sprite_sheet` MCP tool / `/api/sprites/admin/generate/` endpoint |
| `GEMINI_IMAGE_MODEL` | `gemini-3-pro-image-preview` | Gemini image model for sprite generation ("Nano Banana Pro") |
| `GOOGLE_CLIENT_ID` | (empty) | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | (empty) | Google OAuth2 client secret |
| `GOOGLE_REDIRECT_URI` | (empty) | Google OAuth2 redirect URI |
| `USE_S3_STORAGE` | `false` | When true, route `STORAGES["default"]` (user media) through Ceph RGW |
| `SPRITE_S3_BUCKET` | `abby-sprites` | Public-read Ceph bucket for runtime-authored sprite PNGs |
| `SPRITE_S3_ENDPOINT` | (= `AWS_S3_ENDPOINT_URL`) | Ceph RGW endpoint for the sprite bucket |
| `SPRITE_S3_CUSTOM_DOMAIN` | (empty) | Optional CDN hostname for sprites; empty → raw Ceph URL |

### MCP Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ALLOWED_HOSTS` | (derived from `ALLOWED_HOSTS`) | DNS rebinding protection allow-list |
| `MCP_ALLOWED_ORIGINS` | (derived from `CSRF_TRUSTED_ORIGINS`) | Origin allow-list |
| `MCP_PUBLIC_BASE_URL` | — | Public URL advertised to MCP clients |

### Sentry (Backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_DSN` | (empty) | Sentry DSN — if blank, error tracking is disabled |
| `SENTRY_ENVIRONMENT` | (derived from `DEBUG`) | Environment tag |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.2` | Performance trace sample rate |
| `SENTRY_RELEASE` | — | Git SHA release tag (auto-set by CI) |

### Sentry (Frontend)

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_SENTRY_DSN` | (empty) | Frontend Sentry DSN |
| `VITE_SENTRY_ENVIRONMENT` | `production` | Frontend environment tag |
| `VITE_SENTRY_TRACES_SAMPLE_RATE` | `0.2` | Frontend trace sample rate |
| `VITE_SENTRY_RELEASE` | — | Frontend release tag (auto-set by CI build arg) |

### Tunable Settings (in `config/settings.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `COINS_PER_HOUR` | `5` | Coins awarded per clock-out hour |
| `COINS_PER_BADGE_RARITY` | common 5 → legendary 150 | Per-rarity coin bonus |
| `COINS_PER_DOLLAR` | `10` | Coins per $1.00 in money→coins exchange |
| `HOMEWORK_LATE_CUTOFF_DAYS` | `3` | Past this many days late, submissions flip from `late` to `beyond_cutoff` (label-only — homework pays no money or coins) |
| `HOMEWORK_SELF_PLAN_LEAD_DAYS` | `3` | Children can self-trigger AI planning only when due_date is at least N days out; parents bypass |
| `BIRTHDAY_COINS_PER_YEAR` | `100` | Coins granted on birthday, multiplied by `age_years` |
| `SPRITE_GENERATION_MAX_FRAMES` | `8` | Hard cap on `frame_count` for the `generate_sprite_sheet` tool — bounds worst-case Gemini spend per call |

### RPG Game-Design Constants

Hardcoded in `apps/rpg/services.py`, `apps/pets/services.py`, and `apps/quests/services.py` — these are game-design values, not deploy-time config.

| Constant | Location | Default | Description |
|----------|----------|---------|-------------|
| `BASE_CHECK_IN_COINS` | `rpg/services.py` | `5` | Base daily check-in bonus before streak multiplier |
| `STREAK_MULTIPLIER_PER_DAY` | `rpg/services.py` | `0.10` | Per-day bonus to check-in multiplier |
| `STREAK_MULTIPLIER_CAP` | `rpg/services.py` | `3.0` | Max check-in bonus multiplier (15c/day at day 20+) |
| `RAGE_SHIELD_STEP` | `quests/services.py` | `20` | Boss-quest rage climb/decay step per day |
| `RAGE_SHIELD_CAP` | `quests/services.py` | `100` | Max rage a boss quest accumulates |
| `BASE_DROP_RATES` | `rpg/services.py` | dict by trigger | Base drop probability per trigger type (incl. `journal_entry` 0.10, `creation_logged` 0.25, `homework_created` 0.15 — last three are daily-capped at the service layer) |
| `STREAK_DROP_BONUS_PER_DAY` | `rpg/services.py` | `0.05` | Per-day bonus to drop rate |
| `STREAK_DROP_BONUS_CAP` | `rpg/services.py` | `0.50` | Max streak drop bonus (+50%) |
| `GROWTH_PREFERRED_FOOD` | `pets/services.py` | `15` | Growth points from preferred food |
| `GROWTH_NEUTRAL_FOOD` | `pets/services.py` | `5` | Growth points from non-preferred food |
| `EVOLUTION_THRESHOLD` | `pets/services.py` | `100` | Growth points to evolve pet into mount |
| `CONSUMABLE_GROWTH_DAILY_CAP` | `pets/services.py` | `50` | Per-pet per-local-day cap on direct-grant growth from `growth_surge` / `feast_platter` |
| `MOUNT_BREEDING_COOLDOWN_DAYS` | `pets/services.py` | `7` | Per-mount cooldown between breeding pairings |
| `CHROMATIC_UPGRADE_CHANCE` | `pets/services.py` | `0.02` | Probability a bred egg overrides parent potion to Cosmic (legendary) |
| `TRIGGER_DAMAGE` | `quests/services.py` | dict by trigger | Per-trigger boss damage (clock_out scales by hours) |
