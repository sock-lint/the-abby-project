"""Authenticated taxonomy edits cannot introduce ambiguous retained category names."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
import yaml

from apps.achievements.models import Badge, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import content_packs
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import ContentPackEntry, ContentPackPublication, DropLog, RPGContentOverride, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], ALLOWED_HOSTS=["testserver"])
class CategoryRenameAdmissionTests(TestCase):
    def setUp(self):
        cache.clear()
        home = make_family("Category rename owner", parents=[{"username": "rename-owner", "is_staff": True}],
            children=[{"username": "rename-child"}])
        other = make_family("Category rename writer", parents=[{"username": "rename-other", "is_staff": True}])
        self.actor, self.child, self.writer = home.parents[0], home.children[0], other.parents[0]
        temporary = TemporaryDirectory(prefix="abby-category-name-admission-")
        self.addCleanup(temporary.cleanup)
        patcher = patch.object(content_packs, "_packs_root", return_value=Path(temporary.name) / "packs")
        patcher.start()
        self.addCleanup(patcher.stop)

    def wire(self, name, params, *, actor=None):
        with override_user(actor or self.actor, scopes=frozenset({"mcp:catalog", "mcp:publish", "mcp:author"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def ok(self, name, params, *, actor=None):
        result = self.wire(name, params, actor=actor)
        self.assertNotIn("error", result, result)
        return result

    def category(self, name, *, actor=None):
        return SkillCategory.objects.get(pk=self.ok("create_category", {"name": name}, actor=actor)["id"])

    def badge(self, name="Cooking"):
        return Badge.objects.get(pk=self.ok("create_badge", {
            "name": "Saved named project goal", "description": "Shared catalog promise", "criteria_type": "category_projects",
            "criteria_value": {"category": name, "count": 1}, "award_coins": False,
        })["id"])

    def project(self, category):
        return Project.objects.create(title="Saved completed project", assigned_to=self.child,
            created_by=self.actor, category=category, status=Project.Status.COMPLETED)

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            SkillCategory, RPGContentOverride, ContentPackEntry, ContentPackPublication, Badge, Project,
            UserBadge, SkillProgress, CoinLedger, DropLog, UserInventory,
        )}

    def assert_once(self, badge):
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])

    def retained_art(self):
        original = self.category("Art")
        self.ok("update_category", {"category_id": original.pk, "name": "Visual Arts"})
        self.project(original)
        return original

    def write_pack(self, rows):
        self.ok("write_pack_file", {"pack": "category-admission", "filename": "skill_tree.yaml",
            "yaml_content": yaml.safe_dump({"categories": rows})}, actor=self.writer)

    def test_other_family_cannot_rename_current_union_member_away(self):
        cooking = self.category("Cooking")
        self.project(cooking)
        badge = self.badge()
        duplicate = self.category("cooking", actor=self.writer)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        before = self.snapshot()
        result = self.wire("update_category", {"category_id": duplicate.pk, "name": "Baking",
            "description": "Must roll back", "is_retired": True}, actor=self.writer)
        self.assertIn("error", result, result)
        self.assertEqual(result["error"]["code"], "invalid_request")
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_once(badge)

    def test_first_direct_edit_without_own_override_cannot_create_retained_tie(self):
        cooking = SkillCategory.objects.create(name="Cooking")
        duplicate = SkillCategory.objects.create(name="cooking")
        self.project(cooking)
        badge = self.badge()
        self.assertFalse(RPGContentOverride.objects.filter(model_label="achievements.skillcategory").exists())
        before = self.snapshot()
        result = self.wire("update_category", {"category_id": duplicate.pk, "name": "Baking"})
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))

    def test_rest_rejects_union_member_rename_atomically(self):
        cooking = self.category("Cooking")
        duplicate = self.category("cooking", actor=self.writer)
        self.project(cooking)
        badge = self.badge()
        before = self.snapshot()
        client = APIClient()
        client.force_authenticate(self.writer)
        response = client.patch(f"/api/categories/{duplicate.pk}/", {"name": "Baking", "description": "Must roll back"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))

    def test_create_cannot_reuse_case_variant_of_genuinely_retained_alias(self):
        self.retained_art()
        badge = self.badge("Art")
        before = self.snapshot()
        result = self.wire("create_category", {"name": "ART"}, actor=self.writer)
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_once(badge)

    def test_rename_cannot_enter_case_variant_of_retained_alias(self):
        self.retained_art()
        other = self.category("Puzzles", actor=self.writer)
        before = self.snapshot()
        result = self.wire("update_category", {"category_id": other.pk, "name": "ART"}, actor=self.writer)
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)

    def test_rest_create_rejects_retained_case_variant(self):
        self.retained_art()
        before = self.snapshot()
        client = APIClient()
        client.force_authenticate(self.writer)
        response = client.post("/api/categories/", {"name": "ART"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.snapshot(), before)

    def test_pack_preview_rejects_alias_reuse_without_partial_content_or_receipt(self):
        self.retained_art()
        self.write_pack([{"name": "Safe new category"}, {"name": "ART"}])
        before = self.snapshot()
        result = self.wire("preview_content_pack", {"pack": "category-admission"}, actor=self.writer)
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)

    def test_pack_publication_rechecks_after_catalog_change_and_fresh_preview_rejects_alias(self):
        original = self.category("Art")
        self.project(original)
        badge = self.badge("Art")
        self.write_pack([{"name": "ART"}])
        plan = self.ok("preview_content_pack", {"pack": "category-admission"}, actor=self.writer)
        self.ok("update_category", {"category_id": original.pk, "name": "Visual Arts"})
        before = self.snapshot()
        result = self.wire("publish_content_pack", {key: plan[key] for key in ("pack", "preview_id", "content_digest")}, actor=self.writer)
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)
        result = self.wire("preview_content_pack", {"pack": "category-admission"}, actor=self.writer)
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))

    def test_current_union_and_case_only_rename_remain_allowed(self):
        original = self.category("Cooking")
        other = self.category("cooking", actor=self.writer)
        self.ok("update_category", {"category_id": other.pk, "name": "COOKING", "is_retired": True}, actor=self.writer)
        self.ok("update_category", {"category_id": original.pk, "description": "Safe metadata"})
        self.project(original)
        self.project(other)
        badge = self.badge()
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_once(badge)

    def test_single_source_rename_retirement_and_renameback_remain_allowed(self):
        original = self.category("Cooking")
        self.project(original)
        badge = self.badge()
        self.ok("update_category", {"category_id": original.pk, "name": "Cuisine", "is_retired": True})
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.ok("update_category", {"category_id": original.pk, "name": "Cooking", "is_retired": False})
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_once(badge)

    def test_keyed_pack_can_publish_current_case_union_without_new_direct_aliases(self):
        self.write_pack([{"name": "Pack practice"}, {"name": "PACK PRACTICE"}])
        plan = self.ok("preview_content_pack", {"pack": "category-admission"}, actor=self.writer)
        self.ok("publish_content_pack", {key: plan[key] for key in ("pack", "preview_id", "content_digest")}, actor=self.writer)
        categories = list(SkillCategory.objects.filter(name__iexact="Pack practice"))
        self.assertEqual(len(categories), 2)
        self.assertFalse(RPGContentOverride.objects.filter(model_label="achievements.skillcategory").exists())
        for category in categories:
            self.project(category)
        badge = self.badge("Pack practice")
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assert_once(badge)

    def test_pack_owned_union_member_first_direct_rename_is_rejected(self):
        self.write_pack([{"name": "Pack practice"}, {"name": "PACK PRACTICE"}])
        plan = self.ok("preview_content_pack", {"pack": "category-admission"}, actor=self.writer)
        self.ok("publish_content_pack", {key: plan[key] for key in ("pack", "preview_id", "content_digest")}, actor=self.writer)
        category = SkillCategory.objects.get(name="PACK PRACTICE")
        before = self.snapshot()
        result = self.wire("update_category", {"category_id": category.pk, "name": "Another practice"}, actor=self.writer)
        self.assertIn("error", result, result)
        self.assertEqual(self.snapshot(), before)

    def test_first_source_not_intermediate_name_controls_safe_rename(self):
        original = self.category("Heritage")
        self.ok("update_category", {"category_id": original.pk, "name": "Cooking"})
        other = self.category("cooking", actor=self.writer)
        self.project(other)
        badge = self.badge()
        self.ok("update_category", {"category_id": original.pk, "name": "Baking"})
        source = RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=original.pk)
        self.assertEqual(source.source_lookup, {"name": "Heritage"})
        self.assertTrue(BadgeService._check_criteria(self.child, badge))

    def legacy_alias(self, *, marker=None, lookup=None):
        retained = SkillCategory.objects.create(name="Visual Arts")
        current = SkillCategory.objects.create(name="ART")
        source = RPGContentOverride.objects.create(family=self.actor.family, model_label="achievements.skillcategory",
            object_id=retained.pk, source_lookup={"name": "Art"} if lookup is None else lookup,
            values={"_authoring": {"version": 1, "source": "mcp"}} if marker is None else {"_authoring": marker})
        self.project(current)
        return retained, current, source

    def test_existing_legacy_casefold_tie_allows_metadata_and_retirement_without_new_restrictions(self):
        retained, current, _source = self.legacy_alias()
        badge = self.badge("Art")
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        self.ok("update_category", {"category_id": retained.pk, "description": "Legacy retained metadata"})
        self.ok("update_category", {"category_id": current.pk, "is_retired": True})
        self.assertFalse(BadgeService._check_criteria(self.child, badge))

    def test_ignored_provenance_cannot_be_promoted_into_a_new_tie(self):
        for marker in ({}, {"version": 2, "source": "mcp"}, {"version": True, "source": "mcp"}):
            with self.subTest(marker=marker):
                retained, current, source = self.legacy_alias(marker=marker)
                badge = self.badge("Art")
                try:
                    self.assertTrue(BadgeService._check_criteria(self.child, badge))
                    before = self.snapshot()
                    result = self.wire("update_category", {"category_id": retained.pk, "description": "Would promote ignored source"})
                    self.assertIn("error", result, result)
                    self.assertEqual(self.snapshot(), before)
                    self.assertTrue(BadgeService._check_criteria(self.child, badge))
                finally:
                    RPGContentOverride.objects.filter(model_label="achievements.badge", object_id=badge.pk).delete()
                    badge.delete()
                    source.delete()
                    retained.delete()
                    current.delete()

    def test_inexact_source_stays_ignored_when_direct_metadata_is_saved(self):
        retained, _current, _source = self.legacy_alias(marker={}, lookup={"name": "Art", "extra": True})
        badge = self.badge("Art")
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.ok("update_category", {"category_id": retained.pk, "description": "Safe metadata for inexact source"})
        self.assertTrue(BadgeService._check_criteria(self.child, badge))

    def test_dangling_or_ignored_retained_alias_does_not_reserve_case_variants(self):
        for marker in ({"version": 2, "source": "mcp"}, {"version": True, "source": "mcp"}):
            with self.subTest(marker=marker):
                retained = SkillCategory.objects.create(name="Visual Arts")
                source = RPGContentOverride.objects.create(family=self.actor.family, model_label="achievements.skillcategory",
                    object_id=retained.pk, source_lookup={"name": "Art"}, values={"_authoring": marker})
                created = self.category("ART", actor=self.writer)
                RPGContentOverride.objects.filter(model_label="achievements.skillcategory", object_id=created.pk).delete()
                created.delete()
                source.delete()
                retained.delete()
        RPGContentOverride.objects.create(family=self.actor.family, model_label="achievements.skillcategory",
            object_id=1000000, source_lookup={"name": "Art"}, values={"_authoring": {"version": 1, "source": "mcp"}})
        self.category("ART", actor=self.writer)
