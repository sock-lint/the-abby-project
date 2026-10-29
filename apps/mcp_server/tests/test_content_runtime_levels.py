"""Authoring accepts reachable skill levels while retaining earned history."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillPrerequisite, SkillProgress, Subject, UserBadge, XP_THRESHOLDS
from apps.achievements.services import BadgeService, SkillService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import content_packs
from apps.rewards.models import CoinLedger
from apps.rpg.content import validation
from apps.rpg.models import ContentPackEntry, ContentPackPublication, RPGContentOverride, UserInventory
from config.tests.factories import make_family


LEVEL_CASES = (
    ("skill_level_reached", {"count": 1}, "level"),
    ("subjects_completed", {"count": 1}, "min_level"),
    ("skill_categories_breadth", {"categories": 1}, "min_level"),
    ("category_mastery", {"category": "Runtime level category"}, "min_level"),
)
MAX_LEVEL = max(XP_THRESHOLDS)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], ALLOWED_HOSTS=["testserver"])
class ContentRuntimeLevelTests(TestCase):
    scopes = frozenset({"mcp:catalog", "mcp:author", "mcp:publish"})

    def setUp(self):
        cache.clear()
        family = make_family("Runtime level author", parents=[{
            "username": "runtime-level-parent", "is_staff": True,
        }], children=[{"username": "runtime-level-child"}])
        self.actor, self.child = family.parents[0], family.children[0]
        self.category = SkillCategory.objects.create(name="Runtime level category")
        self.skill = Skill.objects.create(category=self.category, name="Runtime level source")
        self.temporary = TemporaryDirectory(prefix="abby-runtime-levels-")
        self.addCleanup(self.temporary.cleanup)
        self.packs = Path(self.temporary.name) / "packs"
        patcher = patch.object(content_packs, "_packs_root", return_value=self.packs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def wire(self, name, params, *, actor=None, scopes=None, confirmation=True):
        with override_user(actor or self.actor, scopes=self.scopes if scopes is None else scopes):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": confirmation})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def ok(self, name, params, **kwargs):
        result = self.wire(name, params, **kwargs)
        self.assertNotIn("error", result, result)
        return result

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            SkillCategory, Subject, Skill, SkillPrerequisite, Badge, UserBadge, SkillProgress,
            RPGContentOverride, ContentPackEntry, ContentPackPublication, CoinLedger, UserInventory,
        )}

    def badge_body(self, name, kind="skill_level_reached", criteria=None):
        return {"name": name, "description": "Synthetic runtime level criterion", "criteria_type": kind,
                "criteria_value": criteria or {"level": MAX_LEVEL, "count": 1},
                "xp_bonus": 0, "award_coins": False}

    def pack_source(self, level):
        return f'''categories:
  - name: Runtime pack category
skills:
  - name: Runtime pack prerequisite
    category: Runtime pack category
    levels: {{"1": Beginner}}
  - name: Runtime pack destination
    category: Runtime pack category
    levels: {{"1": Beginner}}
    locked: true
    prereqs:
      - skill: Runtime pack prerequisite
        level: {level}
'''

    def write_pack(self, level):
        self.ok("write_pack_file", {"pack": "runtime-levels", "filename": "skill_tree.yaml",
                                    "yaml_content": self.pack_source(level)})

    def publication_params(self, preview):
        return {key: preview[key] for key in ("pack", "preview_id", "content_digest")}

    def assert_no_row_writes(self, queries):
        mutations = [query["sql"] for query in queries
                     if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(mutations, [], mutations)

    def test_registered_badge_creation_rejects_each_unreachable_level_without_rows(self):
        for kind, criteria, key in LEVEL_CASES:
            with self.subTest(kind=kind):
                before = self.snapshot()
                result = self.wire("create_badge", self.badge_body(
                    f"Unreachable {kind}", kind, {**criteria, key: MAX_LEVEL + 1},
                ))
                self.assertIn("error", result, result)
                self.assertEqual(self.snapshot(), before)

    def test_registered_badge_update_rejects_each_unreachable_level_atomically(self):
        for kind, criteria, key in LEVEL_CASES:
            with self.subTest(kind=kind):
                badge = self.ok("create_badge", self.badge_body(f"Valid {kind}", kind, {**criteria, key: MAX_LEVEL}))
                before = self.snapshot()
                result = self.wire("update_badge", {"badge_id": badge["id"],
                    "criteria_value": {**criteria, key: MAX_LEVEL + 1}})
                self.assertIn("error", result, result)
                self.assertEqual(self.snapshot(), before)

    def test_maximum_level_badge_is_native_reachable_and_does_not_repay(self):
        badge = self.ok("create_badge", self.badge_body("Reachable maximum level"))
        self.assertEqual(SkillService.award_xp(self.child, self.skill, 1000000).level, MAX_LEVEL)
        self.assertEqual([row.pk for row in BadgeService.evaluate_badges(self.child, scopes={"skill_xp"})], [badge["id"]])
        before = self.snapshot()
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"skill_xp"}), [])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_yaml_preview_rejects_before_upsert_or_publication_receipt(self):
        self.write_pack(MAX_LEVEL + 1)
        before = self.snapshot()
        with CaptureQueriesContext(connection) as queries:
            result = self.wire("preview_content_pack", {"pack": "runtime-levels"})
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)
        self.assert_no_row_writes(queries)

    def test_unpublished_legacy_review_cannot_commit_unreachable_prerequisite(self):
        self.write_pack(MAX_LEVEL + 1)
        # Represent a review produced by the old permissive validator. Current
        # publication must independently validate it before touching catalog rows.
        with patch.object(validation, "validate_content", return_value=None):
            preview = self.ok("preview_content_pack", {"pack": "runtime-levels"})
        before = self.snapshot()
        with CaptureQueriesContext(connection) as queries:
            result = self.wire("publish_content_pack", self.publication_params(preview))
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)
        self.assert_no_row_writes(queries)

    def test_valid_pack_maximum_level_publishes_and_native_skill_unlocks(self):
        self.write_pack(MAX_LEVEL)
        preview = self.ok("preview_content_pack", {"pack": "runtime-levels"})
        self.ok("publish_content_pack", self.publication_params(preview))
        required = Skill.objects.get(name="Runtime pack prerequisite")
        destination = Skill.objects.get(name="Runtime pack destination")
        self.assertEqual(SkillPrerequisite.objects.get(skill=destination).required_level, MAX_LEVEL)
        self.assertEqual(SkillService.award_xp(self.child, required, 1000000).level, MAX_LEVEL)
        self.assertTrue(SkillProgress.objects.get(user=self.child, skill=destination).unlocked)

    def test_completed_legacy_publication_replay_keeps_original_receipt_and_rows(self):
        self.write_pack(MAX_LEVEL + 1)
        with patch.object(validation, "validate_content", return_value=None):
            preview = self.ok("preview_content_pack", {"pack": "runtime-levels"})
            published = self.ok("publish_content_pack", self.publication_params(preview))
        before = self.snapshot()
        self.assertEqual(self.ok("publish_content_pack", self.publication_params(preview)), published)
        self.assertEqual(self.snapshot(), before)
        wrong = self.wire("publish_content_pack", {**self.publication_params(preview), "content_digest": "f" * 64})
        self.assertIn("error", wrong)
        self.assertEqual(self.snapshot(), before)

    def legacy_badges(self):
        earned = Badge.objects.create(**self.badge_body("Legacy earned level", criteria={"level": MAX_LEVEL + 1, "count": 1}))
        Badge.objects.create(**self.badge_body("Legacy unearned level", criteria={"level": MAX_LEVEL + 1, "count": 1}))
        valid = Badge.objects.create(**self.badge_body("Reachable level"))
        UserBadge.objects.create(user=self.child, badge=earned)
        return earned, valid

    def test_legacy_invalid_catalog_is_unavailable_and_audited_without_rewriting_earned_history(self):
        _, valid = self.legacy_badges()
        before = self.snapshot()
        catalog = self.ok("read_rpg_catalog", {"section": "badges"})
        invalid = [row for row in catalog["results"] if row["id"] != valid.pk]
        self.assertEqual(len(invalid), 2)
        self.assertTrue(all(row["available_for_new_user"] is False for row in invalid))
        audit = self.ok("audit_rpg_catalog", {"section": "badges"})
        self.assertEqual({row["id"] for row in audit["findings"]
                          if row["code"] == "invalid_badge_criteria" and row["severity"] == "error"},
                         {row["id"] for row in invalid})
        self.assertEqual(self.snapshot(), before)

    def test_native_unearned_catalog_omits_invalid_level_but_earned_history_and_summary_remain(self):
        earned, valid = self.legacy_badges()
        before = self.snapshot()
        client = APIClient()
        client.force_authenticate(self.child)
        choices = client.get("/api/badges/")
        self.assertEqual(choices.status_code, 200)
        self.assertEqual({row["id"] for row in choices.json()["results"]}, {earned.pk, valid.pk})
        earned_choice = next(row for row in choices.json()["results"] if row["id"] == earned.pk)
        self.assertFalse(earned_choice["catalog_available"])
        history = client.get("/api/badges/earned/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["results"][0]["badge"]["id"], earned.pk)
        self.assertFalse(history.json()["results"][0]["badge"]["catalog_available"])
        summary = client.get("/api/achievements/summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["total_badges"], 2)
        self.assertFalse(summary.json()["badges_earned"][0]["badge"]["catalog_available"])
        self.assertEqual(self.snapshot(), before)

    def test_level_validation_keeps_staff_scope_confirmation_and_receipt_digest_guards(self):
        body = self.badge_body("Authorized level")
        before = self.snapshot()
        self.assertEqual(self.wire("create_badge", body, scopes=frozenset({"mcp:catalog"}))["error"]["code"], "permission_denied")
        self.assertEqual(self.wire("create_badge", body, actor=self.child)["error"]["code"], "permission_denied")
        self.assertEqual(self.snapshot(), before)
        self.write_pack(MAX_LEVEL)
        preview = self.ok("preview_content_pack", {"pack": "runtime-levels"})
        before = self.snapshot()
        self.assertEqual(self.wire("publish_content_pack", self.publication_params(preview),
                                   confirmation=False)["error"]["code"], "confirmation_required")
        self.assertEqual(self.snapshot(), before)

    def test_reachable_level_update_keeps_cross_family_source_ownership(self):
        badge = self.ok("create_badge", self.badge_body("Family-owned reachable badge"))
        other = make_family("Other level author", parents=[{
            "username": "runtime-level-foreign", "is_staff": True,
        }]).parents[0]
        before = self.snapshot()
        result = self.wire("update_badge", {"badge_id": badge["id"],
            "criteria_value": {"level": MAX_LEVEL, "count": 2}}, actor=other)
        self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertEqual(self.snapshot(), before)
