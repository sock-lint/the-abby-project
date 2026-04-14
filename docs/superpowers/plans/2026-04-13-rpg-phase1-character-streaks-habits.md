# RPG Phase 1: Character Profile, Streaks & Habits — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational RPG layer — character profiles with level computation, login streak tracking with daily check-in bonuses, perfect day evaluation, and a habit tracking system with strength decay.

**Architecture:** New `apps/rpg/` Django app following existing patterns (static-method services, DRF viewsets, signal hooks). CharacterProfile as a OneToOneField to User. Game loop service as the central orchestrator called from existing signal handlers. Two new Celery Beat tasks for nightly evaluations.

**Tech Stack:** Django 5.1, DRF 3.15, Celery 5.4, React 19, Tailwind 4, Framer Motion, lucide-react

---

## File Structure

### New files to create:

```
apps/rpg/
���── __init__.py
��── apps.py
├── models.py              # CharacterProfile, Habit, HabitLog
├── services.py            # StreakService, HabitService, GameLoopService
├── serializers.py         # CharacterProfileSerializer, HabitSerializer, HabitLogSerializer
├── views.py               # CharacterViewSet, HabitViewSet
��── urls.py                # DRF router
├── admin.py               # Model registrations
├── tasks.py               # evaluate_perfect_day, decay_habit_strength
├── signals.py             # Auto-create CharacterProfile on User creation
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_services.py
│   ├── test_views.py
│   └���─ test_tasks.py
```

### Existing files to modify:

```
config/settings.py:26-49      # Add "apps.rpg" to INSTALLED_APPS
config/settings.py:309-328    # Add 2 Celery Beat tasks
config/urls.py:42-52          # Add rpg URL include
apps/projects/models.py:235   # Add new NotificationType choices
apps/projects/views.py:82-185 # Add RPG data to DashboardView response
apps/timecards/services.py    # Hook game loop into clock_out
apps/chores/services.py       # Hook game loop into approve_completion
apps/projects/signals.py      # Hook game loop into project/milestone completion
frontend/src/api/index.js     # Add RPG endpoint functions
frontend/src/App.jsx           # Add /habits route
frontend/src/components/Layout.jsx  # Add Habits nav item
frontend/src/pages/Dashboard.jsx    # Add streak flame + habit widgets
frontend/src/pages/Habits.jsx       # New page (create)
```

---

## Task 1: Create the `apps/rpg/` app skeleton

**Files:**
- Create: `apps/rpg/__init__.py`
- Create: `apps/rpg/apps.py`
- Create: `apps/rpg/admin.py`
- Create: `apps/rpg/tests/__init__.py`
- Modify: `config/settings.py:26-49`

- [ ] **Step 1: Create the app directory and boilerplate files**

```bash
mkdir -p apps/rpg/tests
```

- [ ] **Step 2: Create `apps/rpg/__init__.py`**

```python
# empty file
```

- [ ] **Step 3: Create `apps/rpg/apps.py`**

```python
from django.apps import AppConfig


class RpgConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rpg"

    def ready(self):
        import apps.rpg.signals  # noqa: F401
```

- [ ] **Step 4: Create `apps/rpg/admin.py`**

```python
from django.contrib import admin

# Models will be registered as they are created in later tasks.
```

- [ ] **Step 5: Create `apps/rpg/tests/__init__.py`**

```python
# empty file
```

- [ ] **Step 6: Register app in INSTALLED_APPS**

In `config/settings.py`, add `"apps.rpg"` after `"apps.google_integration"` in the `INSTALLED_APPS` list (after line 48):

```python
    "apps.google_integration",
    "apps.rpg",
]
```

- [ ] **Step 7: Commit**

```bash
git add apps/rpg/ config/settings.py
git commit -m "feat(rpg): scaffold apps/rpg app skeleton"
```

---

## Task 2: CharacterProfile model + migration

**Files:**
- Create: `apps/rpg/models.py`
- Create: `apps/rpg/signals.py`
- Test: `apps/rpg/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_models.py`:

```python
from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import CharacterProfile


class CharacterProfileModelTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="testchild", password="testpass", role="child",
        )

    def test_profile_auto_created_on_user_save(self):
        """CharacterProfile should be auto-created via signal."""
        self.assertTrue(
            CharacterProfile.objects.filter(user=self.child).exists(),
        )

    def test_profile_defaults(self):
        profile = self.child.character_profile
        self.assertEqual(profile.level, 0)
        self.assertEqual(profile.login_streak, 0)
        self.assertEqual(profile.longest_login_streak, 0)
        self.assertEqual(profile.perfect_days_count, 0)
        self.assertIsNone(profile.last_active_date)

    def test_str(self):
        profile = self.child.character_profile
        self.assertEqual(str(profile), "testchild (Level 0)")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_models -v2
```

Expected: `ModuleNotFoundError: No module named 'apps.rpg.models'`

- [ ] **Step 3: Create `apps/rpg/models.py`**

```python
from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel, TimestampedModel


class CharacterProfile(TimestampedModel):
    """RPG character profile linked 1:1 to a User."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="character_profile",
    )
    level = models.PositiveIntegerField(default=0)
    login_streak = models.PositiveIntegerField(default=0)
    longest_login_streak = models.PositiveIntegerField(default=0)
    last_active_date = models.DateField(null=True, blank=True)
    perfect_days_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-level"]

    def __str__(self):
        name = self.user.display_name or self.user.username
        return f"{name} (Level {self.level})"
```

- [ ] **Step 4: Create `apps/rpg/signals.py`**

```python
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="projects.User")
def create_character_profile(sender, instance, created, **kwargs):
    """Auto-create a CharacterProfile when a new User is created."""
    if created:
        from apps.rpg.models import CharacterProfile

        CharacterProfile.objects.get_or_create(user=instance)
```

- [ ] **Step 5: Run migration**

```bash
docker compose exec django python manage.py makemigrations rpg
docker compose exec django python manage.py migrate
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_models -v2
```

Expected: 3 tests pass.

- [ ] **Step 7: Register in admin**

Update `apps/rpg/admin.py`:

```python
from django.contrib import admin

from .models import CharacterProfile


@admin.register(CharacterProfile)
class CharacterProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "login_streak", "longest_login_streak", "perfect_days_count")
    list_filter = ("level",)
    readonly_fields = ("created_at", "updated_at")
```

- [ ] **Step 8: Commit**

```bash
git add apps/rpg/
git commit -m "feat(rpg): add CharacterProfile model with auto-creation signal"
```

---

## Task 3: Habit and HabitLog models

**Files:**
- Modify: `apps/rpg/models.py`
- Test: `apps/rpg/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_models.py`:

```python
from apps.rpg.models import Habit, HabitLog


class HabitModelTest(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="testparent", password="testpass", role="parent",
        )
        self.child = User.objects.create_user(
            username="testchild2", password="testpass", role="child",
        )

    def test_create_positive_habit(self):
        habit = Habit.objects.create(
            name="Read for 15 min",
            icon="📖",
            habit_type="positive",
            user=self.child,
            created_by=self.parent,
            coin_reward=1,
            xp_reward=5,
        )
        self.assertEqual(str(habit), "📖 Read for 15 min")
        self.assertEqual(habit.strength, 0)
        self.assertTrue(habit.is_active)

    def test_create_habit_log(self):
        habit = Habit.objects.create(
            name="Drink water",
            icon="💧",
            habit_type="positive",
            user=self.child,
            created_by=self.child,
        )
        log = HabitLog.objects.create(
            habit=habit,
            user=self.child,
            direction=1,
        )
        self.assertEqual(log.direction, 1)
        self.assertEqual(log.streak_at_time, 0)

    def test_habit_type_choices(self):
        for choice in ("positive", "negative", "both"):
            habit = Habit(
                name=f"Test {choice}",
                habit_type=choice,
                user=self.child,
                created_by=self.child,
            )
            habit.full_clean()  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_models.HabitModelTest -v2
```

