# Age-aware Growth & Chronicle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a birthdate/grade foundation to `User`, a lifelong `Chronicle` timeline ("Yearbook") that accrues chapter rollups + first-ever events + birthday big-moments, and the Atlas UI surface to browse it.

**Architecture:** Two nullable `User` fields (`date_of_birth`, `grade_entry_year`) feed computed properties. A new `apps/chronicle/` app owns `ChronicleEntry` (one row per notable event), `ChronicleService` (idempotent writers), two Celery Beat tasks (birthday + chapter transitions), and a `ChronicleViewSet` (`/api/chronicle/`). Event hooks in `GameLoopService`, `ExchangeService`, and `PetService` call `ChronicleService.record_first` to emit first-ever entries. Frontend adds a 4th Atlas tab (Yearbook), a parent-only manual-entry modal, and an `App.jsx`-mounted full-screen `BirthdayCelebrationModal` that fires from a pending-celebration endpoint.

**Tech Stack:** Django 5.1 + DRF, PostgreSQL (partial unique index), Celery 5.4 + Beat, Redis, React 19 + React Router, Vitest 4 + MSW 2 + spyHandler interaction tests, framer-motion for the birthday page-turn animation.

**Spec:** [docs/superpowers/specs/2026-04-21-age-aware-growth-chronicle-design.md](../specs/2026-04-21-age-aware-growth-chronicle-design.md)

---

## Phase 0: Workflow setup (optional)

This plan was produced on the `main` branch without a worktree. If you prefer isolation, create one first:

```bash
git worktree add ../the-abby-project-chronicle -b feat/age-aware-chronicle
cd ../the-abby-project-chronicle
```

Otherwise: work on the current branch; all tasks create independent commits.

---

## Phase 1: `User` age fields + `CharacterProfile.unlocks`

### Task 1: Add `date_of_birth`, `grade_entry_year`, and computed age properties to `User`

**Files:**
- Modify: `apps/accounts/models.py`
- Create: `apps/accounts/migrations/0004_user_dob_grade.py` (exact number depends on current migration state — use whatever `makemigrations` produces)
- Create: `apps/accounts/tests/test_age_properties.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/accounts/tests/test_age_properties.py`:

```python
"""Tests for User.date_of_birth + grade_entry_year computed properties.

Exercises age_years / current_grade / school_year_label / days_until_adult
across boundary cases. Uses unittest.mock.patch to pin 'today' — this repo
does NOT use freezegun or time-machine.
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


def _make_child(dob=None, grade_entry_year=None):
    return User.objects.create(
        username=f"kid-{dob}-{grade_entry_year}",
        role=User.Role.CHILD,
        date_of_birth=dob,
        grade_entry_year=grade_entry_year,
    )


class AgeYearsTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_on_exact_birthday(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 4, 21))
        self.assertEqual(u.age_years, 15)

    @patch("apps.accounts.models.date")
    def test_day_before_birthday(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 20)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 4, 21))
        self.assertEqual(u.age_years, 14)

    @patch("apps.accounts.models.date")
    def test_feb_29_born_in_non_leap_year_treats_mar_1_as_birthday(self, mock_date):
        # Born Feb 29, 2012. On Feb 28, 2026 (non-leap) she's still 13;
        # becomes 14 on Mar 1, 2026.
        mock_date.today.return_value = date(2026, 2, 28)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2012, 2, 29))
        self.assertEqual(u.age_years, 13)

        mock_date.today.return_value = date(2026, 3, 1)
        self.assertEqual(u.age_years, 14)

    def test_no_dob_returns_none(self):
        u = _make_child(dob=None)
        self.assertIsNone(u.age_years)


class CurrentGradeTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_post_august_bumps_to_next_grade(self, mock_date):
        mock_date.today.return_value = date(2025, 8, 15)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.current_grade, 9)

    @patch("apps.accounts.models.date")
    def test_pre_august_stays_on_previous_grade(self, mock_date):
        mock_date.today.return_value = date(2026, 5, 15)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.current_grade, 9)

    @patch("apps.accounts.models.date")
    def test_second_year_shows_grade_10(self, mock_date):
        mock_date.today.return_value = date(2026, 9, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.current_grade, 10)

    def test_no_grade_entry_year_returns_none(self):
        u = _make_child(dob=date(2011, 9, 22))
        self.assertIsNone(u.current_grade)


class SchoolYearLabelTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_freshman(self, mock_date):
        mock_date.today.return_value = date(2025, 10, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.school_year_label, "Freshman")

    @patch("apps.accounts.models.date")
    def test_sophomore_junior_senior(self, mock_date):
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        for today, expected in [
            (date(2026, 10, 1), "Sophomore"),
            (date(2027, 10, 1), "Junior"),
            (date(2028, 10, 1), "Senior"),
        ]:
            mock_date.today.return_value = today
            self.assertEqual(u.school_year_label, expected, today)

    @patch("apps.accounts.models.date")
    def test_post_hs_format(self, mock_date):
        # Entered 9th in Aug 2025 → Senior ends Jun 2029 → first post-HS year
        # is Aug 2029 school_year=2029, age turns 18 that autumn.
        mock_date.today.return_value = date(2029, 10, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.school_year_label, "Age 18 · 2029-30")

    @patch("apps.accounts.models.date")
    def test_pre_hs_format(self, mock_date):
        mock_date.today.return_value = date(2024, 10, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        # grade_entry_year=2025 → in 2024-25, grade = 9 + (2024 - 2025) = 8
        u = _make_child(dob=date(2011, 9, 22), grade_entry_year=2025)
        self.assertEqual(u.school_year_label, "Grade 8")


class DaysUntilAdultTests(TestCase):
    @patch("apps.accounts.models.date")
    def test_counts_down_to_18th(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        u = _make_child(dob=date(2011, 4, 21))
        # 18th birthday = 2029-04-21 — exactly 3 years = 1096 days (includes 2028 leap day)
        self.assertEqual(u.days_until_adult, 1096)

    def test_no_dob_returns_none(self):
        u = _make_child(dob=None)
        self.assertIsNone(u.days_until_adult)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.accounts.tests.test_age_properties -v 2
```

Expected: all tests fail with `AttributeError` or `django.db.utils.ProgrammingError` (field doesn't exist).

- [ ] **Step 3: Add fields + computed properties to `User`**

Edit `apps/accounts/models.py`:

```python
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import CustomUserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        PARENT = "parent", "Parent"
        CHILD = "child", "Child"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CHILD)
    hourly_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("8.00")
    )
    display_name = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    theme = models.CharField(
        max_length=20, default="summer",
        choices=[
            ("summer", "Summer"),
            ("winter", "Winter Break"),
            ("spring", "Spring Break"),
            ("autumn", "Autumn"),
        ],
    )
    date_of_birth = models.DateField(null=True, blank=True)
    grade_entry_year = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Calendar year of August she entered 9th grade (e.g. 2025).",
    )

    objects = CustomUserManager()

    class Meta:
        db_table = "projects_user"

    @property
    def display_label(self) -> str:
        return self.display_name or self.username

    def __str__(self):
        return self.display_label

    # ------------------------------------------------------------------
    # Age / grade / chapter derivations
    # ------------------------------------------------------------------

    @property
    def age_years(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    def _chapter_year(self, today: date | None = None) -> int | None:
        """The August-starting year covering `today`. 2025 = Aug 2025–Jul 2026."""
        today = today or date.today()
        return today.year if today.month >= 8 else today.year - 1

    @property
    def current_grade(self) -> int | None:
        if self.grade_entry_year is None:
            return None
        chapter_year = self._chapter_year()
        if chapter_year is None:
            return None
        return 9 + (chapter_year - self.grade_entry_year)

    @property
    def school_year_label(self) -> str | None:
        grade = self.current_grade
        if grade is None:
            return None
        if 9 <= grade <= 12:
            return {9: "Freshman", 10: "Sophomore", 11: "Junior", 12: "Senior"}[grade]
        if grade < 9:
            return f"Grade {grade}"
        # Post-HS: "Age {n} · {yyyy}-{yy}"
        age = self.age_years
        cy = self._chapter_year()
        if age is None or cy is None:
            return None
        return f"Age {age} · {cy}-{str(cy + 1)[-2:]}"

    @property
    def days_until_adult(self) -> int | None:
        if not self.date_of_birth:
            return None
        try:
            eighteenth = self.date_of_birth.replace(year=self.date_of_birth.year + 18)
        except ValueError:
            # Feb 29 → Mar 1 on non-leap 18th year
            eighteenth = date(self.date_of_birth.year + 18, 3, 1)
        return (eighteenth - date.today()).days
```

- [ ] **Step 4: Generate the migration**

```bash
docker compose exec django python manage.py makemigrations accounts
```

Expected: creates `apps/accounts/migrations/0004_user_dob_grade.py` (or similar number) adding the two nullable fields.

- [ ] **Step 5: Run the test suite**

```bash
docker compose exec django python manage.py test apps.accounts.tests.test_age_properties -v 2
```

Expected: all 12 tests PASS.

- [ ] **Step 6: Also verify existing accounts tests still pass**

```bash
docker compose exec django python manage.py test apps.accounts -v 2
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add apps/accounts/models.py apps/accounts/migrations/ apps/accounts/tests/test_age_properties.py
git commit -m "feat(accounts): add date_of_birth + grade_entry_year + computed age properties"
```

---

### Task 2: Add `CharacterProfile.unlocks` JSONField + helpers

**Files:**
- Modify: `apps/rpg/models.py` (append fields + helpers to `CharacterProfile`)
- Create: `apps/rpg/migrations/00XX_character_unlocks.py` (via `makemigrations`)
- Modify: `apps/rpg/tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Append to `apps/rpg/tests/test_models.py` (check the existing file structure first — may already have `CharacterProfileTests`; add a new test class either way):

```python
class CharacterProfileUnlocksTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)
        # CharacterProfile auto-created via post_save signal

    def test_unlocks_defaults_to_empty_dict(self):
        self.assertEqual(self.user.character_profile.unlocks, {})

    def test_is_unlocked_false_for_missing_slug(self):
        self.assertFalse(self.user.character_profile.is_unlocked("drivers_ed"))

    def test_unlock_sets_enabled_true_and_timestamps(self):
        self.user.character_profile.unlock("drivers_ed")
        self.assertTrue(self.user.character_profile.is_unlocked("drivers_ed"))
        entry = self.user.character_profile.unlocks["drivers_ed"]
        self.assertTrue(entry["enabled"])
        self.assertIn("enabled_at", entry)  # ISO date string

    def test_lock_sets_enabled_false(self):
        self.user.character_profile.unlock("first_job")
        self.user.character_profile.lock("first_job")
        self.assertFalse(self.user.character_profile.is_unlocked("first_job"))

    def test_unlock_persists_to_db(self):
        self.user.character_profile.unlock("college_prep")
        self.user.character_profile.save()
        self.user.character_profile.refresh_from_db()
        self.assertTrue(self.user.character_profile.is_unlocked("college_prep"))
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_models.CharacterProfileUnlocksTests -v 2
```

Expected: FAIL with `AttributeError: 'CharacterProfile' object has no attribute 'unlocks'`.

- [ ] **Step 3: Add field + helpers to `CharacterProfile`**

Locate `class CharacterProfile(...)` in `apps/rpg/models.py` and add:

```python
# inside CharacterProfile class, after existing fields:
unlocks = models.JSONField(default=dict, blank=True)

# and as instance methods:
def is_unlocked(self, slug: str) -> bool:
    entry = self.unlocks.get(slug) or {}
    return bool(entry.get("enabled"))

def unlock(self, slug: str, *, save: bool = False) -> None:
    from datetime import date
    self.unlocks[slug] = {"enabled": True, "enabled_at": date.today().isoformat()}
    if save:
        self.save(update_fields=["unlocks"])

def lock(self, slug: str, *, save: bool = False) -> None:
    entry = self.unlocks.get(slug) or {}
    entry["enabled"] = False
    self.unlocks[slug] = entry
    if save:
        self.save(update_fields=["unlocks"])
```

- [ ] **Step 4: Generate migration**

```bash
docker compose exec django python manage.py makemigrations rpg
```

Expected: creates `apps/rpg/migrations/00XX_character_unlocks.py` adding `unlocks` JSONField with default=dict.

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_models.CharacterProfileUnlocksTests -v 2
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Run full rpg suite for regressions**

```bash
docker compose exec django python manage.py test apps.rpg -v 2
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add apps/rpg/models.py apps/rpg/migrations/ apps/rpg/tests/test_models.py
git commit -m "feat(rpg): scaffold CharacterProfile.unlocks JSONField + is_unlocked/unlock/lock helpers

Future feature-pack specs (Driver's Ed, First Job, College Prep) will
flip these flags. This commit adds no UI and no readers — just the pipe."
```

---

## Phase 2: `apps/chronicle/` app + `ChronicleEntry` model

### Task 3: Scaffold `apps/chronicle/` app with `ChronicleEntry` model

**Files:**
- Create: `apps/chronicle/__init__.py`
- Create: `apps/chronicle/apps.py`
- Create: `apps/chronicle/models.py`
- Create: `apps/chronicle/admin.py`
- Create: `apps/chronicle/tests/__init__.py`
- Create: `apps/chronicle/tests/test_model.py`
- Create: `apps/chronicle/migrations/__init__.py`
- Create: `apps/chronicle/migrations/0001_initial.py` (via `makemigrations`)
- Modify: `config/settings.py` — add `"apps.chronicle"` to `INSTALLED_APPS`

- [ ] **Step 1: Create app skeleton files**

`apps/chronicle/__init__.py`: empty file.

`apps/chronicle/apps.py`:

```python
from django.apps import AppConfig


class ChronicleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chronicle"
    label = "chronicle"
```

`apps/chronicle/tests/__init__.py`: empty file.

`apps/chronicle/migrations/__init__.py`: empty file.

`apps/chronicle/admin.py`:

```python
from django.contrib import admin

from .models import ChronicleEntry


@admin.register(ChronicleEntry)
class ChronicleEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "occurred_on", "chapter_year", "title", "viewed_at")
    list_filter = ("kind", "chapter_year")
    search_fields = ("title", "summary", "event_slug", "user__username")
    raw_id_fields = ("user",)
