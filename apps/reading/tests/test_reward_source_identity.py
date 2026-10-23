"""Fixed Reading XP follows its retained catalog identity through authoring."""
import io
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.reading.models import ReadingDailyReward, ReadingRewardCredit
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingRewardSourceIdentityTests(TestCase):
    def setUp(self):
        household = make_family("Reading source identity", parents=[
            {"username": "reading-source-parent", "is_staff": True},
        ], children=[{"username": f"reading-source-child-{index}"} for index in range(3)])
        self.parent = household.parents[0]
        self.children = household.children
        self.category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(name="Reading Comprehension", category=self.category)
        self.other_category = SkillCategory.objects.create(name="Other practice")
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:read", "mcp:write", "mcp:author", "mcp:catalog", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        if isinstance(result, tuple):
            return result[1]
        self.assertFalse(result.isError, result.structuredContent)
        return result.structuredContent

    def log(self, child, *, rest=False):
        book = self.wire("create_reading_book", {"user_id": child.pk, "title": "Reading identity",
            "client_request_id": str(uuid4())})
        params = {"user_id": child.pk, "book": book["id"], "duration_minutes": 10,
            "client_request_id": str(uuid4())}
        if rest:
            client = APIClient()
            client.force_authenticate(self.parent)
            response = client.post("/api/reading-sessions/", params, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            saved = response.data
        else:
            saved = self.wire("log_reading_session", params)
        return saved, params

    def reload_original_source(self):
        ContentPack(Path(__file__).parent, parsed_content={"skill_tree": {
            "categories": [{"name": "Language Arts"}],
            "skills": [{"name": "Reading Comprehension", "category": "Language Arts"}],
        }}).load(stdout=io.StringIO())

    def assert_reading_xp(self, child, expected, *, rest=False):
        saved, _ = self.log(child, rest=rest)
        self.assertEqual(saved["reading_reward"]["xp_awarded"], expected)
        self.assertEqual(ReadingDailyReward.objects.get(user=child).xp_awarded, expected)
        self.assertEqual(SkillProgress.objects.filter(user=child, skill=self.skill)
            .values_list("xp_points", flat=True).first() or 0, expected)
        return saved

    def test_skill_rename_and_source_reload_keep_same_xp_destination(self):
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading for meaning"})
        self.reload_original_source()
        self.skill.refresh_from_db()
        self.assertEqual(self.skill.name, "Reading for meaning")
        self.assert_reading_xp(self.children[0], 15)

    def test_category_rename_and_source_reload_preserve_native_rest_award(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Communication Arts"})
        self.reload_original_source()
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Communication Arts")
        self.assert_reading_xp(self.children[0], 15, rest=True)

    def test_skill_reparent_rename_and_category_rename_keep_original_identity(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Communication Arts"})
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading for meaning",
            "category_id": self.other_category.pk, "clear_subject": True})
        self.reload_original_source()
        self.skill.refresh_from_db()
        self.assertEqual(self.skill.category_id, self.other_category.pk)
        self.assertEqual(Skill.objects.filter(pk=self.skill.pk).count(), 1)
        self.assert_reading_xp(self.children[0], 15)

    def test_retired_fixed_destination_keeps_saved_identity_and_xp(self):
        self.wire("update_category", {"category_id": self.category.pk, "is_retired": True})
        self.wire("update_skill", {"skill_id": self.skill.pk, "is_retired": True,
            "name": "Retained reading practice"})
        self.assert_reading_xp(self.children[0], 15)

    def test_missing_canonical_destination_does_not_use_other_category_name_match(self):
        self.skill.delete()
        unrelated = Skill.objects.create(name="Reading Comprehension", category=self.other_category)
        saved, _ = self.log(self.children[0])
        self.assertEqual(saved["reading_reward"]["xp_awarded"], 0)
        self.assertFalse(SkillProgress.objects.filter(user=self.children[0], skill=unrelated).exists())

    def test_ambiguous_current_and_retained_category_identity_awards_no_skill(self):
        self.wire("update_category", {"category_id": self.category.pk, "name": "Communication Arts"})
        # Legacy/ORM data can conflict with the retained identity despite the
        # supported authoring validator preventing new competing names.
        competing = SkillCategory.objects.create(name="Language Arts")
        Skill.objects.create(name="Reading Comprehension", category=competing)
        saved, _ = self.log(self.children[0])
        self.assertEqual(saved["reading_reward"]["xp_awarded"], 0)
        self.assertFalse(SkillProgress.objects.filter(user=self.children[0]).exists())

    def test_ambiguous_current_and_retained_skill_identity_awards_no_skill(self):
        other = Skill.objects.create(name="Unrelated practice", category=self.other_category)
        RPGContentOverride.objects.create(family=self.parent.family,
            model_label="achievements.skill", object_id=other.pk,
            source_lookup={"name": "Reading Comprehension", "category_id": self.category.pk},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        saved, _ = self.log(self.children[0])
        self.assertEqual(saved["reading_reward"]["xp_awarded"], 0)
        self.assertFalse(SkillProgress.objects.filter(user=self.children[0]).exists())

    def test_locked_fixed_destination_still_awards_no_invented_xp(self):
        self.skill.is_locked_by_default = True
        self.skill.save(update_fields=["is_locked_by_default"])
        self.assert_reading_xp(self.children[0], 0)

    def test_rename_restore_and_replay_preserve_original_daily_receipt(self):
        first, params = self.log(self.children[0])
        self.assertEqual(first["reading_reward"]["xp_awarded"], 15)
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading for meaning"})
        self.assert_reading_xp(self.children[1], 15)
        self.wire("update_skill", {"skill_id": self.skill.pk, "name": "Reading Comprehension"})
        replay = self.wire("log_reading_session", params)
        self.assertEqual(replay["reading_reward"], first["reading_reward"])
        self.assertEqual(SkillProgress.objects.get(user=self.children[0], skill=self.skill).xp_points, 15)
        self.assertEqual(ReadingRewardCredit.objects.filter(user=self.children[0]).count(), 1)
        self.assert_reading_xp(self.children[2], 15)

    def test_unrelated_authoring_override_does_not_change_reading_destination(self):
        other = Skill.objects.create(name="Other skill", category=self.other_category)
        self.wire("update_skill", {"skill_id": other.pk, "name": "Renamed other skill"})
        self.assert_reading_xp(self.children[0], 15)