Expected: `ImportError: cannot import name 'Habit' from 'apps.rpg.models'`

- [ ] **Step 3: Add Habit and HabitLog models**

Append to `apps/rpg/models.py`:

```python
class Habit(TimestampedModel):
    """Micro-behavior tracked with +/- taps. No approval flow."""

    class HabitType(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEGATIVE = "negative", "Negative"
        BOTH = "both", "Both"

    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=10, blank=True)
    habit_type = models.CharField(
        max_length=10, choices=HabitType.choices, default=HabitType.POSITIVE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="habits",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="created_habits",
    )
    coin_reward = models.PositiveIntegerField(default=1)
    xp_reward = models.PositiveIntegerField(default=5)
    strength = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.icon} {self.name}".strip()


class HabitLog(CreatedAtModel):
    """Single +1 or -1 tap on a habit."""

    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name="logs")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="habit_logs",
    )
    direction = models.SmallIntegerField()  # +1 or -1
    streak_at_time = models.IntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
```

- [ ] **Step 4: Run migration**

```bash
docker compose exec django python manage.py makemigrations rpg
docker compose exec django python manage.py migrate
```

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_models -v2
```

Expected: All tests pass (both CharacterProfile and Habit tests).

- [ ] **Step 6: Register Habit and HabitLog in admin**

Update `apps/rpg/admin.py` — add after CharacterProfileAdmin:

```python
from .models import CharacterProfile, Habit, HabitLog


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "habit_type", "user", "strength", "is_active")
    list_filter = ("habit_type", "is_active")


@admin.register(HabitLog)
class HabitLogAdmin(admin.ModelAdmin):
    list_display = ("habit", "user", "direction", "created_at")
    list_filter = ("direction",)
```

- [ ] **Step 7: Commit**

```bash
git add apps/rpg/
git commit -m "feat(rpg): add Habit and HabitLog models"
```

---

## Task 4: StreakService

**Files:**
- Create: `apps/rpg/services.py`
- Test: `apps/rpg/tests/test_services.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_services.py`:

```python
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import User
from apps.rpg.models import CharacterProfile
from apps.rpg.services import StreakService


class StreakServiceTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="streakchild", password="testpass", role="child",
        )
        self.profile = self.child.character_profile

    def test_record_activity_starts_streak(self):
        """First activity should set streak to 1."""
        today = timezone.localdate()
        result = StreakService.record_activity(self.child, today)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 1)
        self.assertEqual(self.profile.last_active_date, today)
        self.assertTrue(result["is_first_today"])

    def test_record_activity_same_day_not_first(self):
        """Second activity same day should not increment streak."""
        today = timezone.localdate()
        StreakService.record_activity(self.child, today)
        result = StreakService.record_activity(self.child, today)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 1)
        self.assertFalse(result["is_first_today"])

    def test_record_activity_consecutive_day(self):
        """Activity on consecutive day should increment streak."""
        yesterday = timezone.localdate() - timedelta(days=1)
        today = timezone.localdate()
        StreakService.record_activity(self.child, yesterday)
        result = StreakService.record_activity(self.child, today)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 2)
        self.assertTrue(result["is_first_today"])

    def test_record_activity_gap_resets_streak(self):
        """Activity after a missed day should reset streak to 1."""
        two_days_ago = timezone.localdate() - timedelta(days=2)
        today = timezone.localdate()
        StreakService.record_activity(self.child, two_days_ago)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 1)

        result = StreakService.record_activity(self.child, today)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 1)
        self.assertTrue(result["is_first_today"])

    def test_longest_streak_tracked(self):
        """longest_login_streak should track the all-time record."""
        base = timezone.localdate() - timedelta(days=5)
        for i in range(5):
            StreakService.record_activity(self.child, base + timedelta(days=i))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 5)
        self.assertEqual(self.profile.longest_login_streak, 5)

        # Gap
        today = timezone.localdate()
        StreakService.record_activity(self.child, today)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 1)
        self.assertEqual(self.profile.longest_login_streak, 5)  # unchanged

    def test_daily_check_in_bonus_coins(self):
        """First activity should return check-in bonus with streak scaling."""
        today = timezone.localdate()
        result = StreakService.record_activity(self.child, today)
        self.assertEqual(result["check_in_bonus_coins"], 3)  # base, streak=1

    def test_daily_check_in_bonus_scales_with_streak(self):
        """Streak multiplier should increase bonus (capped at 2x)."""
        base = timezone.localdate() - timedelta(days=10)
        for i in range(10):
            StreakService.record_activity(self.child, base + timedelta(days=i))
        today = timezone.localdate()
        result = StreakService.record_activity(self.child, today)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 11)
        # multiplier = min(1 + 11 * 0.07, 2.0) = 1.77
        expected = int(3 * 1.77)  # 5
        self.assertEqual(result["check_in_bonus_coins"], expected)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.StreakServiceTest -v2
```

Expected: `ImportError: cannot import name 'StreakService' from 'apps.rpg.services'`

- [ ] **Step 3: Implement StreakService**

Create `apps/rpg/services.py`:

```python
import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------- constants ----------
BASE_CHECK_IN_COINS = 3
STREAK_MULTIPLIER_PER_DAY = 0.07
STREAK_MULTIPLIER_CAP = 2.0


class StreakService:
    """Tracks login streaks and daily check-in bonuses."""

    @staticmethod
    @transaction.atomic
    def record_activity(user, activity_date=None):
        """Record that a user was active on a given date.

        Returns a dict with:
            is_first_today: bool — whether this is the first activity today
            check_in_bonus_coins: int — coins to award (0 if not first today)
            streak: int — current login streak after update
        """
        from apps.rpg.models import CharacterProfile

        if activity_date is None:
            activity_date = timezone.localdate()

        profile, _ = CharacterProfile.objects.select_for_update().get_or_create(
            user=user,
        )

        # Already active today — no-op
        if profile.last_active_date == activity_date:
            return {
                "is_first_today": False,
                "check_in_bonus_coins": 0,
                "streak": profile.login_streak,
            }

        # Check if consecutive
        if profile.last_active_date is not None:
            days_gap = (activity_date - profile.last_active_date).days
            if days_gap == 1:
                profile.login_streak += 1
            else:
                profile.login_streak = 1
        else:
            profile.login_streak = 1

        profile.last_active_date = activity_date

        # Track all-time record
        if profile.login_streak > profile.longest_login_streak:
            profile.longest_login_streak = profile.login_streak

        profile.save(update_fields=[
            "login_streak", "longest_login_streak", "last_active_date",
            "updated_at",
        ])

        # Calculate check-in bonus
        multiplier = min(
            1 + profile.login_streak * STREAK_MULTIPLIER_PER_DAY,
            STREAK_MULTIPLIER_CAP,
        )
        bonus_coins = int(BASE_CHECK_IN_COINS * multiplier)

        return {
            "is_first_today": True,
            "check_in_bonus_coins": bonus_coins,
            "streak": profile.login_streak,
        }
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.StreakServiceTest -v2
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/services.py apps/rpg/tests/test_services.py
git commit -m "feat(rpg): add StreakService with daily check-in bonus"
```

---

## Task 5: HabitService

**Files:**
- Modify: `apps/rpg/services.py`
- Test: `apps/rpg/tests/test_services.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_services.py`:

```python
from apps.rpg.models import Habit, HabitLog
from apps.rpg.services import HabitService


