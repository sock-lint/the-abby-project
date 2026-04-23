"""Tests for CreationService business logic.

TDD-written: each behaviour has a failing test before the service code was
written. Key invariants pinned here:

1. The first 2 Creations per user per local day award XP + drop roll.
2. The 3rd+ Creation per day still writes the row (proud display) but
   skips both XP and the GameLoopService call entirely.
3. Soft-farm prevention: deleting a Creation does NOT decrement the
   daily counter. A create → delete → create cycle on the same day
   still skips the 3rd log's XP / game loop.
4. Non-creative skills are rejected by ``log_creation``.
5. Every log emits a ChronicleEntry of kind=CREATION.
6. Parent bonus flow (submit → approve / reject) is idempotent per call
   and never unwinds baseline XP.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory
from apps.chronicle.models import ChronicleEntry
from apps.creations.models import Creation, CreationBonusSkillTag
from apps.projects.models import User


def _fake_image(name: str = "art.jpg") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name, b"\xff\xd8\xff\xe0" + b"\x00" * 200, content_type="image/jpeg"
    )


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        # Creative category + skill for the primary tag.
        self.art_cat = SkillCategory.objects.create(name="Art & Crafts", icon="🎨")
        self.draw = Skill.objects.create(
            category=self.art_cat, name="Drawing", icon="✏️",
        )
        self.paint = Skill.objects.create(
            category=self.art_cat, name="Painting", icon="🖌️",
        )
        # A non-creative category + skill (to test rejection).
        self.math_cat = SkillCategory.objects.create(name="Math", icon="🔢")
        self.algebra = Skill.objects.create(
            category=self.math_cat, name="Algebra", icon="✖️",
        )


class LogCreationXPTests(_Fixture):
    def test_first_log_awards_full_pool_to_primary(self):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            c = CreationService.log_creation(
                self.child,
                image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
        self.assertEqual(c.xp_awarded, 10)
        self.assertEqual(c.status, Creation.Status.LOGGED)
        self.assertEqual(c.user, self.child)

    def test_secondary_skill_splits_pool_70_30(self):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            with patch(
                "apps.achievements.services.SkillService.award_xp"
            ) as award:
                CreationService.log_creation(
                    self.child,
                    image=_fake_image(),
                    primary_skill_id=self.draw.id,
                    secondary_skill_id=self.paint.id,
                )
        # Two award_xp calls — one per skill. Weights 7 (primary) + 3
        # (secondary) over 10 pool gives 7 XP + 3 XP.
        awarded = {call.args[1].id: call.args[2] for call in award.call_args_list}
        self.assertEqual(awarded[self.draw.id], 7)
        self.assertEqual(awarded[self.paint.id], 3)


class CreationAntifarmTests(_Fixture):
    def test_first_two_creations_today_fire_game_loop_third_skips(self):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
            CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
            c3 = CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
        self.assertEqual(gl.call_count, 2)
        self.assertEqual(c3.xp_awarded, 0)
        # Row still exists (proud display) — third+ Creations never
        # silently drop. Total rows for the child today: 3.
        self.assertEqual(Creation.objects.filter(user=self.child).count(), 3)

    def test_next_day_resets_counter(self):
        from apps.creations.services import CreationService

        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            # 3 on day 1 — only first 2 award.
            for _ in range(3):
                CreationService.log_creation(
                    self.child, image=_fake_image(),
                    primary_skill_id=self.draw.id,
                )
            # Simulate next day by patching localdate.
            with patch(
                "apps.creations.services.timezone.localdate",
                return_value=tomorrow,
            ):
                c_next = CreationService.log_creation(
                    self.child, image=_fake_image(),
                    primary_skill_id=self.draw.id,
                )
        self.assertEqual(gl.call_count, 3)  # 2 from day 1 + 1 from day 2
        self.assertEqual(c_next.xp_awarded, 10)

    def test_create_two_then_delete_one_then_create_still_skips_xp(self):
        """Soft-farm prevention: deleting a Creation does NOT decrement the
        daily counter. Matches the homework_created anti-farm property.
        """
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            c1 = CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
            CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
            # Delete the first.
            c1.delete()
            # Third attempt should STILL be over the cap.
            c3 = CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
        self.assertEqual(gl.call_count, 2)
        self.assertEqual(c3.xp_awarded, 0)


class LogCreationValidationTests(_Fixture):
    def test_non_creative_primary_skill_rejected(self):
        from apps.creations.services import CreationError, CreationService

        with self.assertRaises(CreationError):
            CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.algebra.id,
            )
        self.assertEqual(Creation.objects.count(), 0)

    def test_non_creative_secondary_skill_rejected(self):
        from apps.creations.services import CreationError, CreationService

        with self.assertRaises(CreationError):
            CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
                secondary_skill_id=self.algebra.id,
            )
        self.assertEqual(Creation.objects.count(), 0)

    def test_same_skill_as_primary_and_secondary_rejected(self):
        from apps.creations.services import CreationError, CreationService

        with self.assertRaises(CreationError):
            CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
                secondary_skill_id=self.draw.id,
            )


class ChronicleEmitTests(_Fixture):
    def test_each_log_emits_chronicle_creation_entry(self):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            c = CreationService.log_creation(
                self.child, image=_fake_image(), caption="my cat",
                primary_skill_id=self.draw.id,
            )
        entries = ChronicleEntry.objects.filter(user=self.child, kind="creation")
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertEqual(entry.related_object_type, "creation")
        self.assertEqual(entry.related_object_id, c.id)
        self.assertIn("cat", entry.title.lower())


class BonusFlowTests(_Fixture):
    def _log(self, **kwargs):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            return CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
                **kwargs,
            )

    def test_submit_flips_status_and_notifies_parents(self):
        from apps.creations.services import CreationService

        c = self._log()
        result = CreationService.submit_for_bonus(c)
        result.refresh_from_db()
        self.assertEqual(result.status, Creation.Status.PENDING)
        # Parent has at least one notification of type CREATION_SUBMITTED.
        self.assertTrue(
            self.parent.notifications.filter(
                notification_type="creation_submitted"
            ).exists()
        )

    def test_approve_distributes_bonus_pool_and_stamps_status(self):
        from apps.creations.services import CreationService

        c = self._log()
        CreationService.submit_for_bonus(c)
        with patch("apps.achievements.services.SkillService.award_xp") as award:
            CreationService.approve_bonus(
                c,
                self.parent,
                bonus_xp=20,
                extra_skill_tags=[{"skill_id": self.draw.id, "xp_weight": 1}],
            )
        c.refresh_from_db()
        self.assertEqual(c.status, Creation.Status.APPROVED)
        self.assertEqual(c.bonus_xp_awarded, 20)
        self.assertEqual(c.decided_by, self.parent)
        self.assertIsNotNone(c.decided_at)
        # Bonus skill tag row was created.
        self.assertEqual(c.bonus_skill_tags.count(), 1)
        # XP was distributed — 20 XP total to Drawing in this case.
        awarded = sum(call.args[2] for call in award.call_args_list)
        self.assertEqual(awarded, 20)
        # Child got a notification.
        self.assertTrue(
            self.child.notifications.filter(
                notification_type="creation_approved"
            ).exists()
        )

    def test_approve_without_extra_tags_uses_child_primary(self):
        """If the parent doesn't add skill tags, the bonus pool falls back
        to the child's primary skill at weight 1.
        """
        from apps.creations.services import CreationService

        c = self._log()
        CreationService.submit_for_bonus(c)
        with patch("apps.achievements.services.SkillService.award_xp") as award:
            CreationService.approve_bonus(c, self.parent, bonus_xp=15)
        call = award.call_args_list[0]
        self.assertEqual(call.args[1].id, self.draw.id)
        self.assertEqual(call.args[2], 15)

    def test_reject_sets_status_without_reversing_baseline_xp(self):
        from apps.creations.services import CreationService

        c = self._log()
        baseline_xp = c.xp_awarded  # 10
        CreationService.submit_for_bonus(c)
        CreationService.reject_bonus(c, self.parent, notes="not feeling it")
        c.refresh_from_db()
        self.assertEqual(c.status, Creation.Status.REJECTED)
        self.assertEqual(c.xp_awarded, baseline_xp)  # unchanged
        self.assertEqual(c.bonus_xp_awarded, 0)
        self.assertEqual(c.decided_by, self.parent)
