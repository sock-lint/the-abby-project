# Age-aware growth & Chronicle

## Context

The Abby Project currently has no concept of Abby's real-world age. Every child user is timeless — the app never knows whether she's 7 or 17, never references what grade she's in, never accumulates across-year artifacts, and never celebrates birthdays. The user (Abby's father) wants her age to be **an element or variable that's used in the app** so the app "grows with her."

Abby is currently 14. The chosen horizon is **indefinite** — the user wants her to keep using this app for life, not just through high school. The Chronicle must therefore keep rolling past grade 12 with no terminal state; graduation is a milestone inside the timeline, not the end of the timeline.

The approach is **hybrid progression** (some things automatic from DOB, some parent-toggled). The MVP scope is **Foundation + Chronicle** — not the broader aesthetic-dial or feature-pack buildout. Future feature packs (Driver's Ed, First Job, College Prep, and eventually adult-life packs — career, housing, etc.) will live in their own specs and write into the foundation laid here.

**Intended outcome:** Abby gets a lifelong "Yearbook" artifact — a chronological, year-by-year record of her life, auto-built from the projects / chores / homework / badges / coins she earns in the app, plus hand-authored memories and illuminated "first-ever" moments. Through grade 12, chapters are school-year labelled (Freshman → Senior); post-graduation, chapters switch to age-based labelling (e.g. `"Age 19 · 2030–31"`) but the underlying data shape and rollover rhythm stay identical. Birthdays are a big-moment celebration every year. The foundation (DOB + grade + unlocks) is cheap to lay and unblocks every future "growth" feature.

## Summary

Three additive backend changes and one new frontend surface:

1. **Age data on `User`** — `date_of_birth`, `grade_entry_year`, computed properties.
2. **`unlocks` JSONField on `CharacterProfile`** — scaffolding for parent-toggled feature gates (no UI, no callers yet — just the pipe for future specs).
3. **New `apps/chronicle/` app** — `ChronicleEntry` model, `ChronicleService`, Celery tasks, REST viewset, event hooks in existing flows.
4. **Atlas → Yearbook tab** — timeline UI, birthday big-moment modal, manual-entry form.

Single-child assumption (Abby). Data model is per-user, so adding siblings later is a UX question, not a schema one.

## 1. Data model

### 1a. `User` (`apps/accounts/models.py`)

Two new nullable fields:

```python
date_of_birth = models.DateField(null=True, blank=True)
grade_entry_year = models.PositiveIntegerField(null=True, blank=True)
# calendar year of August she entered 9th grade — e.g. 2025
```

Computed properties (all return `None` if source data missing):

```python
@property
def age_years(self) -> int | None: ...
@property
def current_grade(self) -> int | None:
    # school_year = today.year if today.month >= 8 else today.year - 1
    # grade = 9 + (school_year - grade_entry_year)
@property
def school_year_label(self) -> str | None:
    # grade 9-12: "Freshman" / "Sophomore" / "Junior" / "Senior"
    # grade > 12: "Age {age_years} · {yyyy}-{yy}" (e.g. "Age 19 · 2030-31")
    # grade < 9 (pre-HS): "Grade {current_grade}" (e.g. "Grade 6")
@property
def days_until_adult(self) -> int | None: ...
```

Why `grade_entry_year` is separate from DOB: kids skip/repeat grades, Phoenix school-cutoff rules near DOB boundaries are fuzzy, and a parent-set integer is more reliable than a computation. Phoenix school-year rollover hard-coded to Aug 1 (start) / Jun 1 (end).

### 1b. `CharacterProfile.unlocks` (`apps/rpg/models.py`)

```python
unlocks = models.JSONField(default=dict, blank=True)
```

Scaffolded for future hybrid feature-gates. Schema convention:

```python
{
    "drivers_ed":   {"enabled": True,  "enabled_at": "2026-05-12"},
    "first_job":    {"enabled": False},
    "college_prep": {"enabled": False},
}
```

Three helpers on `CharacterProfile`: `is_unlocked(slug) -> bool`, `unlock(slug)`, `lock(slug)`. No UI, no readers in this spec. Future feature-pack specs build their own admin + read paths on top.

### 1c. `ChronicleEntry` (new `apps/chronicle/models.py`)

```python
class ChronicleEntry(CreatedAtModel):
    class Kind(models.TextChoices):
        BIRTHDAY      = "birthday"
        CHAPTER_START = "chapter_start"
        CHAPTER_END   = "chapter_end"
        FIRST_EVER    = "first_ever"
        MILESTONE     = "milestone"
        RECAP         = "recap"
        MANUAL        = "manual"

    user                 = FK(User, related_name="chronicle_entries", on_delete=CASCADE)
    kind                 = CharField(max_length=32, choices=Kind.choices)
    occurred_on          = DateField()                   # authoritative "when"
    chapter_year         = PositiveIntegerField()        # 2025 = Aug 2025–Jul 2026; life-long, not school-bound
    title                = CharField(max_length=160)
    summary              = TextField(blank=True)
    icon_slug            = CharField(max_length=80, blank=True)
    event_slug           = CharField(max_length=80, blank=True)   # e.g. "first_bounty_payout"
    related_object_type  = CharField(max_length=40, blank=True)   # soft FK — not GenericForeignKey
    related_object_id    = PositiveIntegerField(null=True, blank=True)
    metadata             = JSONField(default=dict, blank=True)
    viewed_at            = DateTimeField(null=True, blank=True)   # big-moment dismissal

    class Meta:
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            Index(fields=["user", "chapter_year"]),
            Index(fields=["user", "event_slug"]),
            Index(fields=["user", "viewed_at"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["user", "event_slug"],
                condition=Q(kind="first_ever"),
                name="unique_first_ever_per_user",
            ),
        ]
```

**Design notes:**

- `occurred_on` is distinct from `created_at` because Celery writes RECAPs and BIRTHDAYs at midnight-ish, but the "when" must be authoritative.
- `chapter_year` is stored as int (Aug-starting year) for cheap `GROUP BY` and chapter pagination. It's named `chapter` (not `school`) because the same field keeps working after grade 12 — label flips to age-based, data shape stays.
- `event_slug` + partial unique index gives idempotent "emit-once" semantics for firsts without a tracking side-table.
- `related_object_type` / `related_object_id` is a soft FK: deletions of referenced objects leave dangling pointers, but titles/summaries are denormalized at write time so history reads correctly regardless.
- `viewed_at` is reused for future big-moment takeovers (e.g. first legendary badge) without a second migration.

## 2. Service layer

### 2a. `ChronicleService` (`apps/chronicle/services.py`)

```python
class ChronicleService:
    @staticmethod
    def record_first(user, event_slug, *, title, summary="", icon_slug="",
                     related=None, occurred_on=None, metadata=None) -> ChronicleEntry | None:
        """Idempotent. Returns None if slug already exists for this user (IntegrityError caught)."""

    @staticmethod
    def record_birthday(user, *, on_date=None) -> ChronicleEntry:
        """Idempotent via get_or_create(user, kind=BIRTHDAY, occurred_on=on_date)."""

    @staticmethod
    def record_chapter_start(user, chapter_year) -> ChronicleEntry: ...

    @staticmethod
    def record_chapter_end(user, chapter_year) -> ChronicleEntry: ...

    @staticmethod
    def freeze_recap(user, chapter_year) -> ChronicleEntry:
        """Aggregates project/homework/chore/coin/badge stats into metadata.
        Idempotent via get_or_create(user, kind=RECAP, chapter_year=...)."""
```

MANUAL entries go through the REST API, not this service.

### 2b. Event hooks — where `record_first` is called

Extend `GameLoopService.on_task_completed` (`apps/rpg/services.py`) with a new pipeline step after quest-progress, wrapped in `try/except logger.exception(...)` per the existing "never break parent flow" doctrine:

```python
result["chronicle"] = self._record_chronicle_firsts(user, trigger_type, context)
```

Slug map (stored in a module-level dict in `apps/chronicle/firsts.py` for extensibility):

| Trigger | Slug |
|---|---|
| `project_complete` | `first_project_completed` |
| `project_complete` + `context["payment_kind"] == "bounty"` | `first_bounty_payout` |
| `milestone_complete` | `first_milestone_bonus` |
| `badge_earned` + `context["rarity"] == "legendary"` | `first_legendary_badge` |
| `perfect_day` | `first_perfect_day` |
| `quest_complete` | `first_quest_completed` |
| streak reaches 30 / 60 / 100 | `first_streak_30` / `_60` / `_100` |

Flows that don't route through `GameLoopService` call `ChronicleService.record_first` directly:

- `ExchangeService.approve` → `first_exchange_approved`.
- `PetService.hatch_pet` → `first_pet_hatched`.
- `PetService._evolve_to_mount` → `first_mount_evolved`.

### 2c. Celery Beat tasks (`apps/chronicle/tasks.py`, added to `CELERY_BEAT_SCHEDULE`)

- **`chronicle-birthday-check`** — daily at **00:10** local. For each child with `DOB month/day == today`:
  - `with transaction.atomic():`
    - `get_or_create` BIRTHDAY entry (idempotent).
    - On create only: award `settings.BIRTHDAY_COINS_PER_YEAR × age_years` coins via `CoinService.award` with `CoinLedger.Reason.ADJUSTMENT` and `metadata={"reason_detail": "birthday_gift"}`.
    - Write `entry.metadata["gift_coins"] = <amount>`, save.
  - Fire `NotificationType.BIRTHDAY` to child + parents.

- **`chronicle-chapter-transition`** — daily at **00:20** local. No-ops unless today is Aug 1 or Jun 1.
  - Aug 1: `record_chapter_start(user, current_chapter_year)` for each child with DOB set.
  - Jun 1: `record_chapter_end` + `freeze_recap` for the chapter that just ended.
    - If the closing chapter corresponds to grade 12: write `metadata["is_graduation"] = True` on the RECAP **and** emit a separate `MILESTONE`-kind entry with `event_slug="graduated_high_school"`, title `"🎓 Graduated high school"`, so it renders as a standalone illuminated entry on the timeline.
    - After grade 12, this task continues firing forever — chapter labels switch to age-based automatically via the `school_year_label` property; no special-case logic in the task itself.

### 2d. Notification types (`apps/notifications/models.py`)

Two new `NotificationType` choices:

- `BIRTHDAY` — `"It's Abby's 15th birthday! Her Yearbook now shows a new entry."`
- `CHRONICLE_FIRST_EVER` — `"First bounty payout — added to your Yearbook."` Deep-links to `/atlas?tab=yearbook&entry={id}`.

### 2e. REST API — `ChronicleViewSet` (`apps/chronicle/views.py`, mounted at `/api/chronicle/`)

- `GET /api/chronicle/` — list entries for current child (parents: accept `?user_id=` query). Supports `?chapter_year=2025`. Uses `RoleFilteredQuerySetMixin`.
- `GET /api/chronicle/summary/` — grouped-by-chapter-year payload for the Yearbook UI: `{chapters: [{chapter_year, grade, label, is_current, is_post_hs, stats, entries: [...]}]}`. Live stats computed inline for current chapter; past chapters read from the stored RECAP entry's `metadata`.
- `GET /api/chronicle/pending-celebration/` — returns the single unviewed entry eligible for big-moment takeover (today's BIRTHDAY for now; extensible later). Returns HTTP 204 if none.
- `POST /api/chronicle/{id}/mark-viewed/` — idempotent; sets `viewed_at = now()` if null.
- `POST /api/chronicle/manual/` — parent-only (`IsParent`), creates a MANUAL entry. Body requires `user_id` (child target), `title`, `occurred_on`; optional `summary`, `icon_slug`, `metadata`.
- `PATCH /api/chronicle/{id}/` — parent-only; only `kind=MANUAL` entries are editable.
- `DELETE /api/chronicle/{id}/` — parent-only; only MANUAL entries deletable (auto-generated kinds are immutable history).

## 3. Frontend

### 3a. Manage → Children form — DOB + grade entry year

Extend the existing child-edit form (already PATCHes `/api/children/{id}/` for `hourly_rate`) with:

- `<TextField type="date">` for DOB.
- `<SelectField>` for `grade_entry_year`, populated `[current_year-4 .. current_year+4]`, labelled like `"2025 (9th grade Aug 2025)"` to reduce confusion.

Child does NOT edit these themselves. Readback-only display on child Settings page: *"You're 14 · Freshman Year."*

### 3b. Atlas → Yearbook tab (new, 4th sibling of Skills / Badges / Sketchbook)

Route: `/atlas?tab=yearbook`. New page `frontend/src/pages/Yearbook.jsx` + page-scoped components under `frontend/src/pages/yearbook/`:

- `ChapterCard.jsx` — one chapter card. Current-chapter variant: live stats + "year in progress" progress bar (days elapsed / total in Aug-Jul window). Past-chapter: reads frozen RECAP. Near-future chapters (next 3) render as faint placeholders (*"Sophomore Year — begins Aug 2026"* or *"Age 19 · begins Aug 2030"*). Chapter labels are K-12 grade names through senior year, then flip to age-based after. No graduation countdown — graduation is a milestone entry, not a terminal event.
- `TimelineEntry.jsx` — one inline entry row. Variants per `kind`. Icon (`icon_slug` → sprite) + title + date + click-to-open.
- `EntryDetailSheet.jsx` — `BottomSheet` for entry details: full summary, linked project/badge/photo if present, metadata rendering.
- `ManualEntryFormModal.jsx` — parent-only; title + summary + `occurred_on` + optional icon_slug. Uses form primitives.
- `yearbook.constants.js` — grade labels, `kind` → icon map, RECAP stat field ordering.

Layout: vertical timeline, newest-first. Current chapter always expanded. Past chapters as collapsed `AccordionSection` (persists per-title open state in `localStorage`). Future chapters whispered at the bottom.

Empty state (no DOB set): `<EmptyState>` prompting parent to set DOB in Manage.

### 3c. Birthday celebration modal (big moment)

New `frontend/src/components/BirthdayCelebrationModal.jsx` — **shared** component (not page-scoped), mounted at `App.jsx` so it fires regardless of current route.

**Trigger:** `App.jsx` boot-time effect calls `GET /api/chronicle/pending-celebration/`. If the response is an entry (not 204), mount the modal over everything.

**Modal:**

- `createPortal` → `document.body`, `role="alertdialog"`, `aria-labelledby` via `useId`.
- Gold-wash backdrop fade-in.
- Illuminated parchment card with framer-motion page-turn entrance (`scale + rotateY`).
- Giant age number (`"15"`) scales in with gold-leaf glow, staggered ~300ms after card.
- Animated birthday-candle sprite above the age number. **MVP uses a static placeholder PNG**; generating the animated sprite via `generate_sprite_sheet` is a follow-up.
- Confetti particles (framer-motion) behind card.
- After ~1.5s delay: `"🎁 <gift_coins> coins added to your treasury"` count-up reveal, reading `entry.metadata.gift_coins`.
- `"Turn the page →"` dismiss button → `POST /api/chronicle/{id}/mark-viewed/` → app navigates to `/atlas?tab=yearbook&entry={id}`.
- **`prefers-reduced-motion`** → backdrop + card fade-in only; no rotate, no stagger, no confetti, no count-up.

### 3d. "First-ever" celebrations — piggyback on notifications

No new UI system. `NotificationType.CHRONICLE_FIRST_EVER` fires through the existing notification bell with deep link to the entry. Entry's `icon_slug` reused as the notification icon.

### 3e. Graduation as a milestone (not a terminal state)

When the senior-year RECAP is frozen (Jun 1 of grade-12 year), the separately-emitted `MILESTONE`-kind entry (`"🎓 Graduated high school"`) renders as an illuminated gold-leaf row at the bottom of the senior chapter. The Yearbook simply continues: the next chapter opens Aug 1 of that year, labelled by age. No banner, no "complete" state, no features shut off — the app is designed to keep accumulating chapters indefinitely.

## 4. Testing

Follows existing CLAUDE.md patterns. No new frameworks.

### Backend (`python manage.py test`)

- `apps/accounts/tests/test_age_properties.py` — `age_years`, `current_grade`, `school_year_label`, `days_until_adult` across boundary cases: day-before birthday, DOB itself, Feb 29 born in non-leap year, pre-Aug vs post-Aug current date, grades 9–12, grade 13+ (post-HS label format), grade <9 (pre-HS label format), missing DOB/grade_entry_year.
- `apps/chronicle/tests/test_service.py` — `record_first` returns None on duplicate slug; `record_birthday` idempotent; `freeze_recap` aggregates match a hand-counted fixture.
- `apps/chronicle/tests/test_tasks.py` — birthday-check creates exactly one entry + exactly one coin ledger entry even on repeat runs same day; coin amount = `BIRTHDAY_COINS_PER_YEAR × age_years`; missing DOB no-ops; chapter-transition fires only on Aug 1 / Jun 1; Jun 1 of grade-12 flags `is_graduation` AND emits the standalone `graduated_high_school` MILESTONE entry; Jun 1 of grade-13+ (post-HS) fires normally with no graduation flag/milestone (no duplicate graduation across years).
- `apps/chronicle/tests/test_game_loop_hook.py` — triggering `GameLoopService.on_task_completed` with `project_complete` + bounty context creates `first_bounty_payout` FIRST_EVER entry; second call does NOT create duplicate; chronicle-service exception does not break the parent flow (mock with `side_effect=Exception`, assert outer still returns success).
- `apps/chronicle/tests/test_views.py` — summary endpoint grouping shape; pending-celebration 204 empty, returns entry when one exists; mark-viewed sets `viewed_at`; manual-entry child-gets-403; parent-scoped writes for `user_id`.

### Frontend (`vitest`)

- `Yearbook.test.jsx` — renders current/past/future chapter cards from stubbed summary; empty state when DOB missing; `AccordionSection` open/close persists.
- `Yearbook.test.jsx` (interactions via `spyHandler`): parent "Add memory" → `POST /api/chronicle/manual/` body shape; entry click opens `EntryDetailSheet`; child role does not see "Add memory".
- `BirthdayCelebrationModal.test.jsx` — renders from fixture; dismiss fires `POST /api/chronicle/{id}/mark-viewed/`; `prefers-reduced-motion` skips animation classes; `role="alertdialog"` queryable; `gift_coins` rendered.
- `App.test.jsx` (extension) — modal mounts only when pending-celebration returns entry; does NOT mount on 204.

### Deliberately not tested

- Sprite animation timing on candle (visual-only).
- Exact framer-motion easings / pixel positions.
- Django-level Celery beat schedule wiring (trust the existing harness).

## 5. Scope guardrails

### In scope

- `User.date_of_birth`, `User.grade_entry_year`, computed age/grade properties.
- `CharacterProfile.unlocks` JSONField + helpers (no UI, no readers).
- `apps/chronicle/` new app: model + service + tasks + viewset + URL routing.
- Event hooks in `GameLoopService`, `ExchangeService.approve`, `PetService.hatch_pet` / evolution.
- Atlas → Yearbook tab + page-scoped components.
- `BirthdayCelebrationModal` big-moment takeover + pending-celebration endpoint + mark-viewed action.
- Coin-gift birthday mechanic with `BIRTHDAY_COINS_PER_YEAR` setting (default 100).
- Manage → Children form: DOB + grade entry year fields.
- `NotificationType.BIRTHDAY`, `NotificationType.CHRONICLE_FIRST_EVER`.

### Out of scope (future specs)

- **Feature packs** (Driver's Ed, First Job, College Prep, and eventually adult-life packs — career, housing, finance, etc.). `unlocks` is scaffolded; no writers, no readers.
- **Aesthetic dial** — DOB-driven theme/copy maturation.
- **Copy-tone scaling**, **reward-curve rescaling** by age.
- **Multi-child optimizations**. Data model works per-user.
- **Nano-Banana-generated animated candle sprite** — static PNG ships first; animated sprite is a small later PR.
- **Adult-era aesthetic evolution** — post-graduation UX continues in the same journal idiom for MVP. Whether the RPG/pet layer, copy tone, or journal aesthetic should shift for adult Abby is a future decision, not this spec.
- **Retroactive backfill** of pre-14 events. Timeline starts empty and fills forward.

### Known thin ice

- Chapter boundaries hard-coded to Aug 1 / Jun 1 (Phoenix school-year rhythm). Continues forever, even post-HS — the rollover rhythm stays consistent across life stages; only labels change. Year-round school or a move would require a code tweak, not config.
- Birthday coin gift is Celery-driven at 00:10; if beat is down the whole day, the gift misses. `get_or_create` + atomic ensures the gift fires on the next run same day but not the next day. Acceptable for home-scale.
- `related_object_type` / `related_object_id` is a soft FK: deletions leave dangling pointers. Titles/summaries denormalized at write time so history reads correctly.
- The `graduated_high_school` MILESTONE entry uses `event_slug`, but is emitted as a `MILESTONE` kind, not `FIRST_EVER` — the partial unique constraint (scoped to FIRST_EVER) doesn't cover it. Idempotency for that one milestone is enforced via `get_or_create` on `(user, event_slug, kind=MILESTONE)` inside the task. Duplicate-writes risk is therefore bounded to exactly one idempotent call site.

## Critical files

### New

- `apps/chronicle/__init__.py`
- `apps/chronicle/apps.py`
- `apps/chronicle/models.py` — `ChronicleEntry`.
- `apps/chronicle/services.py` — `ChronicleService`.
- `apps/chronicle/firsts.py` — slug map for trigger → first-ever event.
- `apps/chronicle/tasks.py` — `chronicle-birthday-check`, `chronicle-chapter-transition`.
- `apps/chronicle/views.py` — `ChronicleViewSet`.
- `apps/chronicle/serializers.py`.
- `apps/chronicle/urls.py` (or register into `config/urls.py` directly).
- `apps/chronicle/admin.py`.
- `apps/chronicle/migrations/0001_initial.py`.
- `apps/chronicle/tests/test_service.py`, `test_tasks.py`, `test_game_loop_hook.py`, `test_views.py`.
- `frontend/src/pages/Yearbook.jsx`.
- `frontend/src/pages/yearbook/ChapterCard.jsx`.
- `frontend/src/pages/yearbook/TimelineEntry.jsx`.
- `frontend/src/pages/yearbook/EntryDetailSheet.jsx`.
- `frontend/src/pages/yearbook/ManualEntryFormModal.jsx`.
- `frontend/src/pages/yearbook/yearbook.constants.js`.
- `frontend/src/pages/Yearbook.test.jsx`.
- `frontend/src/components/BirthdayCelebrationModal.jsx`.
- `frontend/src/components/BirthdayCelebrationModal.test.jsx`.

### Modified

- `apps/accounts/models.py` — `date_of_birth`, `grade_entry_year`, computed properties.
- `apps/accounts/tests/test_age_properties.py` (new test file under the existing tests folder).
- `apps/accounts/migrations/000X_dob_grade.py` (new).
- `apps/accounts/serializers.py` (and/or `apps/projects/serializers.py` where Child is serialized) — expose DOB, `grade_entry_year`, `age_years`, `current_grade`, `school_year_label` on child endpoints.
- `apps/accounts/admin.py` — expose DOB + grade entry year.
- `apps/projects/views.py` — `ChildViewSet.patch` accepts DOB + `grade_entry_year`.
- `apps/rpg/models.py` — `CharacterProfile.unlocks` + helpers.
- `apps/rpg/services.py` — `GameLoopService.on_task_completed` pipeline extension.
- `apps/rpg/migrations/000X_character_unlocks.py` (new).
- `apps/rewards/services.py` — `ExchangeService.approve` calls `ChronicleService.record_first`.
- `apps/pets/services.py` — `hatch_pet`, `_evolve_to_mount` call `record_first`.
- `apps/notifications/models.py` — add `BIRTHDAY`, `CHRONICLE_FIRST_EVER` to `NotificationType`.
- `config/settings.py` — add `BIRTHDAY_COINS_PER_YEAR = 100`; add Celery beat entries.
- `config/urls.py` — mount `/api/chronicle/`.
- `frontend/src/api/index.js` — new endpoint functions (`getChronicleSummary`, `getPendingCelebration`, `markChronicleViewed`, `createManualEntry`, etc.).
- `frontend/src/App.jsx` — boot-time pending-celebration fetch + mount modal.
- `frontend/src/pages/atlas/index.jsx` — add Yearbook as 4th tab.
- `frontend/src/pages/Manage.jsx` (and child-edit form) — DOB + `grade_entry_year` fields.
- `CLAUDE.md` — add Chronicle app + Yearbook page + birthday mechanic to architecture + gotchas.

### Existing utilities to reuse

- `config.base_models.CreatedAtModel` for `ChronicleEntry` base.
- `config.viewsets.RoleFilteredQuerySetMixin` + `config.permissions.IsParent` for `ChronicleViewSet`.
- `apps.rewards.services.CoinService.award` for the birthday coin gift.
- `apps.notifications.notify` / `notify_parents` for birthday + first-ever notifications.
- `frontend/src/components/{BottomSheet,ConfirmDialog,EmptyState,AccordionSection}` primitives.
- `frontend/src/components/form/{TextField,SelectField,TextAreaField}` for Manage form extension.
- `frontend/src/test/{render,factories,spy,handlers}` for new tests.

## Verification

End-to-end manual sweep (after implementation + all tests green):

1. **Set DOB/grade for Abby.**
   - Parent account → Manage → edit Abby → set DOB (a date you can trigger birthday on for testing) and `grade_entry_year=2025`.
   - Child login → Settings → see `"You're 14 · Freshman Year."`
2. **Yearbook empty-friendly state.**
   - Temporarily clear DOB → child Yearbook shows `EmptyState`.
   - Restore DOB → chapter cards return.
3. **Current-chapter stats.**
   - Child completes a chore → Yearbook's Freshman card live-stats update on page refresh.
4. **First-ever event hook.**
   - Child completes first bounty project → `first_bounty_payout` FIRST_EVER entry appears in current chapter.
   - Completing a second bounty project does NOT create a duplicate entry.
5. **Birthday takeover.**
   - In Django shell: set Abby's DOB to today, run `chronicle-birthday-check` task manually.
   - Next child login → full-screen `BirthdayCelebrationModal` fires, age number visible, coin-count animation reveals.
   - Verify `CoinLedger` has one ADJUSTMENT row with `metadata.reason_detail="birthday_gift"` and the correct amount.
   - Re-running the task same day does NOT add a second ledger row or second entry.
   - Dismiss modal → Yearbook opens to the entry.
6. **Chapter transition.**
   - In Django shell: manually invoke `chronicle-chapter-transition` with `today=date(2026, 6, 1)`.
   - Freshman RECAP entry written with stats in metadata; chapter card flips from "in progress" to frozen stats view.
   - Running again same day does NOT double-write.
   - Repeat with `today=date(2029, 6, 1)` (senior-year end): `is_graduation` flag on RECAP, standalone `"🎓 Graduated high school"` MILESTONE entry renders in senior chapter.
   - Repeat with `today=date(2030, 6, 1)` (first post-HS year-end): chapter closes normally labelled `"Age 18 · 2029-30"`; no duplicate graduation milestone.
7. **Manual entry.**
   - Parent → Yearbook → "Add memory" → submit → new MANUAL entry appears in correct chapter.
   - Child account: "Add memory" button NOT visible; POST from child returns 403.
8. **Notification deep-link.**
   - Fire a `CHRONICLE_FIRST_EVER` → click bell → deep-links to `/atlas?tab=yearbook&entry={id}`, `EntryDetailSheet` opens.
9. **Tests.**
   - `docker compose exec django python manage.py test apps.chronicle apps.accounts` — all green.
   - `cd frontend && npm run test:run` — all green.
   - `npm run test:coverage` — thresholds still met.
10. **Regression sanity.**
    - Existing `GameLoopService.on_task_completed` still returns the same outer shape (with the added `chronicle` key); existing consumers unaffected.
    - Deleting a badge referenced by a FIRST_EVER entry does NOT cascade-delete the entry; entry reads correctly with dangling `related_object_id`.