class HabitServiceTest(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="habitparent", password="testpass", role="parent",
        )
        self.child = User.objects.create_user(
            username="habitchild", password="testpass", role="child",
        )
        self.habit = Habit.objects.create(
            name="Read",
            icon="📖",
            habit_type="positive",
            user=self.child,
            created_by=self.parent,
            coin_reward=2,
            xp_reward=10,
        )

    def test_log_positive_tap(self):
        result = HabitService.log_tap(self.child, self.habit, direction=1)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 1)
        self.assertEqual(result["direction"], 1)
        self.assertEqual(result["coin_reward"], 2)
        self.assertEqual(result["xp_reward"], 10)
        self.assertEqual(HabitLog.objects.count(), 1)

    def test_log_negative_tap(self):
        neg_habit = Habit.objects.create(
            name="Snacking", icon="🍫", habit_type="negative",
            user=self.child, created_by=self.parent,
        )
        result = HabitService.log_tap(self.child, neg_habit, direction=-1)
        neg_habit.refresh_from_db()
        self.assertEqual(neg_habit.strength, -1)
        self.assertEqual(result["coin_reward"], 0)
        self.assertEqual(result["xp_reward"], 0)

    def test_multiple_taps_same_day(self):
        """Habits can be tapped multiple times per day."""
        HabitService.log_tap(self.child, self.habit, direction=1)
        HabitService.log_tap(self.child, self.habit, direction=1)
        HabitService.log_tap(self.child, self.habit, direction=1)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 3)
        self.assertEqual(HabitLog.objects.count(), 3)

    def test_decay_strength(self):
        """Habits not tapped today should decay by 1."""
        self.habit.strength = 5
        self.habit.save()
        decayed = HabitService.decay_all_habits(self.child)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 4)
        self.assertEqual(decayed, 1)

    def test_decay_does_not_affect_tapped_today(self):
        """Habits tapped today should not decay."""
        HabitService.log_tap(self.child, self.habit, direction=1)
        decayed = HabitService.decay_all_habits(self.child)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 1)  # not decayed
        self.assertEqual(decayed, 0)

    def test_invalid_direction_raises(self):
        with self.assertRaises(ValueError):
            HabitService.log_tap(self.child, self.habit, direction=2)

    def test_positive_habit_rejects_negative_tap(self):
        with self.assertRaises(ValueError):
            HabitService.log_tap(self.child, self.habit, direction=-1)

    def test_negative_habit_rejects_positive_tap(self):
        neg_habit = Habit.objects.create(
            name="Bad habit", habit_type="negative",
            user=self.child, created_by=self.parent,
        )
        with self.assertRaises(ValueError):
            HabitService.log_tap(self.child, neg_habit, direction=1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.HabitServiceTest -v2
```

Expected: `ImportError: cannot import name 'HabitService'`

- [ ] **Step 3: Implement HabitService**

Append to `apps/rpg/services.py`:

```python
from datetime import timedelta


class HabitService:
    """Manages habit logging, strength tracking, and daily decay."""

    @staticmethod
    @transaction.atomic
    def log_tap(user, habit, direction):
        """Record a +1 or -1 tap on a habit.

        Returns dict with: direction, coin_reward, xp_reward, new_strength.
        Raises ValueError for invalid direction or type mismatch.
        """
        from apps.rpg.models import HabitLog

        if direction not in (1, -1):
            raise ValueError(f"Direction must be +1 or -1, got {direction}")

        if habit.habit_type == "positive" and direction == -1:
            raise ValueError("Cannot log negative tap on a positive-only habit")
        if habit.habit_type == "negative" and direction == 1:
            raise ValueError("Cannot log positive tap on a negative-only habit")

        # Get current streak for logging context
        profile = getattr(user, "character_profile", None)
        streak = profile.login_streak if profile else 0

        HabitLog.objects.create(
            habit=habit,
            user=user,
            direction=direction,
            streak_at_time=streak,
        )

        habit.strength += direction
        habit.save(update_fields=["strength", "updated_at"])

        # Only positive taps earn rewards
        coin_reward = habit.coin_reward if direction == 1 else 0
        xp_reward = habit.xp_reward if direction == 1 else 0

        return {
            "direction": direction,
            "coin_reward": coin_reward,
            "xp_reward": xp_reward,
            "new_strength": habit.strength,
        }

    @staticmethod
    def decay_all_habits(user, target_date=None):
        """Decay strength by 1 for all habits not tapped today.

        Returns count of habits decayed.
        """
        from apps.rpg.models import Habit, HabitLog

        if target_date is None:
            target_date = timezone.localdate()

        active_habits = Habit.objects.filter(user=user, is_active=True)
        decayed = 0

        for habit in active_habits:
            tapped_today = HabitLog.objects.filter(
                habit=habit,
                user=user,
                created_at__date=target_date,
            ).exists()

            if not tapped_today and habit.strength != 0:
                if habit.strength > 0:
                    habit.strength -= 1
                else:
                    habit.strength += 1  # decay toward 0 from negative
                habit.save(update_fields=["strength", "updated_at"])
                decayed += 1

        return decayed
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.HabitServiceTest -v2
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/services.py apps/rpg/tests/test_services.py
git commit -m "feat(rpg): add HabitService with tap logging and strength decay"
```

---

## Task 6: GameLoopService (central orchestrator)

**Files:**
- Modify: `apps/rpg/services.py`
- Test: `apps/rpg/tests/test_services.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_services.py`:

```python
from apps.rpg.services import GameLoopService
from apps.rewards.models import CoinLedger


class GameLoopServiceTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="loopchild", password="testpass", role="child",
        )

    def test_on_task_completed_first_today(self):
        """First task of the day should award check-in bonus coins."""
        result = GameLoopService.on_task_completed(
            self.child, trigger_type="clock_out",
        )
        self.assertTrue(result["streak"]["is_first_today"])
        self.assertGreater(result["streak"]["check_in_bonus_coins"], 0)
        # Verify coins were actually credited
        coin_total = CoinLedger.objects.filter(user=self.child).aggregate(
            total=models.Sum("amount"),
        )["total"]
        self.assertEqual(coin_total, result["streak"]["check_in_bonus_coins"])

    def test_on_task_completed_second_today(self):
        """Second task should not award check-in bonus."""
        GameLoopService.on_task_completed(self.child, "clock_out")
        result = GameLoopService.on_task_completed(self.child, "clock_out")
        self.assertFalse(result["streak"]["is_first_today"])
        self.assertEqual(result["streak"]["check_in_bonus_coins"], 0)

    def test_on_task_completed_returns_trigger_type(self):
        result = GameLoopService.on_task_completed(
            self.child, "chore_complete",
        )
        self.assertEqual(result["trigger_type"], "chore_complete")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.GameLoopServiceTest -v2
```

Expected: `ImportError: cannot import name 'GameLoopService'`

- [ ] **Step 3: Implement GameLoopService**

Append to `apps/rpg/services.py`:

```python
from django.db import models as db_models


