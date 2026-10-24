"""Saved firsts and graduation immediately recognize Chronicle milestone badges."""
from datetime import UTC, date, datetime
from unittest.mock import patch

from celery.exceptions import Retry
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.chronicle.tasks import chronicle_chapter_transition
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChronicleMilestoneBadgeTests(TestCase):
    def setUp(self):
        family = make_family(children=[{"username": "chronicle-child"}, {"username": "chronicle-sibling"}])
        self.child, self.sibling = family.children
        self.other = make_family("Other Chronicle family", children=[{"username": "chronicle-other"}]).children[0]
        category = SkillCategory.objects.create(name="Chronicle recognition skills")
        skill = Skill.objects.create(name="Persistence", category=category)
        self.progress = SkillProgress.objects.create(user=self.child, skill=skill, xp_points=100, level=1)
        self.food = ItemDefinition.objects.create(
            slug="chronicle-recognition-snack", name="Milestone snack", item_type="food",
        )
        DropTable.objects.create(trigger_type=TriggerType.BADGE_EARNED, item=self.food)

    def badge(self, *, count=3, name="Turning Point", xp=75, rarity="rare"):
        return Badge.objects.create(
            name=name, criteria_type="chronicle_milestones_logged", criteria_value={"count": count},
            xp_bonus=xp, rarity=rarity, award_coins=True,
        )

    def first(self, slug, *, user=None):
        return ChronicleService.record_first(
            user or self.child, event_slug=slug, title="Saved first", occurred_on=date(2026, 10, 22),
        )

    def assert_awarded_once(self, badge, *, xp=75):
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100 + xp)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS).count(), 1)
        self.assertGreater(CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS).amount, 0)
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type=TriggerType.BADGE_EARNED).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 1)

    def test_third_saved_first_immediately_awards_turning_point_once(self):
        badge = self.badge()
        slugs = ["first_project_completed", "first_pet_hatched", "first_exchange_approved"]
        self.first(slugs[0])
        self.first(slugs[1])
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())

        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game_loop:
            entry = self.first(slugs[2])

        self.assertEqual(entry.kind, ChronicleEntry.Kind.FIRST_EVER)
        self.assert_awarded_once(badge)
        game_loop.assert_not_called()
        for slug in slugs:
            self.assertIsNone(self.first(slug))
        self.assertEqual(ChronicleEntry.objects.filter(user=self.child, kind="first_ever").count(), 3)
        self.assert_awarded_once(badge)

    def test_life_chronicler_combines_saved_milestones_and_new_firsts(self):
        badge = self.badge(count=10, name="Life Chronicler", xp=200, rarity="epic")
        # Existing graduation history is a valid saved milestone, not a new award.
        ChronicleEntry.objects.create(
            user=self.child, kind="milestone", event_slug="graduated_high_school",
            occurred_on=date(2025, 6, 1), chapter_year=2024, title="Graduated",
        )
        for index in range(8):
            self.first(f"saved_first_{index}")
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())

        self.first("ninth_saved_first")

        self.assert_awarded_once(badge, xp=200)

    def test_private_other_kinds_and_other_accounts_do_not_count(self):
        badge = self.badge()
        for kind in ("birthday", "chapter_start", "chapter_end", "recap", "manual",
                     "journal", "daily_note", "creation", "grade"):
            ChronicleEntry.objects.create(
                user=self.child, kind=kind, occurred_on=date(2026, 10, 22), chapter_year=2026,
                title="Private history", summary="Private prose must not affect eligibility", is_private=True,
            )
        for user in (self.sibling, self.other):
            self.first("first_project_completed", user=user)
            self.first("first_pet_hatched", user=user)
        self.first("first_project_completed")
        self.first("first_pet_hatched")
        self.assertFalse(UserBadge.objects.exists())

        self.first("first_exchange_approved")

        self.assert_awarded_once(badge)
        self.assertFalse(UserBadge.objects.filter(user__in=[self.sibling, self.other]).exists())
        self.assertFalse(CoinLedger.objects.filter(user__in=[self.sibling, self.other]).exists())
        self.assertFalse(UserInventory.objects.filter(user__in=[self.sibling, self.other]).exists())

    def test_badge_drop_failure_rolls_back_new_first_for_retry(self):
        badge = self.badge()
        self.first("first_project_completed")
        self.first("first_pet_hatched")

        with patch.object(DropLog.objects, "create", side_effect=RuntimeError("Chronicle badge drop failed")):
            with self.assertRaisesRegex(RuntimeError, "Chronicle badge drop failed"):
                self.first("first_exchange_approved")

        self.assertEqual(ChronicleEntry.objects.filter(user=self.child, kind="first_ever").count(), 2)
        self.assertFalse(UserBadge.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(DropLog.objects.exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)
        self.assertIsNotNone(self.first("first_exchange_approved"))
        self.assert_awarded_once(badge)

    def test_badge_integrity_failure_is_not_swallowed_as_a_duplicate_first(self):
        badge = self.badge()
        self.first("first_project_completed")
        self.first("first_pet_hatched")

        with patch.object(DropLog.objects, "create", side_effect=IntegrityError("badge ledger conflict")):
            with self.assertRaisesRegex(IntegrityError, "badge ledger conflict"):
                self.first("first_exchange_approved")

        self.assertEqual(ChronicleEntry.objects.filter(user=self.child, kind="first_ever").count(), 2)
        self.assertFalse(UserBadge.objects.exists())
        self.assertIsNotNone(self.first("first_exchange_approved"))
        self.assert_awarded_once(badge)

    def test_duplicate_first_does_not_backfill_a_new_badge(self):
        for slug in ("first_project_completed", "first_pet_hatched", "first_exchange_approved"):
            self.first(slug)
        self.badge()

        self.assertIsNone(self.first("first_exchange_approved"))

        self.assertFalse(UserBadge.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(DropLog.objects.exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)

    def test_first_default_day_uses_active_local_day_at_utc_boundary(self):
        instant = datetime(2026, 10, 22, 1, tzinfo=UTC)
        with timezone.override("America/Phoenix"), patch("django.utils.timezone.now", return_value=instant):
            with patch("apps.chronicle.services.date") as calendar:
                calendar.today.return_value = date(2026, 10, 22)
                entry = ChronicleService.record_first(
                    self.child, event_slug="first_project_completed", title="First project",
                )

        self.assertEqual(entry.occurred_on, date(2026, 10, 21))

    def test_graduation_task_immediately_recognizes_a_new_milestone_once(self):
        badge = self.badge(count=1, name="Graduation recognition")
        self.child.date_of_birth = date(2011, 4, 21)
        self.child.grade_entry_year = 2025
        self.child.save(update_fields=["date_of_birth", "grade_entry_year"])

        with patch("apps.chronicle.tasks.date") as calendar:
            calendar.today.return_value = date(2029, 6, 1)
            calendar.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            result = chronicle_chapter_transition()
            repeat = chronicle_chapter_transition()

        self.assertEqual(result["graduations"], 1)
        self.assertEqual(repeat["graduations"], 1)
        self.assertEqual(ChronicleEntry.objects.filter(
            user=self.child, kind="milestone", event_slug="graduated_high_school",
        ).count(), 1)
        self.assert_awarded_once(badge)

    def test_failed_graduation_badge_payout_leaves_new_milestone_retryable(self):
        badge = self.badge(count=1, name="Graduation recognition")
        self.child.date_of_birth = date(2011, 4, 21)
        self.child.grade_entry_year = 2025
        self.child.save(update_fields=["date_of_birth", "grade_entry_year"])

        with patch("apps.chronicle.tasks.date") as calendar:
            calendar.today.return_value = date(2029, 6, 1)
            calendar.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            with patch.object(DropLog.objects, "create", side_effect=RuntimeError("graduation badge failed")):
                with self.assertRaisesRegex(RuntimeError, "graduation badge failed"):
                    chronicle_chapter_transition()
            self.assertFalse(ChronicleEntry.objects.filter(user=self.child, kind="milestone").exists())
            self.assertFalse(UserBadge.objects.exists())
            self.assertFalse(CoinLedger.objects.exists())
            chronicle_chapter_transition()

        self.assert_awarded_once(badge)

    def test_failed_graduation_does_not_skip_later_children(self):
        badge = self.badge(count=1, name="Graduation recognition")
        for child in (self.child, self.sibling):
            child.date_of_birth = date(2011, 4, 21)
            child.grade_entry_year = 2025
            child.save(update_fields=["date_of_birth", "grade_entry_year"])
        sibling_progress = SkillProgress.objects.create(
            user=self.sibling, skill=self.progress.skill, xp_points=100, level=1,
        )
        create_drop = DropLog.objects.create

        def fail_first_child(**kwargs):
            if kwargs["user"].pk == self.child.pk:
                raise RuntimeError("first child graduation badge failed")
            return create_drop(**kwargs)

        children = [(self.child.family, self.child), (self.sibling.family, self.sibling)]
        with patch("apps.chronicle.tasks.date") as calendar:
            calendar.today.return_value = date(2029, 6, 1)
            calendar.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            with patch("apps.families.queries.children_across_families", return_value=children):
                with patch.object(DropLog.objects, "create", side_effect=fail_first_child):
                    with self.assertRaisesRegex(RuntimeError, "first child graduation badge failed"):
                        chronicle_chapter_transition()

        self.assertFalse(ChronicleEntry.objects.filter(user=self.child, kind="milestone").exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)
        self.assertSetEqual(set(ChronicleEntry.objects.filter(user=self.sibling).values_list("kind", flat=True)), {
            "chapter_end", "recap", "milestone",
        })
        self.assertEqual(UserBadge.objects.filter(user=self.sibling, badge=badge).count(), 1)
        sibling_progress.refresh_from_db()
        self.assertEqual(sibling_progress.xp_points, 175)
        self.assertEqual(DropLog.objects.filter(user=self.sibling).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.sibling, reason=CoinLedger.Reason.BADGE_BONUS).count(), 1)

    def test_graduation_retry_retains_original_day_without_repaying_later_children(self):
        badge = self.badge(count=1, name="Graduation recognition")
        for child in (self.child, self.sibling):
            child.date_of_birth = date(2011, 4, 21)
            child.grade_entry_year = 2025
            child.save(update_fields=["date_of_birth", "grade_entry_year"])
        sibling_progress = SkillProgress.objects.create(
            user=self.sibling, skill=self.progress.skill, xp_points=100, level=1,
        )
        create_drop = DropLog.objects.create

        def fail_first_child(**kwargs):
            if kwargs["user"].pk == self.child.pk:
                raise RuntimeError("first child graduation badge failed")
            return create_drop(**kwargs)

        children = [(self.child.family, self.child), (self.sibling.family, self.sibling)]
        with patch("apps.chronicle.tasks.date") as calendar:
            calendar.today.return_value = date(2029, 6, 1)
            calendar.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            calendar.fromisoformat.side_effect = date.fromisoformat
            with patch("apps.families.queries.children_across_families", return_value=children):
                with patch.object(DropLog.objects, "create", side_effect=fail_first_child):
                    # Exercise Celery's real retry signature locally, with no broker.
                    with self.assertRaises(Retry) as scheduled:
                        chronicle_chapter_transition.apply(throw=True)
                retry = scheduled.exception
                self.assertEqual(retry.when, 300)
                self.assertEqual(retry.sig.kwargs, {"transition_date": "2029-06-01"})
                self.assertEqual(DropLog.objects.filter(user=self.sibling).count(), 1)

                calendar.today.return_value = date(2029, 6, 2)
                result = retry.sig.apply(throw=True)
                self.assertTrue(result.successful())
                self.assertEqual(result.result, {"starts": 0, "ends": 2, "recaps": 2, "graduations": 2})
                self.assertEqual(chronicle_chapter_transition(), {"noop": True})
                chronicle_chapter_transition(transition_date="2029-06-01")

        self.assert_awarded_once(badge)
        sibling_progress.refresh_from_db()
        self.assertEqual(sibling_progress.xp_points, 175)
        self.assertEqual(DropLog.objects.filter(user=self.sibling).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.sibling, reason=CoinLedger.Reason.BADGE_BONUS).count(), 1)
        milestones = ChronicleEntry.objects.filter(kind="milestone", event_slug="graduated_high_school")
        self.assertEqual(milestones.count(), 2)
        self.assertSetEqual(set(milestones.values_list("occurred_on", "chapter_year")), {(date(2029, 6, 1), 2028)})

    def test_graduation_persistent_failure_stops_after_three_celery_retries(self):
        self.badge(count=1, name="Graduation recognition")
        for child in (self.child, self.sibling):
            child.date_of_birth = date(2011, 4, 21)
            child.grade_entry_year = 2025
            child.save(update_fields=["date_of_birth", "grade_entry_year"])
        create_drop = DropLog.objects.create
        failed_attempts = []

        def fail_first_child(**kwargs):
            if kwargs["user"].pk == self.child.pk:
                failed_attempts.append(kwargs["user"].pk)
                raise RuntimeError("persistent graduation badge failure")
            return create_drop(**kwargs)

        children = [(self.child.family, self.child), (self.sibling.family, self.sibling)]
        with patch("apps.chronicle.tasks.date") as calendar:
            calendar.today.return_value = date(2029, 6, 2)
            calendar.fromisoformat.side_effect = date.fromisoformat
            with patch("apps.families.queries.children_across_families", return_value=children):
                with patch.object(DropLog.objects, "create", side_effect=fail_first_child):
                    for attempt in range(3):
                        with self.assertRaises(Retry) as scheduled:
                            chronicle_chapter_transition.apply(
                                kwargs={"transition_date": "2029-06-01"}, retries=attempt, throw=True,
                            )
                        self.assertEqual(scheduled.exception.sig.kwargs, {"transition_date": "2029-06-01"})
                        self.assertEqual(scheduled.exception.sig.options["retries"], attempt + 1)
                    with self.assertRaisesRegex(RuntimeError, "persistent graduation badge failure"):
                        chronicle_chapter_transition.apply(
                            kwargs={"transition_date": "2029-06-01"}, retries=3, throw=True,
                        )

        self.assertEqual(len(failed_attempts), 4)  # Original attempt plus three retries.
        self.assertFalse(ChronicleEntry.objects.filter(user=self.child, kind="milestone").exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)
        self.assertEqual(ChronicleEntry.objects.filter(user=self.sibling, kind="milestone").count(), 1)
        self.assertEqual(UserBadge.objects.filter(user=self.sibling).count(), 1)
        self.assertEqual(DropLog.objects.filter(user=self.sibling).count(), 1)

    def test_unrelated_chapter_failure_is_not_retried_as_graduation_recognition(self):
        self.child.date_of_birth = date(2011, 4, 21)
        self.child.save(update_fields=["date_of_birth"])
        with patch("apps.chronicle.tasks.date") as calendar:
            calendar.today.return_value = date(2029, 6, 1)
            calendar.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            with patch.object(ChronicleService, "freeze_recap", side_effect=RuntimeError("chapter recap failed")):
                with patch.object(chronicle_chapter_transition, "retry") as retry:
                    with self.assertRaisesRegex(RuntimeError, "chapter recap failed"):
                        chronicle_chapter_transition()

        retry.assert_not_called()
