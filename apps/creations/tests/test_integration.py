"""Cross-app integration tests for the Creations feature.

Keeps the PortfolioView + ChronicleService contract pinned so a future
refactor in either subsystem notices when the Creations wiring breaks.
"""
from __future__ import annotations

import io
from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.creations.models import Creation
from apps.creations.services import CreationService
from apps.projects.models import User


def _real_jpeg(name: str = "art.jpg") -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


class PortfolioIncludesCreationsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.art = SkillCategory.objects.create(name="Art & Crafts", icon="🎨")
        self.draw = Skill.objects.create(category=self.art, name="Drawing", icon="✏️")

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_portfolio_response_includes_creations_section(self, _gl):
        CreationService.log_creation(
            self.child, image=_real_jpeg(), caption="my cat",
            primary_skill_id=self.draw.id,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/portfolio/")
        self.assertEqual(resp.status_code, 200)
        # The new section is present and well-shaped.
        self.assertIn("creations", resp.data)
        creations = resp.data["creations"]
        self.assertEqual(len(creations), 1)
        row = creations[0]
        self.assertEqual(row["caption"], "my cat")
        self.assertEqual(row["primary_skill_name"], "Drawing")
        self.assertEqual(row["primary_skill_category"], "Art & Crafts")
        self.assertEqual(row["status"], Creation.Status.LOGGED)
        self.assertEqual(row["user_id"], self.child.id)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_parent_sees_all_childrens_creations_in_portfolio(self, _gl):
        other = User.objects.create_user(username="c2", password="pw", role="child")
        CreationService.log_creation(
            self.child, image=_real_jpeg(), primary_skill_id=self.draw.id,
        )
        CreationService.log_creation(
            other, image=_real_jpeg(), primary_skill_id=self.draw.id,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/portfolio/")
        self.assertEqual(len(resp.data["creations"]), 2)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_only_sees_own_creations(self, _gl):
        other = User.objects.create_user(username="c2", password="pw", role="child")
        CreationService.log_creation(
            self.child, image=_real_jpeg(), primary_skill_id=self.draw.id,
        )
        CreationService.log_creation(
            other, image=_real_jpeg(), primary_skill_id=self.draw.id,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/portfolio/")
        self.assertEqual(len(resp.data["creations"]), 1)
        self.assertEqual(resp.data["creations"][0]["user_id"], self.child.id)


class RecordCreationIdempotencyTests(TestCase):
    """``ChronicleService.record_creation`` must be safe to call twice for
    the same Creation — we don't currently, but the service must not emit
    duplicate entries if a future retry happens.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="c", password="pw", role="child",
        )

    def test_double_call_yields_single_entry(self):
        entry_a = ChronicleService.record_creation(
            self.user, creation_id=42, title="My cat", caption="a cat",
        )
        entry_b = ChronicleService.record_creation(
            self.user, creation_id=42, title="My cat (retry)", caption="a cat",
        )
        self.assertEqual(entry_a.pk, entry_b.pk)
        self.assertEqual(
            ChronicleEntry.objects.filter(
                user=self.user, related_object_type="creation", related_object_id=42,
            ).count(),
            1,
        )

    def test_different_creation_ids_yield_distinct_entries(self):
        ChronicleService.record_creation(
            self.user, creation_id=1, title="A",
        )
        ChronicleService.record_creation(
            self.user, creation_id=2, title="B",
        )
        self.assertEqual(
            ChronicleEntry.objects.filter(
                user=self.user, kind=ChronicleEntry.Kind.CREATION,
            ).count(),
            2,
        )

    def test_sets_chapter_year_from_occurred_on(self):
        entry = ChronicleService.record_creation(
            self.user, creation_id=99, title="Summer piece",
            occurred_on=date(2026, 8, 15),  # Aug = chapter 2026
        )
        self.assertEqual(entry.chapter_year, 2026)
        # And a June occurrence still belongs to the prior chapter.
        entry_jun = ChronicleService.record_creation(
            self.user, creation_id=100, title="Spring piece",
            occurred_on=date(2026, 6, 15),  # Jun = chapter 2025
        )
        self.assertEqual(entry_jun.chapter_year, 2025)