class GameLoopService:
    """Central orchestrator for RPG events triggered by task completion.

    Called from existing signal handlers. Coordinates streak tracking,
    check-in bonuses, and (in future phases) drop rolls, quest progress,
    and pet reactions.
    """

    @staticmethod
    @transaction.atomic
    def on_task_completed(user, trigger_type, context=None):
        """Process all RPG side effects for a completed task.

        Args:
            user: The child User who completed the action.
            trigger_type: str — e.g. 'clock_out', 'chore_complete',
                          'homework_complete', 'milestone_complete',
                          'badge_earned', 'project_complete', 'habit_log'.
            context: dict — optional metadata (project_id, etc.)

        Returns:
            dict with: trigger_type, streak, notifications
        """
        if context is None:
            context = {}

        notifications = []

        # 1. Streak update + daily check-in bonus
        streak_result = StreakService.record_activity(user)

        if streak_result["is_first_today"] and streak_result["check_in_bonus_coins"] > 0:
            from apps.rewards.models import CoinLedger
            from apps.rewards.services import CoinService

            CoinService.award_coins(
                user,
                streak_result["check_in_bonus_coins"],
                CoinLedger.Reason.ADJUSTMENT,
                description="Daily check-in bonus",
            )

            # Streak milestone notifications
            streak = streak_result["streak"]
            if streak in (3, 7, 14, 30, 60, 100):
                from apps.projects.notifications import notify

                notify(
                    user,
                    title=f"🔥 {streak}-day streak!",
                    message=f"You've been active for {streak} days in a row!",
                    notification_type="badge_earned",
                    link="/",
                )
                notifications.append(f"{streak}-day streak milestone")

        # Future phases will add:
        # 2. Drop roll (Phase 2)
        # 3. Quest progress (Phase 4)
        # 4. Pet reaction (Phase 3)

        return {
            "trigger_type": trigger_type,
            "streak": streak_result,
            "notifications": notifications,
        }
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.GameLoopServiceTest -v2
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/services.py apps/rpg/tests/test_services.py
git commit -m "feat(rpg): add GameLoopService central orchestrator"
```

---

## Task 7: Celery tasks (perfect day + habit decay)

**Files:**
- Create: `apps/rpg/tasks.py`
- Modify: `config/settings.py:309-328`
- Test: `apps/rpg/tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_tasks.py`:

```python
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import User
from apps.rpg.models import CharacterProfile, Habit
from apps.rpg.tasks import evaluate_perfect_day_task, decay_habit_strength_task


class PerfectDayTaskTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="perfectchild", password="testpass", role="child",
        )
        self.profile = self.child.character_profile

    def test_perfect_day_with_all_chores_done(self):
        """If all chores done and user was active, should award perfect day."""
        from apps.chores.models import Chore, ChoreCompletion

        chore = Chore.objects.create(
            title="Test chore", recurrence="daily",
            reward_amount=1, coin_reward=1,
            created_by=User.objects.create_user(
                username="perfectparent", password="testpass", role="parent",
            ),
        )
        ChoreCompletion.objects.create(
            chore=chore, user=self.child,
            completed_date=timezone.localdate(),
            status="approved",
            reward_amount_snapshot=1, coin_reward_snapshot=1,
        )

        # Mark user as active today
        self.profile.last_active_date = timezone.localdate()
        self.profile.login_streak = 1
        self.profile.save()

        result = evaluate_perfect_day_task()
        self.assertIn("evaluated", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)

    def test_not_perfect_if_inactive(self):
        """If user was not active today, no perfect day."""
        result = evaluate_perfect_day_task()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)


class DecayHabitStrengthTaskTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="decaychild", password="testpass", role="child",
        )
        self.parent = User.objects.create_user(
            username="decayparent", password="testpass", role="parent",
        )
        self.habit = Habit.objects.create(
            name="Test", habit_type="positive",
            user=self.child, created_by=self.parent,
            strength=5,
        )

    def test_decay_reduces_untapped_habits(self):
        result = decay_habit_strength_task()
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 4)
        self.assertIn("decayed", result)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_tasks -v2
```

Expected: `ModuleNotFoundError: No module named 'apps.rpg.tasks'`

- [ ] **Step 3: Create `apps/rpg/tasks.py`**

```python
from celery import shared_task
from django.utils import timezone


@shared_task
def evaluate_perfect_day_task():
    """Nightly task: check all children for perfect day achievement."""
    from apps.projects.models import User
    from apps.rpg.models import CharacterProfile
    from apps.chores.models import Chore, ChoreCompletion
    from apps.chores.services import ChoreService
    from apps.rewards.models import CoinLedger
    from apps.rewards.services import CoinService
    from apps.projects.notifications import notify

    today = timezone.localdate()
    children = User.objects.filter(role="child")
    awarded = 0

    for child in children:
        profile = CharacterProfile.objects.filter(user=child).first()
        if not profile or profile.last_active_date != today:
            continue  # not active today

        # Check: all daily chores completed today
        available_chores = ChoreService.get_available_chores(child, today)
        daily_chores = [c for c in available_chores if c.recurrence == Chore.Recurrence.DAILY]

        if daily_chores and not all(getattr(c, "is_done_today", False) for c in daily_chores):
            continue  # missed a chore

        # If no daily chores, still award if user was active
        # (having no chores doesn't prevent perfect day)

        profile.perfect_days_count += 1
        profile.save(update_fields=["perfect_days_count", "updated_at"])

        # Award bonus coins
        CoinService.award_coins(
            child, 15,
            CoinLedger.Reason.ADJUSTMENT,
            description="Perfect Day bonus!",
        )

        notify(
            child,
            title="⭐ Perfect Day!",
            message="You completed all your tasks today!",
            notification_type="badge_earned",
            link="/",
        )
        awarded += 1

    return f"evaluated {children.count()} children, {awarded} perfect days awarded"


@shared_task
def decay_habit_strength_task():
    """Nightly task: decay habit strength for untapped habits."""
    from apps.projects.models import User
    from apps.rpg.services import HabitService

    children = User.objects.filter(role="child")
    total_decayed = 0

    for child in children:
        decayed = HabitService.decay_all_habits(child)
        total_decayed += decayed

    return f"decayed {total_decayed} habits across {children.count()} children"
```

- [ ] **Step 4: Register tasks in Celery Beat**

In `config/settings.py`, add after the `"daily-reminders"` entry in `CELERY_BEAT_SCHEDULE` (after line 327):

```python
    "rpg-perfect-day": {
        "task": "apps.rpg.tasks.evaluate_perfect_day_task",
        "schedule": crontab(hour=23, minute=55),
    },
    "rpg-habit-decay": {
        "task": "apps.rpg.tasks.decay_habit_strength_task",
        "schedule": crontab(hour=0, minute=5),
    },
```

- [ ] **Step 5: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_tasks -v2
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/rpg/tasks.py apps/rpg/tests/test_tasks.py config/settings.py
git commit -m "feat(rpg): add perfect day evaluation and habit decay Celery tasks"
```

---

## Task 8: RPG serializers

**Files:**
- Create: `apps/rpg/serializers.py`

- [ ] **Step 1: Create serializers**

Create `apps/rpg/serializers.py`:

