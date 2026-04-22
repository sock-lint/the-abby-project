"""Tests for the 2026-04-21 life-RPG badge criteria.

Covers the new criterion checkers added in apps/achievements/criteria.py:
pets/mounts collection, chore/milestone/savings-goal/reward/bounty counters,
Perfect Days, habit strength, streak-freeze usage, and time-of-day clock-in.

Project creation with status=COMPLETED fires the project_complete signal
which calls GameLoopService and reaches for Redis via Celery. Tests that
need a completed project patch ``GameLoopService.on_task_completed`` so
the criterion check is the only thing under test.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone


# Some criteria touch models whose signals reach for Redis/Celery. Use an
# in-memory cache so the test env stays self-contained even when the
# project_complete signal can't be patched (e.g. when it runs before the
# per-test `@patch` decorator takes effect).
CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

from apps.achievements.criteria import (
    _bounty_completed,
    _chore_completions,
    _early_bird,
    _fast_project,
    _habit_max_strength,
    _late_night,
    _mounts_evolved,
    _perfect_days_count,
    _pet_species_owned,
    _pets_hatched,
    _reward_redeemed,
    _savings_goal_completed,
    _streak_freeze_used,
)
from apps.projects.models import User


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class PetCollectionCriteriaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def test_pets_hatched_counts_user_pets(self):
        from apps.pets.models import PetSpecies, UserPet, PotionType

        self.assertFalse(_pets_hatched(self.user, {"count": 1}))
        species = PetSpecies.objects.create(slug="fox", name="Fox")
        potion = PotionType.objects.create(slug="base", name="Base")
        UserPet.objects.create(user=self.user, species=species, potion=potion)
        self.assertTrue(_pets_hatched(self.user, {"count": 1}))
        self.assertFalse(_pets_hatched(self.user, {"count": 2}))

    def test_pet_species_owned_counts_distinct(self):
        from apps.pets.models import PetSpecies, UserPet, PotionType

        fox = PetSpecies.objects.create(slug="fox", name="Fox")
        owl = PetSpecies.objects.create(slug="owl", name="Owl")
        potion_a = PotionType.objects.create(slug="fire", name="Fire")
        potion_b = PotionType.objects.create(slug="ice", name="Ice")
        UserPet.objects.create(user=self.user, species=fox, potion=potion_a)
        # Same species, different potion — still one species owned.
        UserPet.objects.create(user=self.user, species=fox, potion=potion_b)
        self.assertFalse(_pet_species_owned(self.user, {"count": 2}))
        UserPet.objects.create(user=self.user, species=owl, potion=potion_a)
        self.assertTrue(_pet_species_owned(self.user, {"count": 2}))

    def test_mounts_evolved_counts_user_mounts(self):
        from apps.pets.models import PetSpecies, UserMount, PotionType

        species = PetSpecies.objects.create(slug="stallion", name="Stallion")
        potion = PotionType.objects.create(slug="golden", name="Golden")
        self.assertFalse(_mounts_evolved(self.user, {"count": 1}))
        UserMount.objects.create(user=self.user, species=species, potion=potion)
        self.assertTrue(_mounts_evolved(self.user, {"count": 1}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ProgressionCriteriaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )

    def test_chore_completions_counts_approved_only(self):
        from apps.chores.models import Chore, ChoreCompletion

        chore = Chore.objects.create(
            title="Dishes", assigned_to=self.user, created_by=self.parent,
            reward_amount=Decimal("0.50"),
        )
        ChoreCompletion.objects.create(
            chore=chore, user=self.user,
            completed_date=timezone.localdate(),
            reward_amount_snapshot=Decimal("0.50"),
            coin_reward_snapshot=0,
            status=ChoreCompletion.Status.PENDING,
        )
        self.assertFalse(_chore_completions(self.user, {"count": 1}))
        ChoreCompletion.objects.create(
            chore=chore, user=self.user,
            completed_date=timezone.localdate() - timedelta(days=1),
            reward_amount_snapshot=Decimal("0.50"),
            coin_reward_snapshot=0,
            status=ChoreCompletion.Status.APPROVED,
        )
        self.assertTrue(_chore_completions(self.user, {"count": 1}))

    def test_perfect_days_count_reads_profile(self):
        from apps.rpg.models import CharacterProfile

        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        profile.perfect_days_count = 3
        profile.save()
        self.assertTrue(_perfect_days_count(self.user, {"count": 3}))
        self.assertFalse(_perfect_days_count(self.user, {"count": 7}))

    def test_streak_freeze_used_reads_profile_counter(self):
        from apps.rpg.models import CharacterProfile

        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        self.assertFalse(_streak_freeze_used(self.user, {"count": 1}))
        profile.streak_freezes_used = 2
        profile.save()
        self.assertTrue(_streak_freeze_used(self.user, {"count": 1}))
        self.assertTrue(_streak_freeze_used(self.user, {"count": 2}))
        self.assertFalse(_streak_freeze_used(self.user, {"count": 3}))

    def test_habit_max_strength_threshold(self):
        from apps.habits.models import Habit

        habit = Habit.objects.create(
            name="Read",
            user=self.user, created_by=self.user,
            strength=5,
        )
        self.assertFalse(_habit_max_strength(self.user, {"strength": 7}))
        habit.strength = 7
        habit.save()
        self.assertTrue(_habit_max_strength(self.user, {"strength": 7}))

    def test_reward_redeemed_counts_fulfilled(self):
        from apps.rewards.models import Reward, RewardRedemption

        reward = Reward.objects.create(name="Snack", cost_coins=10)
        RewardRedemption.objects.create(
            user=self.user, reward=reward, coin_cost_snapshot=10,
            status=RewardRedemption.Status.PENDING,
        )
        self.assertFalse(_reward_redeemed(self.user, {"count": 1}))
        RewardRedemption.objects.create(
            user=self.user, reward=reward, coin_cost_snapshot=10,
            status=RewardRedemption.Status.FULFILLED,
        )
        self.assertTrue(_reward_redeemed(self.user, {"count": 1}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class TimeOfDayCriteriaTests(TestCase):
    def setUp(self):
        from apps.projects.models import Project

        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.project = Project.objects.create(
            title="Shared", assigned_to=self.user, created_by=self.parent,
        )

    def _entry(self, hour: int):
        """Build a TimeEntry whose ``clock_in`` lands at ``hour`` in the
        Django ``TIME_ZONE`` (Phoenix) — that's what ``clock_in__hour``
        extracts against. Passing the datetime in the app's local zone
        means we don't have to mentally subtract a UTC offset."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from django.conf import settings
        from apps.timecards.models import TimeEntry
        tz = ZoneInfo(settings.TIME_ZONE)
        clock_in = datetime(2026, 1, 15, hour, 0, 0, tzinfo=tz)
        return TimeEntry.objects.create(
            user=self.user, project=self.project,
            clock_in=clock_in,
            clock_out=clock_in + timedelta(hours=1),
            duration_minutes=60,
            status=TimeEntry.Status.COMPLETED,
        )

    def test_early_bird_detects_before_cutoff(self):
        self._entry(hour=6)
        self.assertTrue(_early_bird(self.user, {"hour": 8}))
        self.assertFalse(_early_bird(self.user, {"hour": 6}))

    def test_late_night_detects_after_cutoff(self):
        self._entry(hour=22)
        self.assertTrue(_late_night(self.user, {"hour": 21}))
        self.assertFalse(_late_night(self.user, {"hour": 23}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ProjectSpeedCriterionTests(TestCase):
    """The fast_project criterion replaces the broken legacy Speed Runner
    that had a meaningless `projects_completed: 1` criterion."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_fast_project_matches_under_threshold(self, _mock):
        from apps.projects.models import Project

        parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        proj = Project.objects.create(
            title="Speed Build", assigned_to=self.user, created_by=parent,
            status=Project.Status.COMPLETED,
        )
        # completed_at set ~2 days after creation
        proj.completed_at = proj.created_at + timedelta(days=2)
        proj.save()
        self.assertTrue(_fast_project(self.user, {"days": 3}))
        self.assertFalse(_fast_project(self.user, {"days": 1}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class SavingsGoalCriterionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def test_savings_goal_completed_detects_met_target(self):
        from apps.projects.models import SavingsGoal

        goal = SavingsGoal.objects.create(
            title="Bike", user=self.user,
            target_amount=Decimal("100.00"),
            current_amount=Decimal("50.00"),
        )
        self.assertFalse(_savings_goal_completed(self.user, {"count": 1}))
        goal.current_amount = Decimal("100.00")
        goal.save()
        self.assertTrue(_savings_goal_completed(self.user, {"count": 1}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class BountyCompletedCriterionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_bounty_completed_counts_only_bounty_kind(self, _mock):
        from apps.projects.models import Project

        parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        Project.objects.create(
            title="Required Job", assigned_to=self.user, created_by=parent,
            status=Project.Status.COMPLETED,
            payment_kind=Project.PaymentKind.REQUIRED,
        )
        self.assertFalse(_bounty_completed(self.user, {"count": 1}))
        Project.objects.create(
            title="Bounty Job", assigned_to=self.user, created_by=parent,
            status=Project.Status.COMPLETED,
            payment_kind=Project.PaymentKind.BOUNTY,
        )
        self.assertTrue(_bounty_completed(self.user, {"count": 1}))