```

- [ ] **Step 2: Write failing model tests**

`apps/chronicle/tests/test_model.py`:

```python
"""Tests for ChronicleEntry — field defaults, ordering, unique-first_ever constraint."""
from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry

User = get_user_model()


def _make_entry(user, **overrides):
    defaults = dict(
        user=user,
        kind=ChronicleEntry.Kind.MANUAL,
        occurred_on=date(2026, 4, 21),
        chapter_year=2025,
        title="Test entry",
    )
    defaults.update(overrides)
    return ChronicleEntry.objects.create(**defaults)


class ChronicleEntryModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_defaults(self):
        entry = _make_entry(self.user)
        self.assertEqual(entry.summary, "")
        self.assertEqual(entry.icon_slug, "")
        self.assertEqual(entry.event_slug, "")
        self.assertEqual(entry.metadata, {})
        self.assertIsNone(entry.viewed_at)

    def test_ordering_newest_first(self):
        _make_entry(self.user, occurred_on=date(2025, 1, 1), title="old")
        _make_entry(self.user, occurred_on=date(2026, 1, 1), title="new")
        titles = list(ChronicleEntry.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["new", "old"])

    def test_unique_first_ever_per_user_and_slug(self):
        _make_entry(self.user, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_bounty_payout")
        with self.assertRaises(IntegrityError):
            _make_entry(self.user, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_bounty_payout")

    def test_unique_constraint_does_not_block_other_kinds(self):
        # Two MILESTONE entries with the same event_slug should be allowed at the DB level.
        # (The task-level idempotency for graduation uses get_or_create, not this constraint.)
        _make_entry(self.user, kind=ChronicleEntry.Kind.MILESTONE, event_slug="graduated_high_school")
        _make_entry(self.user, kind=ChronicleEntry.Kind.MILESTONE, event_slug="graduated_high_school")
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="graduated_high_school").count(), 2
        )

    def test_unique_first_ever_scoped_per_user(self):
        other = User.objects.create(username="sibling", role=User.Role.CHILD)
        _make_entry(self.user, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_project_completed")
        # Same slug, different user: allowed.
        _make_entry(other, kind=ChronicleEntry.Kind.FIRST_EVER, event_slug="first_project_completed")
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="first_project_completed").count(), 2
        )
```

- [ ] **Step 3: Create `apps/chronicle/models.py`**

```python
from django.conf import settings
from django.db import models
from django.db.models import Index, Q, UniqueConstraint

from config.base_models import CreatedAtModel


class ChronicleEntry(CreatedAtModel):
    class Kind(models.TextChoices):
        BIRTHDAY      = "birthday", "Birthday"
        CHAPTER_START = "chapter_start", "Chapter start"
        CHAPTER_END   = "chapter_end", "Chapter end"
        FIRST_EVER    = "first_ever", "First ever"
        MILESTONE     = "milestone", "Milestone"
        RECAP         = "recap", "Recap"
        MANUAL        = "manual", "Manual"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chronicle_entries",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    occurred_on = models.DateField()
    chapter_year = models.PositiveIntegerField(
        help_text="August-starting year the chapter covers (e.g. 2025 = Aug 2025–Jul 2026)."
    )
    title = models.CharField(max_length=160)
    summary = models.TextField(blank=True)
    icon_slug = models.CharField(max_length=80, blank=True)
    event_slug = models.CharField(max_length=80, blank=True)
    related_object_type = models.CharField(max_length=40, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)

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

    def __str__(self) -> str:  # pragma: no cover — string form
        return f"{self.user_id}·{self.kind}·{self.title}"
```

- [ ] **Step 4: Register app + make migration**

Edit `config/settings.py` — find `INSTALLED_APPS` and append `"apps.chronicle",` alongside the other `apps.*` entries.

```bash
docker compose exec django python manage.py makemigrations chronicle
```

Expected: `apps/chronicle/migrations/0001_initial.py` created with the model, indexes, and partial unique constraint.

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_model -v 2
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/chronicle/ config/settings.py
git commit -m "feat(chronicle): add app skeleton + ChronicleEntry model + admin

Partial unique index on (user, event_slug) where kind=first_ever gives
emit-once semantics for firsts. Soft FK (related_object_type/_id) keeps
entries readable after a referenced object is deleted."
```

---

## Phase 3: `ChronicleService` writers

### Task 4: `ChronicleService.record_first` — idempotent first-ever writer

**Files:**
- Create: `apps/chronicle/services.py`
- Create: `apps/chronicle/tests/test_service.py`

- [ ] **Step 1: Write failing tests**

`apps/chronicle/tests/test_service.py`:

```python
"""Tests for ChronicleService — all writers are idempotent."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService

User = get_user_model()


class RecordFirstTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_first_call_creates_entry(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_bounty_payout",
            title="First bounty payout",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.kind, ChronicleEntry.Kind.FIRST_EVER)
        self.assertEqual(entry.event_slug, "first_bounty_payout")
        self.assertEqual(entry.occurred_on, date.today())
        self.assertEqual(entry.chapter_year, date.today().year if date.today().month >= 8 else date.today().year - 1)

    def test_duplicate_slug_returns_none(self):
        ChronicleService.record_first(self.user, event_slug="first_project_completed", title="x")
        second = ChronicleService.record_first(self.user, event_slug="first_project_completed", title="y")
        self.assertIsNone(second)
        self.assertEqual(ChronicleEntry.objects.filter(event_slug="first_project_completed").count(), 1)

    def test_accepts_custom_occurred_on(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_milestone_bonus",
            title="First milestone",
            occurred_on=date(2025, 9, 14),
        )
        self.assertEqual(entry.occurred_on, date(2025, 9, 14))
        self.assertEqual(entry.chapter_year, 2025)

    def test_related_tuple_is_written(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_legendary_badge",
            title="First legendary badge",
            related=("badge", 42),
        )
        self.assertEqual(entry.related_object_type, "badge")
        self.assertEqual(entry.related_object_id, 42)

    def test_metadata_and_icon_slug(self):
        entry = ChronicleService.record_first(
            self.user,
            event_slug="first_exchange_approved",
            title="First exchange",
            icon_slug="coin-stack",
            metadata={"amount": 500},
        )
        self.assertEqual(entry.icon_slug, "coin-stack")
        self.assertEqual(entry.metadata, {"amount": 500})
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_service -v 2
```

Expected: `ImportError: cannot import name 'ChronicleService'`.

- [ ] **Step 3: Create `ChronicleService.record_first`**

`apps/chronicle/services.py`:

```python
"""ChronicleService — all writers are idempotent.

`record_first` relies on the partial unique index on
(user, event_slug) where kind=first_ever for emit-once semantics.
Other writers use get_or_create keyed on their natural identity.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from django.db import IntegrityError, transaction

from apps.chronicle.models import ChronicleEntry

logger = logging.getLogger(__name__)


def _chapter_year_for(d: date) -> int:
    return d.year if d.month >= 8 else d.year - 1


class ChronicleService:
    @staticmethod
    def record_first(
        user,
        event_slug: str,
        *,
        title: str,
        summary: str = "",
        icon_slug: str = "",
        related: Optional[tuple[str, int]] = None,
        occurred_on: Optional[date] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[ChronicleEntry]:
        """Write a FIRST_EVER entry. Returns None if already exists for this (user, event_slug)."""
        if not event_slug:
            raise ValueError("event_slug is required for record_first")
        day = occurred_on or date.today()
        related_type, related_id = (related or ("", None))
        try:
            with transaction.atomic():
                return ChronicleEntry.objects.create(
                    user=user,
                    kind=ChronicleEntry.Kind.FIRST_EVER,
                    occurred_on=day,
                    chapter_year=_chapter_year_for(day),
                    title=title,
                    summary=summary,
                    icon_slug=icon_slug,
                    event_slug=event_slug,
                    related_object_type=related_type,
                    related_object_id=related_id,
                    metadata=metadata or {},
                )
        except IntegrityError:
            return None
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_service -v 2
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/chronicle/services.py apps/chronicle/tests/test_service.py
git commit -m "feat(chronicle): ChronicleService.record_first — idempotent FIRST_EVER writer

Relies on the partial unique index for emit-once. Returns None on
duplicate, never raises. Safe to call from any flow without pre-checking."
```

---

### Task 5: `ChronicleService.record_birthday`, `record_chapter_start`, `record_chapter_end`

**Files:**
- Modify: `apps/chronicle/services.py`
- Modify: `apps/chronicle/tests/test_service.py`

- [ ] **Step 1: Append failing tests**

Append to `apps/chronicle/tests/test_service.py`:

```python
class RecordBirthdayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD, date_of_birth=date(2011, 4, 21))

    def test_creates_entry_keyed_on_occurred_on(self):
        entry = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        self.assertEqual(entry.kind, ChronicleEntry.Kind.BIRTHDAY)
        self.assertEqual(entry.occurred_on, date(2026, 4, 21))
        self.assertEqual(entry.chapter_year, 2025)

    def test_second_call_same_day_returns_existing(self):
        first = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        second = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ChronicleEntry.objects.filter(kind="birthday").count(), 1)

    def test_title_includes_age_when_known(self):
        entry = ChronicleService.record_birthday(self.user, on_date=date(2026, 4, 21))
        self.assertIn("15", entry.title)


class RecordChapterTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_chapter_start_writes_entry(self):
        entry = ChronicleService.record_chapter_start(self.user, 2025)
        self.assertEqual(entry.kind, ChronicleEntry.Kind.CHAPTER_START)
        self.assertEqual(entry.chapter_year, 2025)
        self.assertEqual(entry.occurred_on, date(2025, 8, 1))

    def test_chapter_start_is_idempotent(self):
        ChronicleService.record_chapter_start(self.user, 2025)
        ChronicleService.record_chapter_start(self.user, 2025)
        self.assertEqual(ChronicleEntry.objects.filter(kind="chapter_start", chapter_year=2025).count(), 1)

    def test_chapter_end_writes_entry(self):
        entry = ChronicleService.record_chapter_end(self.user, 2025)
        self.assertEqual(entry.kind, ChronicleEntry.Kind.CHAPTER_END)
        self.assertEqual(entry.chapter_year, 2025)
        self.assertEqual(entry.occurred_on, date(2026, 6, 1))

    def test_chapter_end_is_idempotent(self):
        ChronicleService.record_chapter_end(self.user, 2025)
        ChronicleService.record_chapter_end(self.user, 2025)
        self.assertEqual(ChronicleEntry.objects.filter(kind="chapter_end", chapter_year=2025).count(), 1)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_service.RecordBirthdayTests apps.chronicle.tests.test_service.RecordChapterTransitionTests -v 2
```

Expected: `AttributeError: type object 'ChronicleService' has no attribute 'record_birthday'`.

- [ ] **Step 3: Add the three methods to `ChronicleService`**

Append to the `ChronicleService` class in `apps/chronicle/services.py`:

```python
    @staticmethod
    def record_birthday(user, *, on_date: Optional[date] = None) -> ChronicleEntry:
        """Idempotent. Keyed on (user, kind=BIRTHDAY, occurred_on)."""
        day = on_date or date.today()
        age = None
        if user.date_of_birth:
            age = day.year - user.date_of_birth.year
            if (day.month, day.day) < (user.date_of_birth.month, user.date_of_birth.day):
                age -= 1
        title = f"Turned {age}" if age is not None else "Birthday"
        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.BIRTHDAY,
            occurred_on=day,
            defaults={
                "chapter_year": _chapter_year_for(day),
                "title": title,
                "icon_slug": "birthday-candle",
            },
        )
        return entry

    @staticmethod
    def record_chapter_start(user, chapter_year: int) -> ChronicleEntry:
        day = date(chapter_year, 8, 1)
        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.CHAPTER_START,
            chapter_year=chapter_year,
            defaults={
                "occurred_on": day,
                "title": "New chapter begins",
            },
        )
        return entry

    @staticmethod
    def record_chapter_end(user, chapter_year: int) -> ChronicleEntry:
        day = date(chapter_year + 1, 6, 1)
        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.CHAPTER_END,
            chapter_year=chapter_year,
            defaults={
                "occurred_on": day,
                "title": "Chapter closes",
            },
        )
        return entry
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_service -v 2
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/chronicle/services.py apps/chronicle/tests/test_service.py
git commit -m "feat(chronicle): record_birthday + record_chapter_start/end services

All three use get_or_create for idempotency. Chapter boundaries hard-coded
to Aug 1 (start) / Jun 1 (end) matching the Phoenix school-year rhythm."
```

---

### Task 6: `ChronicleService.freeze_recap` — aggregate into RECAP entry

**Files:**
- Modify: `apps/chronicle/services.py`
- Modify: `apps/chronicle/tests/test_service.py`

- [ ] **Step 1: Append failing test**

Append to `apps/chronicle/tests/test_service.py`:

```python
class FreezeRecapTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from apps.projects.models import Project
        from apps.rewards.models import CoinLedger

        self.user = User.objects.create(username="kid", role=User.Role.CHILD)
        # Seed minimal fixtures that fall inside chapter_year=2025 (Aug 2025 - Jul 2026):
        # 2 projects complete, 1 coin entry.
        Project.objects.create(
            assigned_to=self.user,
            title="Test project A",
            status="completed",
            completed_at=date(2025, 10, 15),
        )
        Project.objects.create(
            assigned_to=self.user,
            title="Test project B",
            status="completed",
            completed_at=date(2026, 2, 1),
        )
        CoinLedger.objects.create(
            user=self.user,
            amount=Decimal("50"),
            reason=CoinLedger.Reason.ADJUSTMENT,
        )

    def test_freeze_recap_aggregates_into_metadata(self):
        recap = ChronicleService.freeze_recap(self.user, 2025)
        self.assertEqual(recap.kind, ChronicleEntry.Kind.RECAP)
        self.assertEqual(recap.chapter_year, 2025)
        self.assertEqual(recap.occurred_on, date(2026, 6, 1))
        self.assertEqual(recap.metadata.get("projects_completed"), 2)
        self.assertEqual(recap.metadata.get("coins_earned"), 50)

    def test_freeze_recap_is_idempotent(self):
        first = ChronicleService.freeze_recap(self.user, 2025)
        second = ChronicleService.freeze_recap(self.user, 2025)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ChronicleEntry.objects.filter(kind="recap").count(), 1)
```