```python
from rest_framework import serializers

from .models import CharacterProfile, Habit, HabitLog


class CharacterProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = CharacterProfile
        fields = [
            "id", "username", "display_name",
            "level", "login_streak", "longest_login_streak",
            "last_active_date", "perfect_days_count",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_display_name(self, obj):
        return obj.user.display_name or obj.user.username


class HabitSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()

    class Meta:
        model = Habit
        fields = [
            "id", "name", "icon", "habit_type",
            "user", "created_by", "created_by_name",
            "coin_reward", "xp_reward", "strength", "color",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "strength", "color", "created_by_name",
            "created_at", "updated_at",
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.display_name or obj.created_by.username

    def get_color(self, obj):
        """Return color based on strength level."""
        s = obj.strength
        if s < -5:
            return "red-dark"
        elif s < 0:
            return "red-light"
        elif s == 0:
            return "yellow"
        elif s <= 5:
            return "green-light"
        elif s <= 10:
            return "green"
        else:
            return "blue"


class HabitWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habit
        fields = [
            "name", "icon", "habit_type", "user",
            "coin_reward", "xp_reward", "is_active",
        ]


class HabitLogSerializer(serializers.ModelSerializer):
    habit_name = serializers.CharField(source="habit.name", read_only=True)
    habit_icon = serializers.CharField(source="habit.icon", read_only=True)

    class Meta:
        model = HabitLog
        fields = [
            "id", "habit", "habit_name", "habit_icon",
            "user", "direction", "streak_at_time", "created_at",
        ]
        read_only_fields = fields
```

- [ ] **Step 2: Commit**

```bash
git add apps/rpg/serializers.py
git commit -m "feat(rpg): add DRF serializers for CharacterProfile and Habit"
```

---

## Task 9: RPG views and URLs

**Files:**
- Create: `apps/rpg/views.py`
- Create: `apps/rpg/urls.py`
- Modify: `config/urls.py:42-52`
- Test: `apps/rpg/tests/test_views.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_views.py`:

```python
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.projects.models import User
from apps.rpg.models import Habit


class CharacterViewTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="viewchild", password="testpass", role="child",
        )
        self.token = Token.objects.create(user=self.child)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_get_character_profile(self):
        response = self.client.get("/api/character/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "viewchild")
        self.assertEqual(response.data["level"], 0)
        self.assertEqual(response.data["login_streak"], 0)

    def test_get_streaks(self):
        response = self.client.get("/api/streaks/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("login_streak", response.data)
        self.assertIn("longest_login_streak", response.data)
        self.assertIn("perfect_days_count", response.data)


class HabitViewTest(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="habitviewparent", password="testpass", role="parent",
        )
        self.child = User.objects.create_user(
            username="habitviewchild", password="testpass", role="child",
        )
        self.parent_token = Token.objects.create(user=self.parent)
        self.child_token = Token.objects.create(user=self.child)
        self.parent_client = APIClient()
        self.parent_client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.parent_token.key}",
        )
        self.child_client = APIClient()
        self.child_client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.child_token.key}",
        )

    def test_parent_creates_habit(self):
        response = self.parent_client.post("/api/habits/", {
            "name": "Read",
            "icon": "📖",
            "habit_type": "positive",
            "user": self.child.pk,
            "coin_reward": 2,
            "xp_reward": 10,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Read")

    def test_child_creates_own_habit(self):
        response = self.child_client.post("/api/habits/", {
            "name": "Stretch",
            "icon": "🧘",
            "habit_type": "positive",
            "coin_reward": 1,
            "xp_reward": 5,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Habit.objects.get().user, self.child)
        self.assertEqual(Habit.objects.get().created_by, self.child)

    def test_child_logs_positive_tap(self):
        habit = Habit.objects.create(
            name="Water", icon="💧", habit_type="positive",
            user=self.child, created_by=self.parent,
        )
        response = self.child_client.post(f"/api/habits/{habit.pk}/log/", {
            "direction": 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["new_strength"], 1)

    def test_child_sees_only_own_habits(self):
        other = User.objects.create_user(
            username="otherchild", password="testpass", role="child",
        )
        Habit.objects.create(
            name="Mine", user=self.child, created_by=self.parent,
        )
        Habit.objects.create(
            name="Other", user=other, created_by=self.parent,
        )
        response = self.child_client.get("/api/habits/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Mine")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_views -v2
```

Expected: `ModuleNotFoundError` or 404 errors.

- [ ] **Step 3: Create `apps/rpg/views.py`**

```python
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import WriteReadSerializerMixin

from .models import CharacterProfile, Habit, HabitLog
from .serializers import (
    CharacterProfileSerializer,
    HabitLogSerializer,
    HabitSerializer,
    HabitWriteSerializer,
)
from .services import GameLoopService, HabitService


class CharacterView(APIView):
    """GET /api/character/ — current user's RPG profile."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _ = CharacterProfile.objects.get_or_create(user=request.user)
        return Response(CharacterProfileSerializer(profile).data)


class StreakView(APIView):
    """GET /api/streaks/ — current streak info."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _ = CharacterProfile.objects.get_or_create(user=request.user)
        return Response({
            "login_streak": profile.login_streak,
            "longest_login_streak": profile.longest_login_streak,
            "last_active_date": profile.last_active_date,
            "perfect_days_count": profile.perfect_days_count,
        })


class HabitViewSet(WriteReadSerializerMixin, viewsets.ModelViewSet):
    serializer_class = HabitSerializer
    write_serializer_class = HabitWriteSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return Habit.objects.all()
        return Habit.objects.filter(user=user)

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == "child":
            # Children can only create habits for themselves
            serializer.save(user=user, created_by=user)
        else:
            serializer.save(created_by=user)

    @action(detail=True, methods=["post"])
    def log(self, request, pk=None):
        """POST /api/habits/{id}/log/ — record a +1 or -1 tap."""
        habit = self.get_object()
        direction = request.data.get("direction")

        if direction is None:
            return Response(
                {"error": "direction is required (+1 or -1)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            direction = int(direction)
        except (ValueError, TypeError):
            return Response(
                {"error": "direction must be an integer (+1 or -1)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = HabitService.log_tap(request.user, habit, direction)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Trigger game loop for positive taps
        game_event = None
        if direction == 1:
            game_event = GameLoopService.on_task_completed(
                request.user, "habit_log", {"habit_id": habit.pk},
            )

        return Response({
            **result,
            "game_event": game_event,
        })
```

- [ ] **Step 4: Create `apps/rpg/urls.py`**

```python
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"habits", views.HabitViewSet, basename="habit")

urlpatterns = [
    path("character/", views.CharacterView.as_view(), name="character"),
    path("streaks/", views.StreakView.as_view(), name="streaks"),
    path("", include(router.urls)),
]
```

- [ ] **Step 5: Register URL in config/urls.py**

In `config/urls.py`, add after the `apps.homework.urls` include (after line 51):

```python
    path("api/", include("apps.rpg.urls")),
```

