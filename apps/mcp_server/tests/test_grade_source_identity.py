"""Grade recognition follows installed identities after registered MCP edits."""
import io
from pathlib import Path
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.chronicle.models import ChronicleEntry, GradeDailyCounter
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


SOURCE = {
    "categories": [{"name": "Life Skills"}, {"name": "Other practice"}],
    "skills": [{"name": "Time Management", "category": "Life Skills"}],
}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GradeSourceIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Grade source identity", parents=[{
            "username": "grade-identity-parent", "is_staff": True,
        }], children=[{"username": f"grade-identity-child-{index}"} for index in range(3)])
        self.parent, self.children = family.parents[0], family.children
        self.category = SkillCategory.objects.create(name="Life Skills")
        self.other = SkillCategory.objects.create(name="Other practice")
        self.skill = Skill.objects.create(category=self.category, name="Time Management")

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:author", "mcp:catalog", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        payload = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", payload, payload)
        return payload

    def reload_source(self):
        ContentPack(Path(__file__).parent, parsed_content={"skill_tree": SOURCE}).load(stdout=io.StringIO())
        self.assertEqual(Skill.objects.count(), 1)

    def save(self, index=0, *, payload=None, report=False):
        client = APIClient()
        client.force_authenticate(self.children[index])
        if payload is None:
            payload = {"client_entry_id": str(uuid4()), "reflection": "Synthetic progress reflection."}
            if report:
                payload["report_card"] = {
                    "period_type": "quarter", "period_number": 1, "school_year": 2026,
                    "subjects": [{"subject": "Math", "grade_format": "letter", "letter": "B"}],
                }
            else:
                payload.update(subject="Math", assessment="Synthetic quiz", grade_format="percentage", score="80")
        response = client.post("/api/chronicle/grades/", payload, format="json")
        self.assertIn(response.status_code, (200, 201), response.data)
        return response.data, payload

    def assert_award(self, saved, index=0, *, xp=10, status="awarded"):
        self.assertEqual((saved["reward_receipt"]["xp_awarded"], saved["reward_receipt"]["status"]), (xp, status))
        progress = SkillProgress.objects.filter(user=self.children[index], skill=self.skill).first()
        self.assertEqual(progress.xp_points if progress else 0, xp)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.children[index]).count, 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.children[index]).exists())

    def test_category_rename_and_reload_keep_the_original_grade_destination(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.reload_source()
        self.assert_award(self.save()[0])

    def test_skill_rename_keeps_ten_measured_xp(self):
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Time planning"})
        self.assert_award(self.save()[0])

    def test_reparented_renamed_skill_and_category_keep_report_card_xp_after_reload(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Time planning",
            "category_id": self.other.pk, "clear_subject": True})
        self.reload_source()
        self.assert_award(self.save(report=True)[0])

    def test_retired_renamed_installed_destination_still_awards(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice", "is_retired": True})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Time planning", "is_retired": True})
        self.reload_source()
        self.assert_award(self.save()[0])

    def test_source_less_canonical_catalog_and_unrelated_edits_remain_supported(self):
        self.assertFalse(RPGContentOverride.objects.exists())
        self.assert_award(self.save()[0])
        self.wire("update_category", {"category_id": self.other.pk, "name": "Unrelated edited category"})
        self.assert_award(self.save(1)[0], 1)

    def test_current_and_retained_category_collision_never_awards_a_namesake(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        rogue_category = SkillCategory.objects.create(name="Life Skills")
        rogue = Skill.objects.create(category=rogue_category, name="Time Management")
        self.assert_award(self.save()[0], xp=0, status="unavailable")
        self.assertFalse(SkillProgress.objects.filter(skill=rogue).exists())

    def test_current_and_retained_skill_collision_is_unavailable(self):
        rogue = Skill.objects.create(category=self.other, name="Unrelated practice")
        RPGContentOverride.objects.create(family=self.parent.family, model_label="achievements.skill", object_id=rogue.pk,
            source_lookup={"name": "Time Management", "category_id": self.category.pk},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        self.assert_award(self.save()[0], xp=0, status="unavailable")
        self.assertFalse(SkillProgress.objects.filter(skill=rogue).exists())

    def test_renamed_locked_skill_keeps_ordinary_unlock_eligibility(self):
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Time planning", "is_locked_by_default": True})
        self.assert_award(self.save()[0], xp=0, status="not_eligible")

    def test_missing_source_does_not_use_matching_name_in_another_category(self):
        self.skill.delete()
        rogue = Skill.objects.create(category=self.other, name="Time Management")
        saved, _ = self.save()
        self.assertEqual(saved["reward_receipt"]["status"], "unavailable")
        self.assertFalse(SkillProgress.objects.filter(user=self.children[0]).exists())
        self.assertFalse(SkillProgress.objects.filter(skill=rogue).exists())

    def test_inexact_provenance_cannot_redirect_grade_xp(self):
        self.skill.name = "Time planning"
        self.skill.save(update_fields=["name"])
        RPGContentOverride.objects.create(family=self.parent.family, model_label="achievements.skill", object_id=self.skill.pk,
            source_lookup={"name": "Time Management", "category_id": self.category.pk},
            values={"_authoring": {"version": 2, "source": "mcp"}})
        self.assert_award(self.save()[0], xp=0, status="unavailable")

    def test_saved_uuid_replay_and_correction_keep_receipt_and_counter_after_renames(self):
        first, payload = self.save()
        self.wire("update_category", {"category_id": self.category.pk, "name": "Everyday practice"})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Time planning"})
        self.reload_source()
        self.assertEqual(self.save(payload=payload)[0], first)
        client = APIClient()
        client.force_authenticate(self.children[0])
        corrected = client.patch(f"/api/chronicle/{first['id']}/grade/", {"reflection": "Corrected reflection."}, format="json")
        self.assertEqual(corrected.status_code, 200, corrected.data)
        self.assertEqual(corrected.data["reward_receipt"], first["reward_receipt"])
        self.assert_award(corrected.data)
        self.assertEqual(ChronicleEntry.objects.filter(user=self.children[0], kind="grade").count(), 1)

    def test_restore_never_backfills_a_saved_unavailable_attempt(self):
        self.skill.delete()
        first, payload = self.save()
        self.assertEqual(first["reward_receipt"]["status"], "unavailable")
        self.skill = Skill.objects.create(category=self.category, name="Time Management")
        self.assertEqual(self.save(payload=payload)[0], first)
        second, _ = self.save(report=True)
        self.assertEqual(second["reward_receipt"]["status"], "daily_limit")
        self.assertFalse(SkillProgress.objects.filter(user=self.children[0]).exists())
        self.assertEqual(GradeDailyCounter.objects.get(user=self.children[0]).count, 2)
        self.assert_award(self.save(1, report=True)[0], 1)

    def test_report_and_individual_grade_share_daily_limit_after_rename(self):
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Time planning"})
        first, _ = self.save(report=True)
        self.assert_award(first)
        second, _ = self.save()
        self.assertEqual((second["reward_receipt"]["status"], second["reward_receipt"]["xp_awarded"]), ("daily_limit", 0))
        self.assertEqual(SkillProgress.objects.get(user=self.children[0], skill=self.skill).xp_points, 10)
        self.assertEqual(GradeDailyCounter.objects.get(user=self.children[0]).count, 2)