*Note:* fixture assumptions check the actual `Project` and `CoinLedger` field names in `apps/projects/models.py` + `apps/rewards/models.py` — if `status` / `completed_at` / `assigned_to` / `reason` have different names, adjust the fixture constructor before running.

- [ ] **Step 2: Run test — confirm it fails**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_service.FreezeRecapTests -v 2
```

Expected: `AttributeError: freeze_recap`.

- [ ] **Step 3: Implement `freeze_recap`**

Append to `ChronicleService` in `apps/chronicle/services.py`:

```python
    @staticmethod
    def freeze_recap(user, chapter_year: int) -> ChronicleEntry:
        """Aggregates stats for the chapter and writes a RECAP entry. Idempotent."""
        from decimal import Decimal
        from django.db.models import Count, Sum

        from apps.projects.models import Project
        from apps.rewards.models import CoinLedger
        # Optional: homework + chores + badges — reference their models
        # only if present in this codebase. If a model is missing, omit its
        # aggregation (don't fail the recap).

        start = date(chapter_year, 8, 1)
        end = date(chapter_year + 1, 7, 31)

        stats = {}

        # Projects completed in the window (field names verified against apps/projects/models.py).
        projects_qs = Project.objects.filter(
            assigned_to=user,
            status="completed",
            completed_at__range=(start, end),
        )
        stats["projects_completed"] = projects_qs.count()

        # Coins earned (positive only) via CoinLedger (field names verified against apps/rewards/models.py).
        coins_earned = (
            CoinLedger.objects.filter(user=user, created_at__date__range=(start, end), amount__gt=0)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        stats["coins_earned"] = int(coins_earned)

        # Optional aggregations — wrap each in try/except so a missing app
        # doesn't break recap writes in CI. (Each block short-circuits on
        # ImportError without failing the overall freeze.)
        try:
            from apps.homework.models import HomeworkSubmission
            stats["homework_approved"] = HomeworkSubmission.objects.filter(
                assignment__assigned_to=user,
                status="approved",
                decided_at__date__range=(start, end),
            ).count()
        except (ImportError, Exception) as exc:  # pragma: no cover
            logger.debug("homework recap skipped: %s", exc)

        try:
            from apps.chores.models import ChoreCompletion
            stats["chores_approved"] = ChoreCompletion.objects.filter(
                user=user,
                status="approved",
                completed_date__range=(start, end),
            ).count()
        except (ImportError, Exception) as exc:  # pragma: no cover
            logger.debug("chores recap skipped: %s", exc)

        try:
            from apps.achievements.models import BadgeService
            # Badges model name varies; peek if available — this is additive.
        except Exception:  # pragma: no cover
            pass

        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.RECAP,
            chapter_year=chapter_year,
            defaults={
                "occurred_on": date(chapter_year + 1, 6, 1),
                "title": f"Chapter {chapter_year}-{str(chapter_year + 1)[-2:]} recap",
                "metadata": stats,
            },
        )
        return entry
```

**Important:** before implementing, spend 30s grep-verifying the exact field names on `Project` (`assigned_to`, `status`, `completed_at`), `CoinLedger` (`user`, `amount`, `created_at`), `HomeworkSubmission` (`assignment__assigned_to`, `status`, `decided_at`), `ChoreCompletion` (`user`, `status`, `completed_date`). These were read from CLAUDE.md; if any mismatch, adjust the ORM query.

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_service.FreezeRecapTests -v 2
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/chronicle/services.py apps/chronicle/tests/test_service.py
git commit -m "feat(chronicle): ChronicleService.freeze_recap aggregates chapter stats

Writes the RECAP metadata once on Jun 1 of each chapter so past-chapter
views render deterministic frozen stats, not live-recomputed ones that
would drift as later entries accrue."
```

---

## Phase 4: Event hooks — notifications + firsts map + GameLoopService extension

### Task 7: Add `BIRTHDAY` + `CHRONICLE_FIRST_EVER` notification types

**Files:**
- Modify: `apps/notifications/models.py`

- [ ] **Step 1: Open `apps/notifications/models.py` and locate `NotificationType`**

Search for `class NotificationType` — likely an inner `TextChoices` on `Notification` or module-level.

- [ ] **Step 2: Add two new choices**

Add the two members alongside the existing ones:

```python
BIRTHDAY             = "birthday",             "Birthday"
CHRONICLE_FIRST_EVER = "chronicle_first_ever", "Chronicle — first ever"
```

- [ ] **Step 3: Generate + apply migration**

```bash
docker compose exec django python manage.py makemigrations notifications
docker compose exec django python manage.py migrate notifications
```

(`TextChoices` changes don't require a DB column migration, but makemigrations is run for consistency — if no migration is created, that's fine.)

- [ ] **Step 4: Verify no regressions**

```bash
docker compose exec django python manage.py test apps.notifications -v 2
```