- [ ] **Step 6: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_views -v2
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps/rpg/views.py apps/rpg/urls.py config/urls.py apps/rpg/tests/test_views.py
git commit -m "feat(rpg): add character, streaks, and habits API endpoints"
```

---

## Task 10: Hook game loop into existing services

**Files:**
- Modify: `apps/timecards/services.py` (clock_out method)
- Modify: `apps/chores/services.py` (approve_completion method)
- Modify: `apps/projects/signals.py` (project/milestone completion)

- [ ] **Step 1: Write integration test**

Append to `apps/rpg/tests/test_services.py`:

```python
class GameLoopIntegrationTest(TestCase):
    """Test that the game loop is triggered from existing service flows."""

    def setUp(self):
        self.parent = User.objects.create_user(
            username="intparent", password="testpass", role="parent",
        )
        self.child = User.objects.create_user(
            username="intchild", password="testpass", role="child",
        )

    def test_game_loop_called_on_chore_approve(self):
        """Chore approval should trigger game loop and update streak."""
        from apps.chores.models import Chore, ChoreCompletion

        chore = Chore.objects.create(
            title="Test", recurrence="daily",
            reward_amount=1, coin_reward=1,
            created_by=self.parent,
        )
        completion = ChoreCompletion.objects.create(
            chore=chore, user=self.child,
            completed_date=timezone.localdate(),
            status="pending",
            reward_amount_snapshot=1, coin_reward_snapshot=1,
        )

        from apps.chores.services import ChoreService
        ChoreService.approve_completion(completion, self.parent)

        profile = self.child.character_profile
        profile.refresh_from_db()
        self.assertEqual(profile.login_streak, 1)
        self.assertEqual(profile.last_active_date, timezone.localdate())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.GameLoopIntegrationTest -v2
```

Expected: Fails because streak is still 0 (game loop not hooked in yet).

- [ ] **Step 3: Hook into ChoreService.approve_completion**

In `apps/chores/services.py`, at the end of the `approve_completion` method (after the `notify()` call), add:

```python
        # RPG game loop
        from apps.rpg.services import GameLoopService

        GameLoopService.on_task_completed(
            completion.user, "chore_complete", {"chore_id": completion.chore_id},
        )
```

- [ ] **Step 4: Hook into ClockService.clock_out**

In `apps/timecards/services.py`, at the end of the `clock_out` method (after the `AwardService.grant()` call), add:

```python
        # RPG game loop
        from apps.rpg.services import GameLoopService

        GameLoopService.on_task_completed(
            user, "clock_out",
            {"project_id": entry.project_id, "hours": hours},
        )
```

- [ ] **Step 5: Hook into project completion signal**

In `apps/projects/signals.py`, inside `handle_project_status_change` after the completion block (after badge evaluation), add:

```python
        # RPG game loop
        from apps.rpg.services import GameLoopService

        GameLoopService.on_task_completed(
            instance.assigned_to, "project_complete",
            {"project_id": instance.pk},
        )
```

- [ ] **Step 6: Hook into milestone completion signal**

In `apps/projects/signals.py`, inside `handle_milestone_completed` after the existing logic, add:

```python
        # RPG game loop
        from apps.rpg.services import GameLoopService

        if instance.project.assigned_to:
            GameLoopService.on_task_completed(
                instance.project.assigned_to, "milestone_complete",
                {"project_id": instance.project_id, "milestone_id": instance.pk},
            )
```

- [ ] **Step 7: Run integration tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_services.GameLoopIntegrationTest -v2
```

Expected: Pass.

- [ ] **Step 8: Run full test suite to check for regressions**

```bash
docker compose exec django python manage.py test -v2
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add apps/timecards/services.py apps/chores/services.py apps/projects/signals.py apps/rpg/tests/test_services.py
git commit -m "feat(rpg): hook game loop into clock-out, chore approval, and project/milestone signals"
```

---

## Task 11: Add RPG data to Dashboard API

**Files:**
- Modify: `apps/projects/views.py:82-185`

- [ ] **Step 1: Write test**

Append to `apps/rpg/tests/test_views.py`:

```python
class DashboardRpgDataTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="dashchild", password="testpass", role="child",
        )
        self.token = Token.objects.create(user=self.child)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_dashboard_includes_rpg_data(self):
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("rpg", response.data)
        rpg = response.data["rpg"]
        self.assertIn("level", rpg)
        self.assertIn("login_streak", rpg)
        self.assertIn("perfect_days_count", rpg)
        self.assertIn("habits_today", rpg)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_views.DashboardRpgDataTest -v2
```

Expected: Fails because "rpg" key doesn't exist in response.

- [ ] **Step 3: Add RPG data to DashboardView**

In `apps/projects/views.py`, inside the `DashboardView.get` method, add the RPG data block before the `return Response({...})` statement. Add after the chores block (around line 166):

```python
        # RPG profile
        from apps.rpg.models import CharacterProfile, Habit, HabitLog
        rpg_profile, _ = CharacterProfile.objects.get_or_create(user=user)
        habits = Habit.objects.filter(user=user, is_active=True)
        habits_data = []
        today = timezone.localdate()
        for h in habits:
            taps_today = HabitLog.objects.filter(
                habit=h, user=user, created_at__date=today,
            ).count()
            habits_data.append({
                "id": h.pk,
                "name": h.name,
                "icon": h.icon,
                "habit_type": h.habit_type,
                "strength": h.strength,
                "taps_today": taps_today,
                "coin_reward": h.coin_reward,
            })

        rpg_data = {
            "level": rpg_profile.level,
            "login_streak": rpg_profile.login_streak,
            "longest_login_streak": rpg_profile.longest_login_streak,
            "perfect_days_count": rpg_profile.perfect_days_count,
            "last_active_date": rpg_profile.last_active_date,
            "habits_today": habits_data,
        }
```

Then add `"rpg": rpg_data,` to the Response dict (after `"pending_chore_approvals"`).

- [ ] **Step 4: Run tests**

```bash
docker compose exec django python manage.py test apps.rpg.tests.test_views.DashboardRpgDataTest -v2
```

Expected: Pass.

- [ ] **Step 5: Run full test suite**

```bash
docker compose exec django python manage.py test -v2
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/projects/views.py apps/rpg/tests/test_views.py
git commit -m "feat(rpg): add RPG profile and habits to dashboard API response"
```

---

## Task 12: Frontend API functions

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add RPG endpoint functions**

Append to `frontend/src/api/index.js`:

```javascript
// RPG
export const getCharacterProfile = () => api.get('/character/');
export const getStreaks = () => api.get('/streaks/');
export const getHabits = () => api.get('/habits/');
export const createHabit = (data) => api.post('/habits/', data);
export const updateHabit = (id, data) => api.patch(`/habits/${id}/`, data);
export const deleteHabit = (id) => api.delete(`/habits/${id}/`);
export const logHabitTap = (id, direction) =>
  api.post(`/habits/${id}/log/`, { direction });
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat(rpg): add frontend API functions for character, streaks, and habits"
```

---

## Task 13: Habits page (frontend)

**Files:**
- Create: `frontend/src/pages/Habits.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Layout.jsx`

- [ ] **Step 1: Create the Habits page**

Create `frontend/src/pages/Habits.jsx`:

