"""Tests for the Maker + Framed + Polymath criteria (Creations ladder).

Each checker gets three cases: empty, below threshold, at-or-above threshold.
Keep these lightweight — the underlying count logic is trivial; the real
value is catching a future rename/regression in the Creation model shape.
"""
from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.achievements.criteria import (
    _creation_skill_breadth,
    _creations_approved,
    _creations_logged,
)
from apps.achievements.models import Skill, SkillCategory
from apps.creations.models import Creation
from apps.projects.models import User


def _image():
    return SimpleUploadedFile(
        "x.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, content_type="image/jpeg",
    )


class _Fixture(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        self.art = SkillCategory.objects.create(name="Art & Crafts", icon="🎨")
        self.music = SkillCategory.objects.create(name="Music", icon="🎵")
        self.cooking = SkillCategory.objects.create(name="Cooking", icon="🍳")
        self.draw = Skill.objects.create(category=self.art, name="Drawing", icon="✏️")
        self.paint = Skill.objects.create(category=self.art, name="Painting", icon="🖌️")
        self.sing = Skill.objects.create(category=self.music, name="Singing", icon="🎤")
        self.pluck = Skill.objects.create(category=self.music, name="Ukulele", icon="🪕")
        self.bake = Skill.objects.create(category=self.cooking, name="Baking", icon="🍪")

    def _log(self, *, primary, secondary=None, status=Creation.Status.LOGGED):
        import datetime

        return Creation.objects.create(
            user=self.user,
            image=_image(),
            occurred_on=datetime.date.today(),
            primary_skill=primary,
            secondary_skill=secondary,
            status=status,
        )


class CreationsLoggedTests(_Fixture):
    def test_empty_returns_false(self):
        self.assertFalse(_creations_logged(self.user, {"count": 1}))

    def test_below_threshold_returns_false(self):
        self._log(primary=self.draw)
        self.assertFalse(_creations_logged(self.user, {"count": 3}))

    def test_at_threshold_returns_true(self):
        for _ in range(3):
            self._log(primary=self.draw)
        self.assertTrue(_creations_logged(self.user, {"count": 3}))

    def test_counts_all_statuses(self):
        # Proud-display track includes every status, not just APPROVED.
        self._log(primary=self.draw, status=Creation.Status.LOGGED)
        self._log(primary=self.draw, status=Creation.Status.PENDING)
        self._log(primary=self.draw, status=Creation.Status.REJECTED)
        self.assertTrue(_creations_logged(self.user, {"count": 3}))

    def test_default_count_is_1(self):
        self._log(primary=self.draw)
        self.assertTrue(_creations_logged(self.user, {}))


class CreationsApprovedTests(_Fixture):
    def test_empty_returns_false(self):
        self.assertFalse(_creations_approved(self.user, {"count": 1}))

    def test_only_approved_status_counts(self):
        self._log(primary=self.draw, status=Creation.Status.LOGGED)
        self._log(primary=self.draw, status=Creation.Status.PENDING)
        self._log(primary=self.draw, status=Creation.Status.REJECTED)
        self.assertFalse(_creations_approved(self.user, {"count": 1}))

    def test_approved_rows_cross_threshold(self):
        for _ in range(5):
            self._log(primary=self.draw, status=Creation.Status.APPROVED)
        self.assertTrue(_creations_approved(self.user, {"count": 5}))
        self.assertFalse(_creations_approved(self.user, {"count": 6}))


class CreationSkillBreadthTests(_Fixture):
    def test_empty_returns_false(self):
        self.assertFalse(_creation_skill_breadth(self.user, {"count": 5}))

    def test_primary_skills_count_toward_breadth(self):
        # 5 distinct primaries, no secondaries.
        for skill in [self.draw, self.paint, self.sing, self.pluck, self.bake]:
            self._log(primary=skill)
        self.assertTrue(_creation_skill_breadth(self.user, {"count": 5}))

    def test_secondary_skills_also_count(self):
        # 3 primaries + 2 distinct secondaries → 5 total distinct.
        self._log(primary=self.draw, secondary=self.paint)
        self._log(primary=self.sing, secondary=self.pluck)
        self._log(primary=self.bake)
        self.assertTrue(_creation_skill_breadth(self.user, {"count": 5}))

    def test_duplicate_skills_dont_double_count(self):
        # 10 Creations but all using the same 2 skills → breadth of 2.
        for _ in range(10):
            self._log(primary=self.draw, secondary=self.paint)
        self.assertFalse(_creation_skill_breadth(self.user, {"count": 5}))
        self.assertTrue(_creation_skill_breadth(self.user, {"count": 2}))

    def test_default_count_is_5(self):
        for skill in [self.draw, self.paint, self.sing, self.pluck]:
            self._log(primary=skill)
        # Only 4 distinct — default threshold is 5.
        self.assertFalse(_creation_skill_breadth(self.user, {}))
        self._log(primary=self.bake)
        self.assertTrue(_creation_skill_breadth(self.user, {}))