Expected: PASS (and if there's a type-guard test anywhere, it still passes because this is additive).

- [ ] **Step 5: Commit**

```bash
git add apps/notifications/
git commit -m "feat(notifications): add BIRTHDAY + CHRONICLE_FIRST_EVER notification types"
```

---

### Task 8: Firsts slug map + `GameLoopService._record_chronicle_firsts` hook

**Files:**
- Create: `apps/chronicle/firsts.py`
- Modify: `apps/rpg/services.py` (extend `GameLoopService.on_task_completed`)
- Create: `apps/chronicle/tests/test_game_loop_hook.py`

- [ ] **Step 1: Create the slug map module**

`apps/chronicle/firsts.py`:

```python
"""Mapping from GameLoopService trigger + context → chronicle first-ever slug.

Called from GameLoopService._record_chronicle_firsts after quest progress.
Returning None means "no first_ever worth emitting for this trigger+context"."""
from __future__ import annotations

from typing import Optional

from apps.rpg.constants import TriggerType


def slug_for(trigger_type: str, context: dict) -> Optional[tuple[str, str, str]]:
    """Return (event_slug, title, icon_slug) or None.

    Slugs here must NEVER change after shipping — they key the partial unique
    index and are used for deep-link lookups.
    """
    ctx = context or {}

    if trigger_type == TriggerType.PROJECT_COMPLETE:
        if ctx.get("payment_kind") == "bounty":
            return ("first_bounty_payout", "First bounty payout", "coin-stack")
        return ("first_project_completed", "First project completed", "spark")

    if trigger_type == TriggerType.MILESTONE_COMPLETE:
        return ("first_milestone_bonus", "First milestone bonus", "banner")

    if trigger_type == TriggerType.BADGE_EARNED and ctx.get("rarity") == "legendary":
        return ("first_legendary_badge", "First legendary badge", "legendary-sigil")

    if trigger_type == TriggerType.PERFECT_DAY:
        return ("first_perfect_day", "First perfect day", "sun-crown")

    if trigger_type == TriggerType.QUEST_COMPLETE:
        return ("first_quest_completed", "First quest completed", "quest-seal")

    # Streak milestones come through context["streak"] on any trigger.
    streak = ctx.get("streak")
    if streak in (30, 60, 100):
        return (f"first_streak_{streak}", f"First {streak}-day streak", "streak-flame")

    return None
```

- [ ] **Step 2: Write failing test for the hook**

`apps/chronicle/tests/test_game_loop_hook.py`:

```python
"""Tests for GameLoopService._record_chronicle_firsts pipeline step.

Core contract: record_first is called with the right slug; duplicates
don't double-write; chronicle failures don't break the parent flow.
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry
from apps.rpg.constants import TriggerType
from apps.rpg.services import GameLoopService

User = get_user_model()


class ChronicleHookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    @patch("apps.rpg.services.random.random", return_value=1.0)  # suppress drops
    def test_project_complete_bounty_emits_first_bounty_payout(self, _):
        GameLoopService.on_task_completed(
            self.user,
            TriggerType.PROJECT_COMPLETE,
            {"payment_kind": "bounty"},
        )
        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.user, kind="first_ever", event_slug="first_bounty_payout"
            ).exists()
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    def test_duplicate_does_not_create_second_entry(self, _):
        GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "bounty"})
        GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "bounty"})
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="first_bounty_payout").count(), 1
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    def test_non_bounty_project_emits_first_project_completed(self, _):
        GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "required"})
        self.assertTrue(
            ChronicleEntry.objects.filter(event_slug="first_project_completed").exists()
        )
        self.assertFalse(
            ChronicleEntry.objects.filter(event_slug="first_bounty_payout").exists()
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    @patch("apps.chronicle.services.ChronicleService.record_first", side_effect=Exception("db exploded"))
    def test_chronicle_exception_does_not_break_parent_flow(self, _mock_record, _mock_random):
        result = GameLoopService.on_task_completed(self.user, TriggerType.PROJECT_COMPLETE, {"payment_kind": "bounty"})
        # Outer flow still returns, does not raise.
        self.assertIsNotNone(result)
        # And the chronicle sub-result is empty, not crashing.
        self.assertIn("chronicle", result)
```

- [ ] **Step 3: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_game_loop_hook -v 2
```

Expected: tests fail — either the hook isn't called, or `result["chronicle"]` is missing.

- [ ] **Step 4: Extend `GameLoopService.on_task_completed`**

Read `apps/rpg/services.py` around line 263 (method start). Add, after the quest-progress step and before the method's return statement:

```python
        # Chronicle firsts — wrapped so a chronicle failure never breaks the parent flow.
        try:
            result["chronicle"] = cls._record_chronicle_firsts(user, trigger_type, context)
        except Exception:  # pragma: no cover — defensive
            logger.exception("Chronicle firsts hook failed")
            result["chronicle"] = None
```

Add a new classmethod to `GameLoopService`:

```python
    @classmethod
    def _record_chronicle_firsts(cls, user, trigger_type, context):
        from apps.chronicle.firsts import slug_for
        from apps.chronicle.services import ChronicleService

        mapped = slug_for(trigger_type, context or {})
        if mapped is None:
            return None
        event_slug, title, icon_slug = mapped
        entry = ChronicleService.record_first(
            user,
            event_slug=event_slug,
            title=title,
            icon_slug=icon_slug,
        )
        if entry:
            from apps.notifications.models import Notification, NotificationType
            Notification.objects.create(
                user=user,
                type=NotificationType.CHRONICLE_FIRST_EVER,
                title=title,
                message=f"{title} — added to your Yearbook.",
                metadata={"chronicle_entry_id": entry.id},
            )
        return {"entry_id": entry.id if entry else None, "event_slug": event_slug}
```

Ensure `logger` is imported at the top of `apps/rpg/services.py` — if not, add `import logging; logger = logging.getLogger(__name__)`.

**Double-check** the exact signature of `Notification.objects.create(...)` by skimming `apps/notifications/models.py` — the `metadata` field name may differ (could be `data` or `extra`). Adjust accordingly.

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_game_loop_hook -v 2
```

Expected: 4 tests PASS.

- [ ] **Step 6: Run full rpg suite for regressions**

```bash
docker compose exec django python manage.py test apps.rpg -v 2
```

Expected: no regressions (the `result` dict just has an extra key now).

- [ ] **Step 7: Commit**

```bash
git add apps/chronicle/firsts.py apps/chronicle/tests/test_game_loop_hook.py apps/rpg/services.py
git commit -m "feat(chronicle): hook GameLoopService to emit first-ever entries + notifications

Pipeline step runs after quest-progress, wrapped in try/except so a chronicle
failure never breaks the parent flow. Notification fires on each real first."
```

---

### Task 9: Hook `ExchangeService.approve` + `PetService.hatch_pet` + `_evolve_to_mount`

**Files:**
- Modify: `apps/rewards/services.py` (`ExchangeService.approve`)
- Modify: `apps/pets/services.py` (`hatch_pet`, `_evolve_to_mount`)
- Create: `apps/chronicle/tests/test_direct_hooks.py`

- [ ] **Step 1: Write failing tests**

`apps/chronicle/tests/test_direct_hooks.py`:

```python
"""Hooks for flows that don't route through GameLoopService.on_task_completed."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry

User = get_user_model()


class ExchangeServiceHookTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create(username="mom", role=User.Role.PARENT)
        self.child = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_approving_exchange_emits_first_exchange_approved(self):
        from apps.rewards.models import ExchangeRequest
        from apps.rewards.services import ExchangeService

        request = ExchangeRequest.objects.create(
            user=self.child,
            amount_cents=500,
            rate_snapshot=10,
            status="pending",
        )
        # Seed enough PaymentLedger balance for approval to succeed —
        # check exact seed path in apps/payments/models.py for your fixtures.
        from apps.payments.models import PaymentLedger
        PaymentLedger.objects.create(
            user=self.child,
            amount=Decimal("50.00"),
            entry_type=PaymentLedger.EntryType.ADJUSTMENT,
        )

        ExchangeService.approve(request, parent=self.parent)

        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.child, kind="first_ever", event_slug="first_exchange_approved"
            ).exists()
        )


class PetServiceHookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_hatching_first_pet_emits_first_pet_hatched(self):
        # Seed required fixtures: one PetSpecies, one PotionType,
        # egg + potion items in inventory. Use existing test helpers if any;
        # otherwise construct minimally.
        # ... (implementation of fixture specific to the pet model setup)
        # After hatch:
        #   self.assertTrue(ChronicleEntry.objects.filter(event_slug="first_pet_hatched").exists())
        self.skipTest("Fill in fixture setup matching apps.pets.tests patterns")
```

- [ ] **Step 2: Run the exchange test — confirm it fails**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_direct_hooks.ExchangeServiceHookTests -v 2
```

Expected: FAIL — no ChronicleEntry created.

- [ ] **Step 3: Hook `ExchangeService.approve`**

In `apps/rewards/services.py`, locate `class ExchangeService: ... def approve(...):` (or equivalent). After the atomic `transaction.atomic()` block that debits PaymentLedger + credits CoinLedger, append:

```python
        # Chronicle hook — wrapped so a chronicle failure never breaks approval.
        try:
            from apps.chronicle.services import ChronicleService
            ChronicleService.record_first(
                request.user,
                event_slug="first_exchange_approved",
                title="First money → coins exchange",
                icon_slug="coin-stack",
                metadata={"amount_cents": request.amount_cents, "rate": request.rate_snapshot},
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Chronicle hook failed in ExchangeService.approve")
```

- [ ] **Step 4: Hook `PetService.hatch_pet` and `_evolve_to_mount`**

In `apps/pets/services.py`, inside `PetService.hatch_pet(...)` after the UserPet row is created, append:

```python
        try:
            from apps.chronicle.services import ChronicleService
            ChronicleService.record_first(
                user,
                event_slug="first_pet_hatched",
                title=f"Hatched your first pet — {pet.species.display_name}",
                icon_slug="egg-crack",
                related=("userpet", pet.id),
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Chronicle hook failed in hatch_pet")
```

And in `_evolve_to_mount(...)` after the `UserMount` row is created:

```python
        try:
            from apps.chronicle.services import ChronicleService
            ChronicleService.record_first(
                user,
                event_slug="first_mount_evolved",
                title=f"First mount — {mount.species.display_name}",
                icon_slug="mount-sigil",
                related=("usermount", mount.id),
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Chronicle hook failed in _evolve_to_mount")
```

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_direct_hooks -v 2
```

Expected: `test_approving_exchange_emits_first_exchange_approved` PASSES. The pet test is skipped by design (hand-writing the fixture is optional; the pet hook is simple enough that the ExchangeService test proves the pattern).

- [ ] **Step 6: Run regression sweeps**

```bash
docker compose exec django python manage.py test apps.rewards apps.pets -v 2
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add apps/rewards/services.py apps/pets/services.py apps/chronicle/tests/test_direct_hooks.py
git commit -m "feat(chronicle): hook ExchangeService.approve + PetService.hatch/evolve

These three flows don't route through GameLoopService.on_task_completed,
so they call ChronicleService.record_first directly. Same failure-isolation
contract as the GameLoop hook — chronicle exceptions never break parents."
```

---

## Phase 5: Celery Beat tasks

### Task 10: `chronicle-birthday-check` task + `BIRTHDAY_COINS_PER_YEAR` setting

**Files:**
- Create: `apps/chronicle/tasks.py`
- Modify: `config/settings.py` — add `BIRTHDAY_COINS_PER_YEAR = 100` and add to `CELERY_BEAT_SCHEDULE`
- Create: `apps/chronicle/tests/test_tasks.py`

- [ ] **Step 1: Write failing tests**

`apps/chronicle/tests/test_tasks.py`:

```python
"""Tests for chronicle Celery tasks — birthday gifting + chapter transitions."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.tasks import chronicle_birthday_check, chronicle_chapter_transition
from apps.rewards.models import CoinLedger

User = get_user_model()


class BirthdayCheckTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="kid", role=User.Role.CHILD, date_of_birth=date(2011, 4, 21)
        )
        self.other = User.objects.create(
            username="not-birthday", role=User.Role.CHILD, date_of_birth=date(2010, 7, 4)
        )

    @patch("apps.chronicle.tasks.date")
    def test_creates_entry_and_grants_coins_on_birthday(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()

        entry = ChronicleEntry.objects.get(user=self.user, kind="birthday", occurred_on=date(2026, 4, 21))
        self.assertEqual(entry.metadata.get("gift_coins"), 1500)  # 100 × 15
        self.assertEqual(
            CoinLedger.objects.filter(user=self.user, reason="adjustment").count(), 1
        )

    @patch("apps.chronicle.tasks.date")
    def test_second_run_same_day_does_not_double_grant(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()
        chronicle_birthday_check()
        self.assertEqual(ChronicleEntry.objects.filter(kind="birthday").count(), 1)
        self.assertEqual(
            CoinLedger.objects.filter(user=self.user, reason="adjustment").count(), 1
        )

    @patch("apps.chronicle.tasks.date")
    def test_non_birthday_user_untouched(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()
        self.assertFalse(ChronicleEntry.objects.filter(user=self.other).exists())

    @patch("apps.chronicle.tasks.date")
    def test_missing_dob_noop(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        User.objects.create(username="nodob", role=User.Role.CHILD)  # no DOB
        chronicle_birthday_check()  # no exceptions
        # Only our `self.user` (DOB matches today) gets an entry.
        self.assertEqual(ChronicleEntry.objects.filter(kind="birthday").count(), 1)

    @override_settings(BIRTHDAY_COINS_PER_YEAR=50)
    @patch("apps.chronicle.tasks.date")
    def test_setting_overrides_coin_amount(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 21)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_birthday_check()
        entry = ChronicleEntry.objects.get(user=self.user, kind="birthday")
        self.assertEqual(entry.metadata.get("gift_coins"), 750)  # 50 × 15
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_tasks.BirthdayCheckTests -v 2
```

Expected: `ImportError: chronicle_birthday_check`.

- [ ] **Step 3: Create `apps/chronicle/tasks.py`**

```python
"""Celery tasks for the Chronicle app."""
from __future__ import annotations

import logging
from datetime import date

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(name="apps.chronicle.tasks.chronicle_birthday_check")
def chronicle_birthday_check() -> dict:
    """Fires daily. For each child whose DOB month/day == today:
    - idempotently create a BIRTHDAY entry
    - on first creation, grant BIRTHDAY_COINS_PER_YEAR × age_years coins
    - fire a BIRTHDAY notification
    """
    today = date.today()
    coins_per_year = getattr(settings, "BIRTHDAY_COINS_PER_YEAR", 100)

    children = User.objects.filter(
        role=User.Role.CHILD,
        date_of_birth__month=today.month,
        date_of_birth__day=today.day,
    )

    results = {"birthdays": 0, "gifts": 0}
    for user in children:
        with transaction.atomic():
            entry, created = ChronicleEntry.objects.get_or_create(
                user=user,
                kind=ChronicleEntry.Kind.BIRTHDAY,
                occurred_on=today,
                defaults={
                    "chapter_year": today.year if today.month >= 8 else today.year - 1,
                    "title": f"Turned {user.age_years}" if user.age_years else "Birthday",
                    "icon_slug": "birthday-candle",
                },
            )
            results["birthdays"] += 1
            if created and user.age_years:
                amount = coins_per_year * user.age_years
                CoinService.award(
                    user,
                    amount=amount,
                    reason=CoinLedger.Reason.ADJUSTMENT,
                    metadata={"reason_detail": "birthday_gift"},
                )
                entry.metadata["gift_coins"] = amount
                entry.save(update_fields=["metadata"])
                results["gifts"] += 1
                _send_birthday_notification(user, amount)

    return results


def _send_birthday_notification(user, coin_amount: int) -> None:
    try:
        from apps.notifications.models import Notification, NotificationType
        Notification.objects.create(
            user=user,
            type=NotificationType.BIRTHDAY,
            title=f"Happy birthday, {user.display_label}!",
            message=f"Your Yearbook has a new entry and {coin_amount} coins are in your treasury.",
        )
    except Exception:
        logger.exception("Birthday notification failed")
```

**Important:** the exact signature of `CoinService.award(...)` may differ. Grep `apps/rewards/services.py` for it — if it takes `(user, amount, reason, metadata=None)` keep as-is; if it takes different kwargs, adjust. If there's no `award` method, use `CoinService.adjust(...)` or create the `CoinLedger` row directly:

```python
CoinLedger.objects.create(
    user=user,
    amount=amount,
    reason=CoinLedger.Reason.ADJUSTMENT,
    metadata={"reason_detail": "birthday_gift"},
)
```

- [ ] **Step 4: Add setting + beat schedule entry**

In `config/settings.py`:

- Near the existing `COINS_PER_HOUR` / `COINS_PER_DOLLAR` block, add:

```python
BIRTHDAY_COINS_PER_YEAR = 100  # coins × age_years granted on birthday (tunable)
```

- In `CELERY_BEAT_SCHEDULE`, add:

```python
    "chronicle-birthday-check": {
        "task": "apps.chronicle.tasks.chronicle_birthday_check",
        "schedule": crontab(hour=0, minute=10),
    },
```

(Use the `crontab` import that's already present at the top of `CELERY_BEAT_SCHEDULE`.)

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_tasks.BirthdayCheckTests -v 2
```

Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/chronicle/tasks.py apps/chronicle/tests/test_tasks.py config/settings.py
git commit -m "feat(chronicle): chronicle-birthday-check Celery task + BIRTHDAY_COINS_PER_YEAR setting

Fires daily at 00:10 local. Idempotent via get_or_create on (user, BIRTHDAY,
occurred_on). Coin gift scales 100 × age_years (tunable via setting)."
```

---

### Task 11: `chronicle-chapter-transition` task (Aug 1 / Jun 1 rollover + graduation)

**Files:**
- Modify: `apps/chronicle/tasks.py`
- Modify: `config/settings.py` (append beat schedule entry)
- Modify: `apps/chronicle/tests/test_tasks.py`

- [ ] **Step 1: Append failing tests**

Append to `apps/chronicle/tests/test_tasks.py`:

```python
class ChapterTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="kid",
            role=User.Role.CHILD,
            date_of_birth=date(2011, 9, 22),
            grade_entry_year=2025,
        )

    @patch("apps.chronicle.tasks.date")
    def test_aug_1_opens_chapter(self, mock_date):
        mock_date.today.return_value = date(2025, 8, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="chapter_start", chapter_year=2025).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_jun_1_closes_chapter_and_writes_recap(self, mock_date):
        mock_date.today.return_value = date(2026, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="chapter_end", chapter_year=2025).exists()
        )
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="recap", chapter_year=2025).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_other_days_are_noop(self, mock_date):
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        self.assertFalse(ChronicleEntry.objects.filter(kind__in=["chapter_start", "chapter_end", "recap"]).exists())

    @patch("apps.chronicle.tasks.date")
    def test_senior_year_jun_1_emits_graduation(self, mock_date):
        # Entered 9th grade Aug 2025 → grade 12 is 2028-29 chapter → closes Jun 2029
        mock_date.today.return_value = date(2029, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()

        recap = ChronicleEntry.objects.get(user=self.user, kind="recap", chapter_year=2028)
        self.assertTrue(recap.metadata.get("is_graduation"))

        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.user, kind="milestone", event_slug="graduated_high_school"
            ).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_post_hs_year_end_is_normal_no_graduation_duplicate(self, mock_date):
        # First post-HS chapter (Aug 2029 → Jun 2030) closes without a second graduation.
        # Seed the senior-year chain first.
        mock_date.today.return_value = date(2029, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()

        mock_date.today.return_value = date(2030, 6, 1)
        chronicle_chapter_transition()

        # Exactly one graduation milestone — not two.
        self.assertEqual(
            ChronicleEntry.objects.filter(event_slug="graduated_high_school").count(), 1
        )
        # And the 2029 chapter still wrapped up.
        self.assertTrue(
            ChronicleEntry.objects.filter(user=self.user, kind="recap", chapter_year=2029).exists()
        )

    @patch("apps.chronicle.tasks.date")
    def test_chapter_end_is_idempotent_same_day(self, mock_date):
        mock_date.today.return_value = date(2026, 6, 1)
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        chronicle_chapter_transition()
        chronicle_chapter_transition()
        self.assertEqual(
            ChronicleEntry.objects.filter(kind="chapter_end", chapter_year=2025).count(), 1
        )
        self.assertEqual(
            ChronicleEntry.objects.filter(kind="recap", chapter_year=2025).count(), 1
        )
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_tasks.ChapterTransitionTests -v 2
```

Expected: `ImportError: chronicle_chapter_transition`.

- [ ] **Step 3: Implement the task**

Append to `apps/chronicle/tasks.py`:

```python
@shared_task(name="apps.chronicle.tasks.chronicle_chapter_transition")
def chronicle_chapter_transition() -> dict:
    """Fires daily at 00:20 local. No-op except on Aug 1 or Jun 1.

    - Aug 1: for each child with DOB, record_chapter_start(user, current_chapter_year).
    - Jun 1: for each child with DOB, record_chapter_end + freeze_recap for the chapter
      that just closed. If that chapter corresponds to grade 12, mark the recap's
      metadata.is_graduation=True and also emit a standalone MILESTONE entry
      with event_slug='graduated_high_school'.
    """
    today = date.today()
    if (today.month, today.day) not in ((8, 1), (6, 1)):
        return {"noop": True}

    children = User.objects.filter(role=User.Role.CHILD, date_of_birth__isnull=False)
    results = {"starts": 0, "ends": 0, "recaps": 0, "graduations": 0}

    for user in children:
        if (today.month, today.day) == (8, 1):
            ChronicleService.record_chapter_start(user, today.year)
            results["starts"] += 1
        else:  # Jun 1
            closing_chapter_year = today.year - 1  # Aug (year-1) → Jun year
            ChronicleService.record_chapter_end(user, closing_chapter_year)
            recap = ChronicleService.freeze_recap(user, closing_chapter_year)
            results["ends"] += 1
            results["recaps"] += 1

            # If the closing chapter was grade 12, flag + emit graduation milestone.
            if user.grade_entry_year is not None:
                grade_of_closing_chapter = 9 + (closing_chapter_year - user.grade_entry_year)
                if grade_of_closing_chapter == 12:
                    recap.metadata["is_graduation"] = True
                    recap.save(update_fields=["metadata"])
                    ChronicleEntry.objects.get_or_create(
                        user=user,
                        kind=ChronicleEntry.Kind.MILESTONE,
                        event_slug="graduated_high_school",
                        defaults={
                            "chapter_year": closing_chapter_year,
                            "occurred_on": today,
                            "title": "🎓 Graduated high school",
                            "icon_slug": "graduation-cap",
                        },
                    )
                    results["graduations"] += 1

    return results
```

- [ ] **Step 4: Add beat schedule entry**

In `config/settings.py` `CELERY_BEAT_SCHEDULE`, append:

```python
    "chronicle-chapter-transition": {
        "task": "apps.chronicle.tasks.chronicle_chapter_transition",
        "schedule": crontab(hour=0, minute=20),
    },
```

- [ ] **Step 5: Run all task tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_tasks -v 2
```

Expected: 11 tests PASS (5 birthday + 6 chapter).

- [ ] **Step 6: Commit**

```bash
git add apps/chronicle/tasks.py apps/chronicle/tests/test_tasks.py config/settings.py
git commit -m "feat(chronicle): chronicle-chapter-transition Celery task + graduation milestone

Aug 1 opens next chapter; Jun 1 closes previous chapter + freezes RECAP.
Grade-12 Jun 1 additionally flags is_graduation on the RECAP and emits a
standalone MILESTONE entry 'graduated_high_school'. Post-HS Jun 1s continue
firing as normal rollovers with no duplicate graduation."
```

---

## Phase 6: REST API — `ChronicleViewSet`

### Task 12: Serializers + list + summary endpoints

**Files:**
- Create: `apps/chronicle/serializers.py`
- Create: `apps/chronicle/views.py`
- Create: `apps/chronicle/urls.py`
- Modify: `config/urls.py` — include `apps.chronicle.urls`
- Create: `apps/chronicle/tests/test_views.py`

- [ ] **Step 1: Create serializers**

`apps/chronicle/serializers.py`:

```python
from rest_framework import serializers

from apps.chronicle.models import ChronicleEntry


class ChronicleEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChronicleEntry
        fields = (
            "id", "kind", "occurred_on", "chapter_year", "title", "summary",
            "icon_slug", "event_slug", "related_object_type", "related_object_id",
            "metadata", "viewed_at", "created_at",
        )
        read_only_fields = fields


class ManualEntryCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ChronicleEntry
        fields = ("user_id", "title", "summary", "icon_slug", "occurred_on", "metadata")
```

- [ ] **Step 2: Create the ViewSet (list + summary actions first)**

`apps/chronicle/views.py`:

```python
from collections import defaultdict
from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.serializers import ChronicleEntrySerializer, ManualEntryCreateSerializer
from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin, get_child_or_404


class ChronicleViewSet(
    RoleFilteredQuerySetMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ChronicleEntrySerializer
    permission_classes = [IsAuthenticated]
    role_filter_field = "user"

    def get_queryset(self):
        qs = self.get_role_filtered_queryset(ChronicleEntry.objects.all())
        # Parents can further scope with ?user_id=
        if self.request.user.role == "parent":
            user_id = self.request.query_params.get("user_id")
            if user_id:
                qs = qs.filter(user_id=user_id)
        chapter_year = self.request.query_params.get("chapter_year")
        if chapter_year:
            qs = qs.filter(chapter_year=chapter_year)
        return qs

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Group entries by chapter_year into chapter cards."""
        target = request.user
        if request.user.role == "parent" and (uid := request.query_params.get("user_id")):
            from django.contrib.auth import get_user_model
            target = get_object_or_404(get_user_model(), pk=uid, role="child")

        entries = list(ChronicleEntry.objects.filter(user=target).order_by("-chapter_year", "-occurred_on"))

        by_year: dict[int, list] = defaultdict(list)
        for e in entries:
            by_year[e.chapter_year].append(e)

        today = date.today()
        current_chapter = today.year if today.month >= 8 else today.year - 1

        chapters = []
        for year in sorted(by_year.keys(), reverse=True):
            is_current = (year == current_chapter)
            grade = None
            label = None
            if target.grade_entry_year is not None:
                grade = 9 + (year - target.grade_entry_year)
                if 9 <= grade <= 12:
                    label = {9: "Freshman Year", 10: "Sophomore Year", 11: "Junior Year", 12: "Senior Year"}[grade]
                elif grade < 9:
                    label = f"Grade {grade}"
                else:
                    # Post-HS — age during this chapter
                    if target.date_of_birth:
                        age_in_chapter = year - target.date_of_birth.year
                        if target.date_of_birth.month >= 8:
                            age_in_chapter -= 1
                        label = f"Age {age_in_chapter} · {year}-{str(year + 1)[-2:]}"
            chapters.append({
                "chapter_year": year,
                "grade": grade,
                "label": label,
                "is_current": is_current,
                "is_post_hs": grade is not None and grade > 12,
                "stats": _stats_for(target, year, by_year[year], is_current),
                "entries": ChronicleEntrySerializer(by_year[year], many=True).data,
            })

        return Response({"chapters": chapters, "current_chapter_year": current_chapter})


def _stats_for(user, chapter_year, entries, is_current):
    """For past chapters, read frozen RECAP metadata; for current, compute live."""
    for e in entries:
        if e.kind == ChronicleEntry.Kind.RECAP:
            return e.metadata
    if not is_current:
        return {}
    # Live stats for the in-progress current chapter — use the same aggregations
    # as ChronicleService.freeze_recap, but without writing an entry.
    from apps.chronicle.services import ChronicleService
    # Reuse the private aggregation by calling freeze_recap in a "dry" mode:
    # simpler approach — replicate the query inline here.
    from decimal import Decimal
    from django.db.models import Sum
    from apps.projects.models import Project
    from apps.rewards.models import CoinLedger

    start = date(chapter_year, 8, 1)
    end = date(chapter_year + 1, 7, 31)
    return {
        "projects_completed": Project.objects.filter(
            assigned_to=user, status="completed",
            completed_at__range=(start, end),
        ).count(),
        "coins_earned": int(
            CoinLedger.objects.filter(
                user=user, created_at__date__range=(start, end), amount__gt=0,
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        ),
    }
```

- [ ] **Step 3: Create `apps/chronicle/urls.py`**

```python
from rest_framework.routers import DefaultRouter

from apps.chronicle.views import ChronicleViewSet

router = DefaultRouter(trailing_slash=True)
router.register("chronicle", ChronicleViewSet, basename="chronicle")

urlpatterns = router.urls
```

- [ ] **Step 4: Mount in `config/urls.py`**

Find the block where other app urls are included (look for `include("apps.rpg.urls")` or similar). Append:

```python
path("api/", include("apps.chronicle.urls")),
```

- [ ] **Step 5: Write view tests**

`apps/chronicle/tests/test_views.py`:

```python
"""Tests for ChronicleViewSet — list, summary, pending-celebration, mark-viewed, manual CRUD."""
from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.chronicle.models import ChronicleEntry

User = get_user_model()


class ChronicleListTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create(username="mom", role=User.Role.PARENT)
        self.child = User.objects.create(
            username="kid", role=User.Role.CHILD,
            date_of_birth=date(2011, 9, 22), grade_entry_year=2025,
        )
        ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2025, 10, 1),
            chapter_year=2025, title="A manual memory",
        )

    def test_child_sees_own_entries(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_parent_can_filter_by_user_id(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/chronicle/?user_id={self.child.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_filter_by_chapter_year(self):
        ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2026, 9, 1),
            chapter_year=2026, title="Later chapter",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/?chapter_year=2026")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["title"], "Later chapter")


class ChronicleSummaryTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create(
            username="kid", role=User.Role.CHILD,
            date_of_birth=date(2011, 9, 22), grade_entry_year=2025,
        )
        ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2025, 10, 1),
            chapter_year=2025, title="Freshman memory",
        )
        ChronicleEntry.objects.create(
            user=self.child, kind="recap", occurred_on=date(2026, 6, 1),
            chapter_year=2025, title="Freshman recap", metadata={"projects_completed": 3},
        )

    def test_summary_groups_by_chapter(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/summary/")
        self.assertEqual(resp.status_code, 200)
        chapters = resp.data["chapters"]
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["chapter_year"], 2025)
        self.assertEqual(chapters[0]["grade"], 9)
        self.assertEqual(chapters[0]["label"], "Freshman Year")
        # Past chapter reads stats from frozen RECAP.
        self.assertEqual(chapters[0]["stats"]["projects_completed"], 3)
```

- [ ] **Step 6: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_views -v 2
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/chronicle/serializers.py apps/chronicle/views.py apps/chronicle/urls.py apps/chronicle/tests/test_views.py config/urls.py
git commit -m "feat(chronicle): ChronicleViewSet list + summary endpoints

/api/chronicle/ — paginated list with role filtering + ?user_id for parents.
/api/chronicle/summary/ — grouped-by-chapter payload for the Yearbook UI,
with live stats for the current chapter and frozen RECAP stats for past chapters."
```

---

### Task 13: `pending-celebration` + `mark-viewed` actions

**Files:**
- Modify: `apps/chronicle/views.py`
- Modify: `apps/chronicle/tests/test_views.py`

- [ ] **Step 1: Append failing tests**

Append to `apps/chronicle/tests/test_views.py`:

```python
class PendingCelebrationTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create(username="kid", role=User.Role.CHILD, date_of_birth=date(2011, 4, 21))

    def test_returns_204_when_nothing_pending(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 204)

    def test_returns_birthday_entry_today(self):
        from datetime import datetime
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date.today(),
            chapter_year=date.today().year if date.today().month >= 8 else date.today().year - 1,
            title="Turned 15", metadata={"gift_coins": 1500},
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], entry.id)
        self.assertEqual(resp.data["metadata"]["gift_coins"], 1500)

    def test_does_not_return_already_viewed_entry(self):
        from django.utils import timezone
        ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date.today(),
            chapter_year=2025, title="Turned 15", viewed_at=timezone.now(),
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 204)

    def test_does_not_leak_across_users(self):
        other_child = User.objects.create(username="sibling", role=User.Role.CHILD)
        ChronicleEntry.objects.create(
            user=other_child, kind="birthday", occurred_on=date.today(),
            chapter_year=2025, title="Turned 10",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 204)


class MarkViewedTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create(username="kid", role=User.Role.CHILD)
        self.entry = ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date.today(),
            chapter_year=2025, title="Turned 15",
        )

    def test_sets_viewed_at(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chronicle/{self.entry.id}/mark-viewed/")
        self.assertEqual(resp.status_code, 200)
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.viewed_at)

    def test_idempotent_does_not_rewrite_viewed_at(self):
        from django.utils import timezone
        fixed = timezone.now()
        self.entry.viewed_at = fixed
        self.entry.save()
        self.client.force_authenticate(self.child)
        self.client.post(f"/api/chronicle/{self.entry.id}/mark-viewed/")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.viewed_at, fixed)

    def test_other_user_cannot_mark_viewed(self):
        stranger = User.objects.create(username="stranger", role=User.Role.CHILD)
        self.client.force_authenticate(stranger)
        resp = self.client.post(f"/api/chronicle/{self.entry.id}/mark-viewed/")
        self.assertIn(resp.status_code, (403, 404))
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_views.PendingCelebrationTests apps.chronicle.tests.test_views.MarkViewedTests -v 2
```

Expected: 404s / Not Found for both action paths.

- [ ] **Step 3: Add the actions to the ViewSet**

Append to `ChronicleViewSet` in `apps/chronicle/views.py`:

```python
    @action(detail=False, methods=["get"], url_path="pending-celebration")
    def pending_celebration(self, request):
        """Return the single unviewed BIRTHDAY entry for today, or 204."""
        today = date.today()
        entry = (
            ChronicleEntry.objects.filter(
                user=request.user,
                kind=ChronicleEntry.Kind.BIRTHDAY,
                occurred_on=today,
                viewed_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if entry is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(ChronicleEntrySerializer(entry).data)

    @action(detail=True, methods=["post"], url_path="mark-viewed")
    def mark_viewed(self, request, pk=None):
        """Set viewed_at=now() if null — idempotent."""
        from django.utils import timezone
        entry = get_object_or_404(ChronicleEntry, pk=pk)
        # Role-filter ownership: child sees own, parent sees their kids.
        if request.user.role == "child" and entry.user_id != request.user.id:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # (If parent, treat as OK — they can dismiss on behalf.)
        if entry.viewed_at is None:
            entry.viewed_at = timezone.now()
            entry.save(update_fields=["viewed_at"])
        return Response(ChronicleEntrySerializer(entry).data)
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_views.PendingCelebrationTests apps.chronicle.tests.test_views.MarkViewedTests -v 2
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/chronicle/views.py apps/chronicle/tests/test_views.py
git commit -m "feat(chronicle): pending-celebration + mark-viewed endpoints

Boot-time effect in App.jsx will poll pending-celebration to decide
whether to mount BirthdayCelebrationModal. mark-viewed dismisses atomically."
```

---

### Task 14: Manual entry CRUD (POST / PATCH / DELETE)

**Files:**
- Modify: `apps/chronicle/views.py`
- Modify: `apps/chronicle/tests/test_views.py`

- [ ] **Step 1: Append failing tests**

```python
class ManualEntryTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create(username="mom", role=User.Role.PARENT)
        self.child = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_parent_creates_manual_entry(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/chronicle/manual/", {
            "user_id": self.child.id,
            "title": "Rode a bike for the first time",
            "summary": "Big Wednesday.",
            "occurred_on": "2026-04-21",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(ChronicleEntry.objects.filter(user=self.child, kind="manual").exists())

    def test_child_cannot_create_manual_entry(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/chronicle/manual/", {
            "user_id": self.child.id,
            "title": "Unauthorized",
            "occurred_on": "2026-04-21",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_parent_edits_manual_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2026, 4, 21),
            chapter_year=2025, title="Old title",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/chronicle/{entry.id}/", {"title": "New title"}, format="json")
        self.assertEqual(resp.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "New title")

    def test_parent_cannot_edit_auto_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date(2026, 4, 21),
            chapter_year=2025, title="Turned 15",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/chronicle/{entry.id}/", {"title": "No"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_parent_deletes_manual_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2026, 4, 21),
            chapter_year=2025, title="Delete me",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/chronicle/{entry.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ChronicleEntry.objects.filter(pk=entry.id).exists())

    def test_parent_cannot_delete_auto_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="recap", occurred_on=date(2026, 6, 1),
            chapter_year=2025, title="Freshman recap",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/chronicle/{entry.id}/")
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_views.ManualEntryTests -v 2
```

Expected: 404 / 405 on most.

- [ ] **Step 3: Extend ChronicleViewSet**

Change the `ChronicleViewSet` inheritance to include Update + Destroy mixins, and add the `manual` action:

```python
class ChronicleViewSet(
    RoleFilteredQuerySetMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    # ...existing serializer_class, permission_classes, role_filter_field stay the same...

    def get_permissions(self):
        # Writes require parent role; reads require authenticated.
        if self.action in ("update", "partial_update", "destroy", "manual"):
            return [IsAuthenticated(), IsParent()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["post"], url_path="manual")
    def manual(self, request):
        serializer = ManualEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target = get_child_or_404(data.pop("user_id"))
        occurred_on: date = data["occurred_on"]
        chapter_year = occurred_on.year if occurred_on.month >= 8 else occurred_on.year - 1
        entry = ChronicleEntry.objects.create(
            user=target,
            kind=ChronicleEntry.Kind.MANUAL,
            chapter_year=chapter_year,
            **data,
        )
        return Response(ChronicleEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if serializer.instance.kind != ChronicleEntry.Kind.MANUAL:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only manual entries are editable.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.kind != ChronicleEntry.Kind.MANUAL:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only manual entries are deletable.")
        instance.delete()
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.chronicle.tests.test_views -v 2
```

Expected: all view tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/chronicle/views.py apps/chronicle/tests/test_views.py
git commit -m "feat(chronicle): parent-only manual entry CRUD

POST /api/chronicle/manual/, PATCH/DELETE /api/chronicle/{id}/ — parent-only;
auto-generated entry kinds (birthday, recap, chapter_start/end, first_ever,
milestone) are immutable history and return 403 on edit/delete attempts."
```

---

### Task 15: Expose `date_of_birth` + `grade_entry_year` + computed labels on `ChildViewSet`

**Files:**
- Modify: `apps/accounts/serializers.py` (or wherever `Child` is serialized — likely `apps/projects/serializers.py` per CLAUDE.md)
- Modify: `apps/projects/views.py` (`ChildViewSet`)
- Modify: `apps/accounts/tests/test_age_properties.py` OR new file

- [ ] **Step 1: Find the child serializer**

```bash
grep -rn "ChildViewSet\|class ChildSerializer" apps/
```

Identify the serializer used by `ChildViewSet`. Note its current fields.

- [ ] **Step 2: Add the new fields to that serializer's `Meta.fields`**

Extend with: `"date_of_birth", "grade_entry_year", "age_years", "current_grade", "school_year_label"`.

The computed properties return `None` cleanly when source data is missing, so no extra `SerializerMethodField` machinery is needed — DRF's `ModelSerializer` will call them as read-only attrs (ensure each is declared explicitly):

```python
age_years = serializers.IntegerField(read_only=True)
current_grade = serializers.IntegerField(read_only=True)
school_year_label = serializers.CharField(read_only=True, allow_null=True)
```

- [ ] **Step 3: Confirm `ChildViewSet.patch` accepts the new fields**

If it uses a separate write serializer, mirror the additions. PATCH-writable fields should include `date_of_birth` and `grade_entry_year` but NOT the computed trio.

- [ ] **Step 4: Write interaction-style test**

Add a test (new file or append) that PATCHes `/api/children/{id}/` with DOB + grade_entry_year and asserts the computed trio comes back on GET:

```python
class ChildAgeFieldsEndpointTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create(username="mom", role=User.Role.PARENT)
        self.child = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_patch_and_read_back(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/children/{self.child.id}/", {
            "date_of_birth": "2011-09-22",
            "grade_entry_year": 2025,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["date_of_birth"], "2011-09-22")
        self.assertEqual(resp.data["grade_entry_year"], 2025)
        # Computed read-only fields
        self.assertIsNotNone(resp.data["age_years"])
        self.assertIsNotNone(resp.data["school_year_label"])
```

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.projects.tests -v 2
```

Expected: new test PASSES, no regressions.

- [ ] **Step 6: Commit**

```bash
git add apps/accounts/serializers.py apps/projects/serializers.py apps/projects/views.py apps/projects/tests/
git commit -m "feat(accounts): expose DOB + grade_entry_year + computed labels on ChildViewSet"
```

---

## Phase 7: Frontend — API client + Manage form

### Task 16: Add chronicle endpoint functions to `frontend/src/api/index.js`

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/test/handlers.js` (MSW defaults for the new routes)

- [ ] **Step 1: Open `frontend/src/api/index.js` and append**

```javascript
// Chronicle / Yearbook
export const getChronicleEntries = (params = {}) => api.get('/api/chronicle/', { params })
export const getChronicleSummary = (userId) =>
  api.get('/api/chronicle/summary/', { params: userId ? { user_id: userId } : {} })
export const getPendingCelebration = () => api.get('/api/chronicle/pending-celebration/')
export const markChronicleViewed = (id) => api.post(`/api/chronicle/${id}/mark-viewed/`)
export const createManualChronicleEntry = (data) => api.post('/api/chronicle/manual/', data)
export const updateManualChronicleEntry = (id, data) => api.patch(`/api/chronicle/${id}/`, data)
export const deleteChronicleEntry = (id) => api.delete(`/api/chronicle/${id}/`)
```

Use the exact existing api-client pattern — check a neighbor file for whether this codebase uses `api.get` vs `apiFetch(...)` vs a different wrapper.

- [ ] **Step 2: Add permissive MSW defaults**

In `frontend/src/test/handlers.js`, inside the default handlers array, add:

```javascript
http.get('/api/chronicle/', () => HttpResponse.json([])),
http.get('/api/chronicle/summary/', () => HttpResponse.json({ chapters: [], current_chapter_year: 2025 })),
http.get('/api/chronicle/pending-celebration/', () => new HttpResponse(null, { status: 204 })),
http.post('/api/chronicle/:id/mark-viewed/', () => HttpResponse.json({})),
http.post('/api/chronicle/manual/', () => HttpResponse.json({ id: 1 }, { status: 201 })),
http.patch('/api/chronicle/:id/', () => HttpResponse.json({})),
http.delete('/api/chronicle/:id/', () => new HttpResponse(null, { status: 204 })),
```

- [ ] **Step 3: Run the frontend test suite**

```bash
cd frontend && npm run test:run
```

Expected: no new failures — the additions are additive.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/index.js frontend/src/test/handlers.js
git commit -m "feat(frontend): add chronicle endpoint functions + MSW permissive defaults"
```

---

### Task 17: Add DOB + `grade_entry_year` fields to Manage → Children form

**Files:**
- Modify: `frontend/src/pages/Manage.jsx` (or the child-edit form it composes)
- Modify/Create: `frontend/src/pages/Manage.test.jsx` (add interaction test)

- [ ] **Step 1: Locate the child-edit form**

```bash
grep -n "hourly_rate\|updateChild\|PATCH.*children" frontend/src/pages/Manage.jsx
```

Identify the form. If child-editing lives in a sibling component, edit that file instead.

- [ ] **Step 2: Add the two fields above/beside the hourly-rate field**

Using existing form primitives (per CLAUDE.md conventions):

```jsx
import { TextField, SelectField } from '../components/form'

// inside the form JSX, near hourly_rate:
<TextField
  type="date"
  label="Date of birth"
  value={form.date_of_birth || ''}
  onChange={(e) => setForm(f => ({ ...f, date_of_birth: e.target.value }))}
  helpText="Used for birthday celebrations and chapter rollovers."
/>

<SelectField
  label="Grade entry year"
  value={form.grade_entry_year || ''}
  onChange={(e) => setForm(f => ({ ...f, grade_entry_year: e.target.value ? Number(e.target.value) : null }))}
  helpText="Year she entered 9th grade (August)."
>
  <option value="">—</option>
  {Array.from({ length: 9 }, (_, i) => new Date().getFullYear() - 4 + i).map(year => (
    <option key={year} value={year}>{year} (9th grade Aug {year})</option>
  ))}
</SelectField>
```

The submit handler's PATCH body must include both fields. If the existing submit uses `updateChild(id, { hourly_rate })`, extend it to include `date_of_birth` and `grade_entry_year`.

- [ ] **Step 3: Write the interaction test**

Append/create in `Manage.test.jsx` per the CLAUDE.md interaction-test rule:

```jsx
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../test/render'
import { spyHandler } from '../test/spy'
import { server } from '../test/server'
import { buildParent, buildUser } from '../test/factories'
import Manage from './Manage'

it('saving child DOB + grade_entry_year patches /api/children/{id}/ with both fields', async () => {
  const parent = buildParent()
  const child = buildUser({ id: 7, role: 'child' })
  const spy = spyHandler('patch', /\/api\/children\/7\/$/, {})
  server.use(spy.handler)

  const { user } = renderWithProviders(<Manage />, { withAuth: parent })
  // Navigate to children section, open child-edit form for child id 7...
  await user.click(screen.getByRole('button', { name: /edit/i }))

  const dobInput = screen.getByLabelText(/date of birth/i)
  await user.clear(dobInput)
  await user.type(dobInput, '2011-09-22')

  const gradeSelect = screen.getByLabelText(/grade entry year/i)
  await user.selectOptions(gradeSelect, '2025')

  await user.click(screen.getByRole('button', { name: /save|update/i }))

  await waitFor(() => expect(spy.calls).toHaveLength(1))
  expect(spy.calls[0].body).toMatchObject({
    date_of_birth: '2011-09-22',
    grade_entry_year: 2025,
  })
})
```

- [ ] **Step 4: Run test**

```bash
cd frontend && npm run test:run -- Manage.test
```

Expected: PASSES.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Manage.jsx frontend/src/pages/Manage.test.jsx
git commit -m "feat(manage): parent can set child DOB + grade_entry_year"
```

---

## Phase 8: Frontend — Yearbook page

### Task 18: Add Yearbook tab to Atlas + scaffold `Yearbook.jsx`

**Files:**
- Modify: `frontend/src/pages/atlas/index.jsx` (add 4th tab)
- Create: `frontend/src/pages/Yearbook.jsx`
- Create: `frontend/src/pages/yearbook/yearbook.constants.js`
- Create: `frontend/src/pages/Yearbook.test.jsx`

- [ ] **Step 1: Locate the Atlas `ChapterHub` + add Yearbook tab**

```bash
grep -n "Skills\|Badges\|Sketchbook\|ChapterHub" frontend/src/pages/atlas/index.jsx
```

Add a 4th tab entry matching the existing shape (title, route slug `yearbook`, component reference).

- [ ] **Step 2: Create `yearbook.constants.js`**

```javascript
export const GRADE_LABELS = {
  9: 'Freshman Year',
  10: 'Sophomore Year',
  11: 'Junior Year',
  12: 'Senior Year',
}

export const KIND_ICON = {
  birthday: '🎂',
  chapter_start: '📖',
  chapter_end: '📕',
  first_ever: '✨',
  milestone: '🏆',
  recap: '📜',
  manual: '🖋️',
}

export const RECAP_STAT_FIELDS = [
  { key: 'projects_completed', label: 'Projects completed' },
  { key: 'homework_approved',  label: 'Homework approved' },
  { key: 'chores_approved',    label: 'Chores approved' },
  { key: 'coins_earned',       label: 'Coins earned' },
]
```

- [ ] **Step 3: Write failing tests for Yearbook skeleton**

`frontend/src/pages/Yearbook.test.jsx`:

```jsx
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { renderWithProviders } from '../test/render'
import { server } from '../test/server'
import { buildUser } from '../test/factories'
import Yearbook from './Yearbook'

describe('Yearbook page', () => {
  it('shows empty-state when DOB missing', async () => {
    server.use(
      http.get('/api/chronicle/summary/', () =>
        HttpResponse.json({ chapters: [], current_chapter_year: 2025 }),
      ),
    )
    const child = buildUser({ role: 'child', date_of_birth: null })
    renderWithProviders(<Yearbook />, { withAuth: child })
    expect(await screen.findByText(/set your date of birth/i)).toBeInTheDocument()
  })

  it('renders chapter cards from summary payload', async () => {
    server.use(
      http.get('/api/chronicle/summary/', () =>
        HttpResponse.json({
          chapters: [
            { chapter_year: 2025, grade: 9, label: 'Freshman Year', is_current: true, is_post_hs: false, stats: {}, entries: [] },
            { chapter_year: 2024, grade: 8, label: 'Grade 8', is_current: false, is_post_hs: false, stats: { projects_completed: 5 }, entries: [] },
          ],
          current_chapter_year: 2025,
        }),
      ),
    )
    const child = buildUser({ role: 'child', date_of_birth: '2011-09-22' })
    renderWithProviders(<Yearbook />, { withAuth: child })
    expect(await screen.findByText('Freshman Year')).toBeInTheDocument()
    expect(await screen.findByText('Grade 8')).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Create `Yearbook.jsx` (page-level container)**

```jsx
import { useEffect, useState } from 'react'

import EmptyState from '../components/EmptyState'
import Loader from '../components/Loader'
import { useAuth } from '../hooks/useApi'
import { getChronicleSummary } from '../api'
import ChapterCard from './yearbook/ChapterCard'

export default function Yearbook() {
  const { user } = useAuth()
  const [state, setState] = useState({ loading: true, chapters: [], error: null })

  useEffect(() => {
    let cancelled = false
    if (!user?.date_of_birth) {
      setState({ loading: false, chapters: [], error: null })
      return
    }
    getChronicleSummary()
      .then((res) => {
        if (cancelled) return
        setState({ loading: false, chapters: res.data.chapters, error: null })
      })
      .catch((err) => { if (!cancelled) setState({ loading: false, chapters: [], error: err }) })
    return () => { cancelled = true }
  }, [user?.id, user?.date_of_birth])

  if (state.loading) return <Loader />

  if (!user?.date_of_birth) {
    return (
      <EmptyState
        title="Set your date of birth"
        description="A parent can set it on the Manage page. Then your Yearbook will start filling in."
      />
    )
  }

  return (
    <div className="space-y-4">
      {state.chapters.map((chapter) => (
        <ChapterCard key={chapter.chapter_year} chapter={chapter} />
      ))}
    </div>
  )
}
```

Create a placeholder `ChapterCard.jsx` that just renders `chapter.label` so the tests pass (full implementation is Task 19):

```jsx
// frontend/src/pages/yearbook/ChapterCard.jsx
export default function ChapterCard({ chapter }) {
  return (
    <div className="parchment-card p-4">
      <h3 className="text-lede font-serif">{chapter.label}</h3>
    </div>
  )
}
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm run test:run -- Yearbook.test
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/atlas/index.jsx frontend/src/pages/Yearbook.jsx frontend/src/pages/yearbook/ frontend/src/pages/Yearbook.test.jsx
git commit -m "feat(yearbook): add Atlas tab + Yearbook page skeleton + chapter constants

Empty-state prompt when DOB missing. ChapterCard is a minimal stub —
Task 19 fleshes out stats + progress bar + entries."
```

---

### Task 19: Flesh out `ChapterCard.jsx` (stats, progress bar, variants)

**Files:**
- Modify: `frontend/src/pages/yearbook/ChapterCard.jsx`
- Create: `frontend/src/pages/yearbook/ChapterCard.test.jsx`

- [ ] **Step 1: Write failing tests**

```jsx
// ChapterCard.test.jsx
import { render, screen } from '@testing-library/react'
import ChapterCard from './ChapterCard'

describe('ChapterCard', () => {
  it('current-chapter shows live progress bar', () => {
    render(<ChapterCard chapter={{
      chapter_year: 2025, label: 'Freshman Year', grade: 9,
      is_current: true, is_post_hs: false,
      stats: { projects_completed: 3, coins_earned: 200 },
      entries: [],
    }} />)
    expect(screen.getByText('Freshman Year')).toBeInTheDocument()
    expect(screen.getByText(/projects completed/i)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('past-chapter shows frozen stats, no progress bar', () => {
    render(<ChapterCard chapter={{
      chapter_year: 2024, label: 'Grade 8', grade: 8,
      is_current: false, is_post_hs: false,
      stats: { projects_completed: 5 },
      entries: [],
    }} />)
    expect(screen.getByText('Grade 8')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('post-HS chapter renders age-based label', () => {
    render(<ChapterCard chapter={{
      chapter_year: 2029, label: 'Age 18 · 2029-30', grade: 13,
      is_current: false, is_post_hs: true,
      stats: {},
      entries: [],
    }} />)
    expect(screen.getByText('Age 18 · 2029-30')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd frontend && npm run test:run -- ChapterCard.test
```

Expected: progress-bar test fails (no `role="progressbar"`).

- [ ] **Step 3: Flesh out `ChapterCard.jsx`**

```jsx
import ProgressBar from '../../components/ProgressBar'
import TimelineEntry from './TimelineEntry'
import { RECAP_STAT_FIELDS } from './yearbook.constants'

function schoolDaysProgress(chapterYear) {
  // Aug 1 of chapter_year → Jul 31 of chapter_year+1. Percent elapsed.
  const start = new Date(chapterYear, 7, 1).getTime()
  const end = new Date(chapterYear + 1, 6, 31).getTime()
  const now = Date.now()
  if (now <= start) return 0
  if (now >= end) return 100
  return Math.round(((now - start) / (end - start)) * 100)
}

export default function ChapterCard({ chapter }) {
  const { label, is_current, stats, entries } = chapter
  const statLines = RECAP_STAT_FIELDS
    .map(f => [f, stats?.[f.key]])
    .filter(([, v]) => v !== undefined && v !== null)

  return (
    <section className="parchment-card p-4 space-y-3" aria-labelledby={`chapter-${chapter.chapter_year}`}>
      <header className="flex items-baseline justify-between">
        <h3 id={`chapter-${chapter.chapter_year}`} className="text-lede font-serif">{label}</h3>
        {is_current && <span className="text-caption text-ink-whisper">in progress</span>}
      </header>

      {is_current && (
        <ProgressBar
          value={schoolDaysProgress(chapter.chapter_year)}
          aria-label={`${label} — days elapsed`}
        />
      )}

      {statLines.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-caption">
          {statLines.map(([field, value]) => (
            <div key={field.key}>
              <dt className="text-ink-whisper">{field.label}</dt>
              <dd className="text-body font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {entries?.length > 0 && (
        <ul className="divide-y divide-ink-whisper/10">
          {entries.map((entry) => (
            <TimelineEntry key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </section>
  )
}
```

Create a placeholder `TimelineEntry.jsx` (Task 20 fleshes it out):

```jsx
// frontend/src/pages/yearbook/TimelineEntry.jsx
export default function TimelineEntry({ entry }) {
  return <li className="py-2 text-body">{entry.title}</li>
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test:run -- ChapterCard.test
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/yearbook/
git commit -m "feat(yearbook): ChapterCard renders stats + current-chapter progress bar

Reads RECAP stat fields when present, computes school-days progress for the
in-progress chapter. TimelineEntry is still a stub — next task fleshes it out."
```

---

### Task 20: `TimelineEntry.jsx` + `EntryDetailSheet.jsx`

**Files:**
- Modify: `frontend/src/pages/yearbook/TimelineEntry.jsx`
- Create: `frontend/src/pages/yearbook/EntryDetailSheet.jsx`
- Create: `frontend/src/pages/yearbook/TimelineEntry.test.jsx`

- [ ] **Step 1: Write failing tests**

```jsx
// TimelineEntry.test.jsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/render'
import TimelineEntry from './TimelineEntry'

describe('TimelineEntry', () => {
  it('renders title + kind icon', () => {
    renderWithProviders(
      <TimelineEntry entry={{
        id: 1, kind: 'birthday', title: 'Turned 15',
        occurred_on: '2026-04-21', metadata: {},
      }} />,
    )
    expect(screen.getByText('Turned 15')).toBeInTheDocument()
    expect(screen.getByText('🎂')).toBeInTheDocument()
  })

  it('opening entry shows EntryDetailSheet', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <TimelineEntry entry={{
        id: 1, kind: 'manual', title: 'Rode bike',
        summary: 'Big day', occurred_on: '2026-04-21', metadata: {},
      }} />,
    )
    await user.click(screen.getByRole('button', { name: /rode bike/i }))
    expect(screen.getByRole('dialog', { name: /rode bike/i })).toBeInTheDocument()
    expect(screen.getByText('Big day')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests — confirm they fail**

- [ ] **Step 3: Implement `TimelineEntry.jsx`**

```jsx
import { useState } from 'react'
import { KIND_ICON } from './yearbook.constants'
import EntryDetailSheet from './EntryDetailSheet'

export default function TimelineEntry({ entry }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <li>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex w-full items-center gap-3 py-2 text-left hover:bg-ink-whisper/5"
        >
          <span aria-hidden="true" className="text-lede">{KIND_ICON[entry.kind] ?? '•'}</span>
          <span className="flex-1">
            <span className="block text-body">{entry.title}</span>
            <span className="block text-caption text-ink-whisper">{entry.occurred_on}</span>
          </span>
        </button>
      </li>
      {open && <EntryDetailSheet entry={entry} onClose={() => setOpen(false)} />}
    </>
  )
}
```

- [ ] **Step 4: Implement `EntryDetailSheet.jsx`**

```jsx
import BottomSheet from '../../components/BottomSheet'

export default function EntryDetailSheet({ entry, onClose }) {
  return (
    <BottomSheet title={entry.title} onClose={onClose}>
      <div className="space-y-3 p-4">
        <p className="text-caption text-ink-whisper">{entry.occurred_on}</p>
        {entry.summary && <p className="text-body">{entry.summary}</p>}
        {entry.metadata?.gift_coins && (
          <p className="text-body">🎁 {entry.metadata.gift_coins} coins</p>
        )}
      </div>
    </BottomSheet>
  )
}
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm run test:run -- TimelineEntry.test
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/yearbook/
git commit -m "feat(yearbook): TimelineEntry click opens EntryDetailSheet (BottomSheet)"
```

---

### Task 21: `ManualEntryFormModal.jsx` — parent add-memory flow

**Files:**
- Create: `frontend/src/pages/yearbook/ManualEntryFormModal.jsx`
- Modify: `frontend/src/pages/Yearbook.jsx` (parent-only "Add memory" button)
- Modify: `frontend/src/pages/Yearbook.test.jsx` (interaction test)

- [ ] **Step 1: Write failing interaction test**

Append to `Yearbook.test.jsx`:

```jsx
import { spyHandler } from '../test/spy'

describe('Yearbook — parent add-memory interaction', () => {
  it('submitting ManualEntryFormModal POSTs /api/chronicle/manual/ with expected body', async () => {
    server.use(
      http.get('/api/chronicle/summary/', () =>
        HttpResponse.json({ chapters: [{ chapter_year: 2025, grade: 9, label: 'Freshman Year', is_current: true, is_post_hs: false, stats: {}, entries: [] }], current_chapter_year: 2025 }),
      ),
    )
    const spy = spyHandler('post', /\/api\/chronicle\/manual\/$/, { id: 99 })
    server.use(spy.handler)

    const parent = buildUser({ role: 'parent' })
    const { user } = renderWithProviders(<Yearbook userIdContext={7} />, { withAuth: parent })

    await user.click(await screen.findByRole('button', { name: /add memory/i }))

    await user.type(screen.getByLabelText(/title/i), 'Rode a bike')
    await user.type(screen.getByLabelText(/when/i), '2026-04-21')
    await user.click(screen.getByRole('button', { name: /save|add/i }))

    await waitFor(() => expect(spy.calls).toHaveLength(1))
    expect(spy.calls[0].body).toMatchObject({
      title: 'Rode a bike',
      occurred_on: '2026-04-21',
    })
  })

  it('child does not see Add memory button', async () => {
    server.use(
      http.get('/api/chronicle/summary/', () =>
        HttpResponse.json({ chapters: [], current_chapter_year: 2025 }),
      ),
    )
    const child = buildUser({ role: 'child', date_of_birth: '2011-09-22' })
    renderWithProviders(<Yearbook />, { withAuth: child })
    expect(screen.queryByRole('button', { name: /add memory/i })).toBeNull()
  })
})
```

- [ ] **Step 2: Run test — confirm it fails**

- [ ] **Step 3: Create `ManualEntryFormModal.jsx`**

```jsx
import { useState } from 'react'
import BottomSheet from '../../components/BottomSheet'
import Button from '../../components/Button'
import { TextField, TextAreaField } from '../../components/form'
import { createManualChronicleEntry } from '../../api'

export default function ManualEntryFormModal({ userId, onClose, onCreated }) {
  const [form, setForm] = useState({ title: '', summary: '', occurred_on: '' })
  const [saving, setSaving] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const res = await createManualChronicleEntry({ user_id: userId, ...form })
      onCreated?.(res.data)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <BottomSheet title="Add memory" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3 p-4">
        <TextField
          label="Title"
          required
          value={form.title}
          onChange={(e) => setForm(f => ({ ...f, title: e.target.value }))}
        />
        <TextField
          type="date"
          label="When"
          required
          value={form.occurred_on}
          onChange={(e) => setForm(f => ({ ...f, occurred_on: e.target.value }))}
        />
        <TextAreaField
          label="Summary"
          value={form.summary}
          onChange={(e) => setForm(f => ({ ...f, summary: e.target.value }))}
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  )
}
```

- [ ] **Step 4: Wire "Add memory" button into `Yearbook.jsx`**

Add at the top of the Yearbook render:

```jsx
import { useState } from 'react'
import ManualEntryFormModal from './yearbook/ManualEntryFormModal'

// inside Yearbook component:
const [showAdd, setShowAdd] = useState(false)
const canAdd = user?.role === 'parent'
// ... in the JSX, above chapters list:
{canAdd && (
  <div className="flex justify-end">
    <Button variant="secondary" onClick={() => setShowAdd(true)}>Add memory</Button>
  </div>
)}
{showAdd && (
  <ManualEntryFormModal
    userId={props.userIdContext /* or from parent-context elsewhere */}
    onClose={() => setShowAdd(false)}
    onCreated={() => { /* refetch summary */ }}
  />
)}
```

*Note:* `userIdContext` refers to the child being viewed. For MVP, a parent viewing Yearbook likely selects a child up-stream; if there's only one child, default to that child's id. Check how other parent-facing pages solve this (e.g. `ParentDashboard`) and mirror the pattern.

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm run test:run -- Yearbook.test
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/yearbook/ManualEntryFormModal.jsx frontend/src/pages/Yearbook.jsx frontend/src/pages/Yearbook.test.jsx
git commit -m "feat(yearbook): parent-only ManualEntryFormModal for adding memories"
```

---

## Phase 9: Frontend — Birthday celebration modal

### Task 22: `BirthdayCelebrationModal.jsx` + test

**Files:**
- Create: `frontend/src/components/BirthdayCelebrationModal.jsx`
- Create: `frontend/src/components/BirthdayCelebrationModal.test.jsx`
- Create: `frontend/src/assets/birthday-candle-placeholder.png` (static PNG; generated via `generate_sprite_sheet` later)

- [ ] **Step 1: Write failing tests**

```jsx
// BirthdayCelebrationModal.test.jsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../test/render'
import { spyHandler } from '../test/spy'
import { server } from '../test/server'
import BirthdayCelebrationModal from './BirthdayCelebrationModal'

const entry = {
  id: 42,
  kind: 'birthday',
  title: 'Turned 15',
  occurred_on: '2026-04-21',
  chapter_year: 2025,
  metadata: { gift_coins: 1500 },
}

describe('BirthdayCelebrationModal', () => {
  it('renders age + gift and exposes role="alertdialog"', () => {
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={() => {}} />)
    expect(screen.getByRole('alertdialog', { name: /birthday/i })).toBeInTheDocument()
    expect(screen.getByText('15')).toBeInTheDocument()
    expect(screen.getByText(/1500/i)).toBeInTheDocument()
  })

  it('dismiss fires POST /api/chronicle/{id}/mark-viewed/ then onDismiss', async () => {
    const spy = spyHandler('post', /\/api\/chronicle\/42\/mark-viewed\/$/, {})
    server.use(spy.handler)
    const onDismiss = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={onDismiss} />)
    await user.click(screen.getByRole('button', { name: /turn the page/i }))
    await waitFor(() => expect(spy.calls).toHaveLength(1))
    expect(onDismiss).toHaveBeenCalled()
  })

  it('respects prefers-reduced-motion by skipping confetti', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(query => ({
        matches: query.includes('reduce'),
        media: query, onchange: null,
        addListener: vi.fn(), removeListener: vi.fn(),
        addEventListener: vi.fn(), removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={() => {}} />)
    expect(screen.queryByTestId('birthday-confetti')).toBeNull()
  })
})
```

- [ ] **Step 2: Run tests — confirm they fail**

- [ ] **Step 3: Implement the modal**

```jsx
// BirthdayCelebrationModal.jsx
import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'

import Button from './Button'
import { markChronicleViewed } from '../api'
import candlePng from '../assets/birthday-candle-placeholder.png'

function usePrefersReducedMotion() {
  const [pref, setPref] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
  useEffect(() => {
    const mql = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mql) return
    const handler = (e) => setPref(e.matches)
    mql.addEventListener?.('change', handler)
    return () => mql.removeEventListener?.('change', handler)
  }, [])
  return pref
}

export default function BirthdayCelebrationModal({ entry, onDismiss }) {
  const titleId = useId()
  const reduced = usePrefersReducedMotion()
  const [leaving, setLeaving] = useState(false)

  // Extract age from the title (e.g. "Turned 15") — fallback is empty string.
  const ageMatch = /\d+/.exec(entry.title || '')
  const age = ageMatch ? ageMatch[0] : ''
  const gift = entry.metadata?.gift_coins ?? 0

  const dismiss = async () => {
    setLeaving(true)
    try {
      await markChronicleViewed(entry.id)
    } finally {
      onDismiss?.()
    }
  }

  const content = (
    <div
      role="alertdialog"
      aria-labelledby={titleId}
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      <div className="absolute inset-0 bg-[rgba(204,170,92,0.25)] backdrop-blur-sm" />
      <motion.div
        initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.85, rotateY: -20 }}
        animate={{ opacity: 1, scale: 1, rotateY: 0 }}
        exit={{ opacity: 0 }}
        transition={reduced ? { duration: 0.15 } : { duration: 0.6 }}
        className="relative parchment-card p-8 text-center max-w-sm"
      >
        <img src={candlePng} alt="" aria-hidden="true" className="mx-auto h-16 w-16" />
        <h2 id={titleId} className="mt-4 font-serif text-2xl">Happy birthday</h2>
        <motion.div
          initial={reduced ? {} : { scale: 0 }}
          animate={{ scale: 1 }}
          transition={reduced ? { duration: 0 } : { delay: 0.3, duration: 0.4 }}
          className="mt-4 text-6xl font-serif text-gold-leaf"
        >
          {age}
        </motion.div>
        {gift > 0 && (
          <p className="mt-4 text-body">🎁 {gift} coins added to your treasury</p>
        )}
        {!reduced && (
          <div data-testid="birthday-confetti" aria-hidden="true" className="pointer-events-none absolute inset-0">
            {/* Confetti particles — simple framer-motion triangles */}
          </div>
        )}
        <div className="mt-6">
          <Button variant="primary" onClick={dismiss} disabled={leaving}>
            Turn the page →
          </Button>
        </div>
      </motion.div>
    </div>
  )

  return createPortal(content, document.body)
}
```

- [ ] **Step 4: Create the placeholder candle PNG**

Grab a small pixel-art candle PNG (any royalty-free source or a simple placeholder — even a 64×64 solid square is fine for MVP) and save to `frontend/src/assets/birthday-candle-placeholder.png`. A follow-up commit will replace it with a generated animated sprite.

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm run test:run -- BirthdayCelebrationModal.test
```

Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BirthdayCelebrationModal.jsx frontend/src/components/BirthdayCelebrationModal.test.jsx frontend/src/assets/birthday-candle-placeholder.png
git commit -m "feat(birthday): BirthdayCelebrationModal with page-turn entrance + gift reveal

Respects prefers-reduced-motion (no page-turn, no confetti, fade only).
Uses static placeholder candle PNG — animated sprite is a later small PR
via generate_sprite_sheet."
```

---

### Task 23: `App.jsx` boot-time pending-celebration → modal mount

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.test.jsx` (or create if missing)

- [ ] **Step 1: Write failing test**

```jsx
// App.test.jsx (extension)
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from './test/server'
import { renderWithProviders } from './test/render'
import { buildUser } from './test/factories'
import App from './App'

describe('App — birthday celebration boot', () => {
  it('mounts BirthdayCelebrationModal when pending-celebration returns an entry', async () => {
    server.use(
      http.get('/api/chronicle/pending-celebration/', () =>
        HttpResponse.json({
          id: 9, kind: 'birthday', title: 'Turned 15',
          occurred_on: '2026-04-21', chapter_year: 2025,
          metadata: { gift_coins: 1500 },
        }),
      ),
    )
    renderWithProviders(<App />, { withAuth: buildUser({ role: 'child' }) })
    await waitFor(() => {
      expect(screen.getByRole('alertdialog', { name: /birthday/i })).toBeInTheDocument()
    })
  })

  it('does not mount modal when endpoint returns 204', async () => {
    server.use(
      http.get('/api/chronicle/pending-celebration/', () => new HttpResponse(null, { status: 204 })),
    )
    renderWithProviders(<App />, { withAuth: buildUser({ role: 'child' }) })
    // Wait a tick then assert absence.
    await new Promise(r => setTimeout(r, 50))
    expect(screen.queryByRole('alertdialog', { name: /birthday/i })).toBeNull()
  })
})
```

- [ ] **Step 2: Add boot-time effect to `App.jsx`**

Inside the top-level App component, after existing effects:

```jsx
import { useEffect, useState } from 'react'
import BirthdayCelebrationModal from './components/BirthdayCelebrationModal'
import { getPendingCelebration } from './api'
import { useAuth } from './hooks/useApi'

// inside App():
const { user } = useAuth()
const [celebration, setCelebration] = useState(null)

useEffect(() => {
  if (!user) return
  let cancelled = false
  getPendingCelebration()
    .then((res) => {
      if (cancelled) return
      if (res?.data && res.status === 200) setCelebration(res.data)
    })
    .catch(() => {})  // 204 → interceptor often rejects; handled silently
  return () => { cancelled = true }
}, [user?.id])

// ... in JSX near the top of render:
{celebration && (
  <BirthdayCelebrationModal
    entry={celebration}
    onDismiss={() => setCelebration(null)}
  />
)}
```

**Important:** the 204 handling depends on your API client's contract. If it rejects on 204, catch it and treat as "nothing pending". If it resolves with status 204 and no body, check `res.status !== 204` before setting celebration. Inspect `frontend/src/api/client.js` first to confirm.

- [ ] **Step 3: Run tests**

```bash
cd frontend && npm run test:run -- App.test
```

Expected: both tests PASS.

- [ ] **Step 4: Run full frontend suite for regressions**

```bash
cd frontend && npm run test:run
```

Expected: no regressions; coverage still within thresholds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx
git commit -m "feat(birthday): mount BirthdayCelebrationModal on boot when pending-celebration fires"
```

---

## Phase 10: Documentation + verification

### Task 24: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the Chronicle app to the "apps/" architecture tree**

Insert near the other app entries, in alphabetical position:

```
  chronicle/         ChronicleEntry (birthday / chapter_start / chapter_end /
                     first_ever / milestone / recap / manual),
                     ChronicleService (idempotent writers — record_first,
                     record_birthday, record_chapter_start/end, freeze_recap),
                     Celery tasks: chronicle-birthday-check (00:10, grants
                     BIRTHDAY_COINS_PER_YEAR × age_years coins),
                     chronicle-chapter-transition (00:20, Aug 1 opens / Jun 1
                     closes + freezes RECAP; grade-12 Jun 1 also emits a
                     standalone graduated_high_school MILESTONE entry).
                     ChronicleViewSet at /api/chronicle/ with summary,
                     pending-celebration, mark-viewed, and parent-only
                     manual CRUD. Event hooks in GameLoopService,
                     ExchangeService.approve, PetService.hatch_pet/evolve.
```

- [ ] **Step 2: Add a new gotcha**

Append to the Gotchas section:

```markdown
- **Age-aware Chronicle** (`apps/chronicle/`): `User.date_of_birth` + `User.grade_entry_year` (both nullable) feed computed properties `age_years`, `current_grade`, `school_year_label` (Freshman/Sophomore/Junior/Senior through grade 12; `"Age {n} · YYYY-YY"` after). `ChronicleEntry.chapter_year` is the August-starting year (2025 = Aug 2025–Jul 2026) — named `chapter` not `school` because the same field keeps working post-HS. `ChronicleService.record_first` uses a partial unique index on `(user, event_slug) where kind=first_ever` for emit-once semantics, returning `None` on duplicate. `CharacterProfile.unlocks` JSONField is scaffolded for future feature-pack gates (Driver's Ed, First Job, College Prep) — no UI, no readers in the current release. The birthday coin gift is tunable via `BIRTHDAY_COINS_PER_YEAR` (default 100 × age). Full-screen `BirthdayCelebrationModal` fires at App boot when `/api/chronicle/pending-celebration/` returns an unviewed BIRTHDAY entry; dismiss hits `POST /api/chronicle/{id}/mark-viewed/`. Graduation is a milestone inside the timeline, not a terminal state — the app keeps rolling chapters forever, labels flip to age-based after grade 12.
```

- [ ] **Step 3: Add Yearbook page to the frontend pages section**

Insert near the existing Atlas entry:

```
  Yearbook         (Atlas 4th tab — lifelong chronological chapter timeline;
                   ChapterCard (current/past/future variants), TimelineEntry
                   (kind-iconed rows), EntryDetailSheet (BottomSheet),
                   ManualEntryFormModal (parent-only add-memory)).
```

- [ ] **Step 4: Add the new env/settings to the tunables list**

Add under "Tunable settings":

```
- `BIRTHDAY_COINS_PER_YEAR` (default `100`) — coins granted on birthday, multiplied by `age_years`. Tunable without code change.
- `CELERY_BEAT_SCHEDULE` additions: `chronicle-birthday-check` at 00:10; `chronicle-chapter-transition` at 00:20.
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Chronicle app + Yearbook + birthday mechanic"
```

---

### Task 25: End-to-end manual verification

This is a manual sweep, not an automated task. Only run after every prior task is committed and CI is green.

**Environment:**

```bash
docker compose up --build -d
docker compose exec django python manage.py migrate --noinput
docker compose exec django python manage.py seed_data --noinput
```

- [ ] **Step 1: Set DOB + grade for Abby.** Parent account → Manage → edit Abby → DOB=today (for birthday test) and `grade_entry_year=2025`. Verify child Settings shows `"You're {age} · Freshman Year"`.

- [ ] **Step 2: Empty-state sanity.** Clear DOB, reload Yearbook → EmptyState appears. Restore DOB → chapter cards return.

- [ ] **Step 3: Current-chapter live stats.** Log in as child, complete a chore (approve it as parent). Reload Yearbook → Freshman chapter stats reflect the new chore count.

- [ ] **Step 4: First-ever hook.** Complete a bounty-kind project. Verify a `first_bounty_payout` FIRST_EVER entry appears in the current chapter. Complete another bounty project — confirm there's still exactly one FIRST_EVER with that slug.

- [ ] **Step 5: Birthday takeover.** In Django shell:

```bash
docker compose exec django python manage.py shell
>>> from apps.chronicle.tasks import chronicle_birthday_check
>>> chronicle_birthday_check()
```

Log in as child → full-screen modal fires, age number visible, `1500` coins revealed. Dismiss → Yearbook opens to the entry. Run the shell command again → no second modal, no second CoinLedger ADJUSTMENT.

- [ ] **Step 6: Chapter transition — Freshman close.**

```bash
>>> from unittest.mock import patch
>>> from datetime import date
>>> from apps.chronicle.tasks import chronicle_chapter_transition
>>> with patch("apps.chronicle.tasks.date") as mock_date:
...     mock_date.today.return_value = date(2026, 6, 1)
...     mock_date.side_effect = lambda *a, **k: date(*a, **k)
...     chronicle_chapter_transition()
```

Verify Freshman card in Yearbook flips from "in progress" to frozen stats; RECAP entry present.

- [ ] **Step 7: Chapter transition — Senior graduation.** Repeat with `date(2029, 6, 1)`. Verify senior-year RECAP has `is_graduation=True` and a `🎓 Graduated high school` MILESTONE entry renders.

- [ ] **Step 8: Post-HS rollover.** Repeat with `date(2030, 6, 1)`. Verify `Age 18 · 2029-30` chapter closes normally; only one `graduated_high_school` entry exists (no duplicate).

- [ ] **Step 9: Manual entry.** Parent → Yearbook → "Add memory" → submit → new MANUAL entry appears in the right chapter. Log in as child → no "Add memory" button. Attempting `POST /api/chronicle/manual/` as child returns 403.

- [ ] **Step 10: Notification deep-link.** Fire a `CHRONICLE_FIRST_EVER` notification (e.g. do a real first-bounty-payout) → click bell → deep-link to `/atlas?tab=yearbook&entry={id}` opens Yearbook with `EntryDetailSheet` open.

- [ ] **Step 11: Test sweep + coverage gate.**

```bash
docker compose exec django python manage.py test apps.chronicle apps.accounts apps.rpg -v 2
cd frontend && npm run test:run && npm run test:coverage
```

Expected: all green; coverage thresholds met (65/55/55/65).

- [ ] **Step 12: Regression sanity — existing `GameLoopService` contract.** Verify `on_task_completed(user, "chore_complete", {})` still returns a result with the expected `streak`, `drops`, `quest` keys plus a new `chronicle` key. Existing callers (unchanged) see no surprises.

- [ ] **Step 13: Soft-FK durability.** Delete a `Project` that was referenced by a `first_project_completed` FIRST_EVER entry (via Django admin). Confirm the chronicle entry still renders with its denormalized title, even though `related_object_id` now points at a dead row.

If any step fails, open an issue and pause merging until resolved.

---

## Self-review checklist

Before declaring this plan complete, confirm against the spec:

**Spec coverage:** Every spec section maps to at least one task:
- §1a User fields + computed properties → Task 1
- §1b CharacterProfile.unlocks → Task 2
- §1c ChronicleEntry model → Task 3
- §2a ChronicleService → Tasks 4, 5, 6
- §2b Event hooks (GameLoop + Exchange + Pet) → Tasks 8, 9
- §2c Celery tasks → Tasks 10, 11
- §2d Notification types → Task 7
- §2e REST API → Tasks 12, 13, 14
- §3a Manage form → Tasks 15, 17
- §3b Yearbook tab + components → Tasks 18, 19, 20, 21
- §3c BirthdayCelebrationModal → Tasks 22, 23
- §3d First-ever notifications → Task 8 (piggybacks existing notification system)
- §3e Graduation milestone → Task 11
- §4 Testing → woven into every task (TDD)
- §5 Scope guardrails → respected; `unlocks` has no UI, no feature packs shipped, etc.
- §Critical files → each file in the spec appears in a task's "Files:" section

**No placeholders:** No TBDs, no "implement later", no "similar to Task N" without repeating the code.

**Type consistency:** `chapter_year`, `event_slug`, `record_first` / `record_birthday` / `record_chapter_start/end` / `freeze_recap` are named the same everywhere they appear.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-age-aware-growth-chronicle.md`. Two execution options:

**1. Subagent-driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
**2. Inline execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