```jsx
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus, ThumbsUp, ThumbsDown, Pencil, Trash2, Zap,
} from 'lucide-react';
import {
  getHabits, createHabit, updateHabit, deleteHabit, logHabitTap, getChildren,
} from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import ConfirmDialog from '../components/ConfirmDialog';
import { inputClass } from '../constants/styles';
import { normalizeList } from '../utils/api';

const STRENGTH_COLORS = {
  'red-dark': 'bg-red-700 text-white',
  'red-light': 'bg-red-400 text-white',
  'yellow': 'bg-yellow-400 text-gray-900',
  'green-light': 'bg-green-400 text-white',
  'green': 'bg-green-600 text-white',
  'blue': 'bg-blue-600 text-white',
};

function getStrengthColor(strength) {
  if (strength < -5) return STRENGTH_COLORS['red-dark'];
  if (strength < 0) return STRENGTH_COLORS['red-light'];
  if (strength === 0) return STRENGTH_COLORS['yellow'];
  if (strength <= 5) return STRENGTH_COLORS['green-light'];
  if (strength <= 10) return STRENGTH_COLORS['green'];
  return STRENGTH_COLORS['blue'];
}

function HabitFormModal({ habit, children, onClose, onSaved }) {
  const isEdit = !!habit;
  const [form, setForm] = useState({
    name: habit?.name || '',
    icon: habit?.icon || '',
    habit_type: habit?.habit_type || 'positive',
    user: habit?.user || '',
    coin_reward: habit?.coin_reward ?? 1,
    xp_reward: habit?.xp_reward ?? 5,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = {
        ...form,
        coin_reward: Number(form.coin_reward),
        xp_reward: Number(form.xp_reward),
      };
      if (isEdit) {
        await updateHabit(habit.id, payload);
      } else {
        await createHabit(payload);
      }
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      >
        <div className="absolute inset-0 bg-black/50" onClick={onClose} />
        <motion.div
          className="relative bg-forge-surface rounded-t-2xl md:rounded-2xl w-full max-w-md max-h-[85vh] overflow-y-auto p-5"
          initial={{ y: 100 }} animate={{ y: 0 }}
        >
          <h2 className="font-heading text-lg font-bold mb-4">{isEdit ? 'Edit' : 'New'} Habit</h2>
          {error && <ErrorAlert message={error} />}
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-xs text-forge-text-dim mb-1">Name</label>
              <input className={inputClass} value={form.name} onChange={set('name')} required />
            </div>
            <div>
              <label className="block text-xs text-forge-text-dim mb-1">Icon (emoji)</label>
              <input className={inputClass} value={form.icon} onChange={set('icon')} placeholder="📖" />
            </div>
            <div>
              <label className="block text-xs text-forge-text-dim mb-1">Type</label>
              <select className={inputClass} value={form.habit_type} onChange={set('habit_type')}>
                <option value="positive">Positive (+)</option>
                <option value="negative">Negative (-)</option>
                <option value="both">Both (+/-)</option>
              </select>
            </div>
            {children?.length > 0 && (
              <div>
                <label className="block text-xs text-forge-text-dim mb-1">For</label>
                <select className={inputClass} value={form.user} onChange={set('user')} required>
                  <option value="">Select child...</option>
                  {children.map((c) => (
                    <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-forge-text-dim mb-1">Coin reward</label>
                <input type="number" className={inputClass} value={form.coin_reward} onChange={set('coin_reward')} min={0} />
              </div>
              <div>
                <label className="block text-xs text-forge-text-dim mb-1">XP reward</label>
                <input type="number" className={inputClass} value={form.xp_reward} onChange={set('xp_reward')} min={0} />
              </div>
            </div>
            <div className="flex gap-2 pt-2">
              <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg bg-forge-surface-alt text-forge-text text-sm">
                Cancel
              </button>
              <button type="submit" disabled={saving} className="flex-1 py-2 rounded-lg bg-amber-primary text-white text-sm font-medium">
                {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

export default function Habits() {
  const { user } = useAuth();
  const isParent = user?.role === 'parent';

  const { data: habitsData, loading, reload } = useApi(getHabits);
  const { data: childrenData } = useApi(
    isParent ? getChildren : () => Promise.resolve([]),
    [isParent],
  );

  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingHabit, setEditingHabit] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [tapping, setTapping] = useState(null);

  const habits = normalizeList(habitsData);
  const children = normalizeList(childrenData);

  const handleTap = async (habit, direction) => {
    setTapping(habit.id);
    setError('');
    try {
      await logHabitTap(habit.id, direction);
      reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setTapping(null);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await deleteHabit(confirmDelete.id);
      setConfirmDelete(null);
      reload();
    } catch (e) {
      setError(e.message);
    }
  };

  if (loading) return <Loader />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
          <Zap size={22} /> Habits
        </h1>
        <button
          onClick={() => { setEditingHabit(null); setShowForm(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-primary text-white text-sm font-medium"
        >
          <Plus size={14} /> New Habit
        </button>
      </div>

      <ErrorAlert message={error} />

      {habits.length === 0 ? (
        <EmptyState>No habits yet. Create one to start tracking!</EmptyState>
      ) : (
        <div className="space-y-2">
          {habits.map((habit) => (
            <motion.div
              key={habit.id}
              layout
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Card className="flex items-center gap-3">
                {/* Strength indicator */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${getStrengthColor(habit.strength)}`}>
                  {habit.strength}
                </div>

                {/* Icon + name */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    {habit.icon && <span className="text-lg">{habit.icon}</span>}
                    <span className="font-medium text-sm truncate">{habit.name}</span>
                  </div>
                  <div className="text-xs text-forge-text-dim">
                    +{habit.coin_reward} coins, +{habit.xp_reward} XP
                  </div>
                </div>

                {/* Tap buttons */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {(habit.habit_type === 'positive' || habit.habit_type === 'both') && (
                    <button
                      onClick={() => handleTap(habit, 1)}
                      disabled={tapping === habit.id}
                      className="w-9 h-9 rounded-full bg-green-500/20 text-green-400 flex items-center justify-center hover:bg-green-500/30 transition"
                    >
                      <ThumbsUp size={16} />
                    </button>
                  )}
                  {(habit.habit_type === 'negative' || habit.habit_type === 'both') && (
                    <button
                      onClick={() => handleTap(habit, -1)}
                      disabled={tapping === habit.id}
                      className="w-9 h-9 rounded-full bg-red-500/20 text-red-400 flex items-center justify-center hover:bg-red-500/30 transition"
                    >
                      <ThumbsDown size={16} />
                    </button>
                  )}
                </div>

                {/* Edit/Delete (parent only) */}
                {isParent && (
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => { setEditingHabit(habit); setShowForm(true); }} className="p-1.5 rounded hover:bg-forge-surface-alt">
                      <Pencil size={14} className="text-forge-text-dim" />
                    </button>
                    <button onClick={() => setConfirmDelete(habit)} className="p-1.5 rounded hover:bg-forge-surface-alt">
                      <Trash2 size={14} className="text-red-400" />
                    </button>
                  </div>
                )}
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      {showForm && (
        <HabitFormModal
          habit={editingHabit}
          children={children}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); reload(); }}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete Habit"
          message={`Delete "${confirmDelete.name}"? This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add route to App.jsx**

In `frontend/src/App.jsx`, add the import at the top with other page imports:

```javascript
import Habits from './pages/Habits';
```

Add the route inside the `<Routes>` block (after the homework route):

```jsx
<Route path="/habits" element={<Habits />} />
```

- [ ] **Step 3: Add nav item to Layout.jsx**

In `frontend/src/components/Layout.jsx`, add the import for the Zap icon:

```javascript
import { ..., Zap } from 'lucide-react';
```

Add the nav item in the `allNavItems` array (after the homework entry):

```javascript
{ to: '/habits', icon: Zap, label: 'Habits' },
```

- [ ] **Step 4: Verify locally**

```bash
cd frontend && npm run dev
```

Navigate to `http://localhost:3000/habits` — should render the Habits page.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Habits.jsx frontend/src/App.jsx frontend/src/components/Layout.jsx
git commit -m "feat(rpg): add Habits page with tap UI and parent CRUD"
```

---

## Task 14: Enhanced streak flame on Dashboard

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Update Dashboard to use RPG data**

In `frontend/src/pages/Dashboard.jsx`, update the destructured fields (line 20) to include `rpg`:

```javascript
const { active_timer, current_balance, coin_balance, this_week, active_projects, recent_badges, streak_days, savings_goals, chores_today, pending_chore_approvals, rpg } = data;
```

Replace the streak Card in the stats grid (the Flame card, currently around lines 87-93) with an enhanced version:

```jsx
<motion.div initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.2 }}>
  <Card>
    <Flame className={`mb-1 ${(rpg?.login_streak || streak_days) > 0 ? 'text-orange-400' : 'text-gray-500'}`} size={20} />
    <div className="font-heading text-2xl font-bold">{rpg?.login_streak ?? streak_days}</div>
    <div className="text-xs text-forge-text-dim">Day Streak</div>
    {rpg?.perfect_days_count > 0 && (
      <div className="text-xs text-amber-highlight mt-0.5">
        {rpg.perfect_days_count} perfect day{rpg.perfect_days_count !== 1 ? 's' : ''}
      </div>
    )}
  </Card>
</motion.div>
```

Add a habits widget section after chores (before Active Projects):

```jsx
{/* Today's Habits */}
{rpg?.habits_today?.length > 0 && (
  <div>
    <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2 cursor-pointer" onClick={() => navigate('/habits')}>
      <Zap size={18} /> Habits
    </h2>
    <div className="flex gap-2 overflow-x-auto pb-2">
      {rpg.habits_today.map((h) => (
        <Card key={h.id} className="shrink-0 text-center w-20 cursor-pointer" onClick={() => navigate('/habits')}>
          <div className="text-2xl mb-1">{h.icon || '⚡'}</div>
          <div className="text-xs font-medium truncate">{h.name}</div>
          <div className="text-xs text-forge-text-dim">{h.taps_today}x today</div>
        </Card>
      ))}
    </div>
  </div>
)}
```

Add the `Zap` import to the icon imports at top of file:

```javascript
import { Check, ClipboardCheck, Clock, Coins, DollarSign, Flame, FolderKanban, Trophy, Timer, Target, Zap } from 'lucide-react';
```

- [ ] **Step 2: Verify locally**

```bash
cd frontend && npm run dev
```

Check that the dashboard renders with the RPG streak and habits sections.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx
git commit -m "feat(rpg): add enhanced streak flame and habits widget to dashboard"
```

---

## Task 15: Seed data for RPG

**Files:**
- Modify: `apps/projects/management/commands/seed_data.py`

- [ ] **Step 1: Add RPG seed data method**

Add a `_create_sample_habits` method to the seed data Command class:

```python
def _create_sample_habits(self):
    from apps.rpg.models import CharacterProfile, Habit
    from apps.projects.models import User

    parent = User.objects.filter(role="parent").first()
    child = User.objects.filter(role="child").first()
    if not parent or not child:
        self.stdout.write("  Skipping habits: no parent/child found")
        return

    # Ensure character profile exists
    CharacterProfile.objects.get_or_create(user=child)

    habits = [
        {"name": "Read for 15 min", "icon": "📖", "habit_type": "positive", "coin_reward": 2, "xp_reward": 10},
        {"name": "Practice instrument", "icon": "🎵", "habit_type": "positive", "coin_reward": 2, "xp_reward": 10},
        {"name": "Drink water", "icon": "💧", "habit_type": "positive", "coin_reward": 1, "xp_reward": 5},
        {"name": "Exercise / stretch", "icon": "🏃", "habit_type": "positive", "coin_reward": 1, "xp_reward": 5},
        {"name": "Screen time snack", "icon": "🍫", "habit_type": "negative", "coin_reward": 0, "xp_reward": 0},
    ]

    for h_data in habits:
        habit, created = Habit.objects.get_or_create(
            name=h_data["name"],
            user=child,
            defaults={**h_data, "created_by": parent},
        )
        if created:
            self.stdout.write(f"  Created habit: {habit.name}")
```

Call `self._create_sample_habits()` from the `handle` method (after the last `_create_*` call).

- [ ] **Step 2: Test the seed**

```bash
docker compose exec django python manage.py seed_data --noinput
```

Expected: See "Created habit: ..." lines.

- [ ] **Step 3: Commit**

```bash
git add apps/projects/management/commands/seed_data.py
git commit -m "feat(rpg): add habit seed data to seed_data command"
```

---

## Task 16: Add new NotificationType choices

**Files:**
- Modify: `apps/projects/models.py:235-257`

- [ ] **Step 1: Add RPG notification types**

In `apps/projects/models.py`, inside the `Notification.NotificationType` class, add after `HOMEWORK_DUE_SOON`:

```python
        STREAK_MILESTONE = "streak_milestone", "Streak Milestone"
        PERFECT_DAY = "perfect_day", "Perfect Day"
        DAILY_CHECK_IN = "daily_check_in", "Daily Check-In"
```

- [ ] **Step 2: Make migration**

```bash
docker compose exec django python manage.py makemigrations projects
docker compose exec django python manage.py migrate
```

- [ ] **Step 3: Update GameLoopService notifications to use new types**

In `apps/rpg/services.py`, update the streak milestone notification to use the new type:

Replace `notification_type="badge_earned"` with `notification_type="streak_milestone"` in the streak notification.

Update the perfect day task in `apps/rpg/tasks.py` to use `notification_type="perfect_day"`.

- [ ] **Step 4: Run full test suite**

```bash
docker compose exec django python manage.py test -v2
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/projects/models.py apps/projects/migrations/ apps/rpg/services.py apps/rpg/tasks.py
git commit -m "feat(rpg): add RPG notification types (streak_milestone, perfect_day, daily_check_in)"
```

---

## Task 17: Final verification

- [ ] **Step 1: Run full backend test suite**

```bash
docker compose exec django python manage.py test -v2
```

Expected: All tests pass, zero failures.

- [ ] **Step 2: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: No errors.

- [ ] **Step 3: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds.

- [ ] **Step 4: Manual E2E test**

```bash
docker compose up --build
docker compose exec django python manage.py migrate --noinput
docker compose exec django python manage.py seed_data --noinput
```

Verify:
1. Log in as child → Dashboard shows streak flame and habits widget
2. Navigate to `/habits` → See seeded habits with +/- buttons
3. Tap a positive habit → Strength increments, coins awarded
4. Clock in/out on a project → Streak updates on dashboard
5. Check `/api/character/` → Returns profile with level and streak
6. Check `/api/streaks/` → Returns streak info
7. Check `/api/habits/` → Returns habit list
8. Log in as parent → Can create/edit/delete habits for child

- [ ] **Step 5: Final commit (if any lint/build fixes needed)**

```bash
git add -A
git commit -m "fix(rpg): address lint/build issues from Phase 1"
```

---

## Summary

Phase 1 delivers:
- **CharacterProfile** model with auto-creation signal
- **Habit** and **HabitLog** models for micro-behavior tracking
- **StreakService** for login streak tracking with daily check-in bonuses
- **HabitService** for tap logging and nightly strength decay
- **GameLoopService** as the central RPG orchestrator (extensible for future phases)
- **Celery tasks** for perfect day evaluation and habit decay
- **API endpoints** for character, streaks, and habits
- **Habits page** with tap UI, strength visualization, and parent CRUD
- **Dashboard enhancements** with RPG streak and habits widgets
- **Signal hooks** into clock-out, chore approval, and project/milestone completion
- **Seed data** for sample habits
- **42 unit/integration tests** across models, services, views, and tasks
