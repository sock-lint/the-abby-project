"""Direct edits preserve a supported repair for legacy category-name ties."""
from django.core.cache import cache
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from asgiref.sync import async_to_sync

from apps.achievements.models import Badge, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import ContentPackEntry, DropLog, RPGContentOverride, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], ALLOWED_HOSTS=["testserver"])
class CategoryRetainedRepairAdmissionTests(TestCase):
    def setUp(self):
        cache.clear()
        home = make_family("Retained repair owner", parents=[{"username": "repair-owner", "is_staff": True}],
            children=[{"username": "repair-child"}])
        other = make_family("Retained repair other", parents=[{"username": "repair-other", "is_staff": True}])
        self.actor, self.child, self.other = home.parents[0], home.children[0], other.parents[0]

    def edit(self, transport, actor, category, **changes):
        if transport == "rest":
            client = APIClient()
            client.force_authenticate(actor)
            response = client.patch(f"/api/categories/{category.pk}/", changes, format="json")
            return response.status_code, response.data
        with override_user(actor, scopes=frozenset({"mcp:publish"})):
            result = async_to_sync(mcp.call_tool)("update_category", {
                "params": {"category_id": category.pk, **changes}, "confirmation": True,
            })
        body = result[1] if isinstance(result, tuple) else result.structuredContent
        return (400 if "error" in body else 200), body

    def override(self, category, source, *, actor=None, marker=None):
        return RPGContentOverride.objects.create(family=(actor or self.actor).family,
            model_label="achievements.skillcategory", object_id=category.pk,
            source_lookup={"name": source},
            values={"_authoring": {"version": 1, "source": "mcp"} if marker is None else marker})

    def history(self, *categories):
        for category in categories:
            Project.objects.create(title="Saved completed project", assigned_to=self.child,
                created_by=self.actor, category=category, status=Project.Status.COMPLETED)
        return Badge.objects.create(name="Original category goal", criteria_type="category_projects",
            criteria_value={"category": "Art", "count": len(categories)}, award_coins=False, xp_bonus=0)

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            SkillCategory, RPGContentOverride, ContentPackEntry, Project, Badge,
            UserBadge, SkillProgress, CoinLedger, DropLog, UserInventory,
        )}

    def legacy_tie(self, *, actor, own_source=True):
        retained = SkillCategory.objects.create(name="Visual Arts")
        current = SkillCategory.objects.create(name="ART")
        self.override(retained, "Art")
        if own_source:
            self.override(current, "ART", actor=actor)
        badge = self.history(retained, current)
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        return retained, current, badge

    def assert_departure_rejected_and_repair_pays_once(self, transport, actor, *, own_source=True):
        retained, current, badge = self.legacy_tie(actor=actor, own_source=own_source)
        before = self.snapshot()
        status, body = self.edit(transport, actor, current, name="Drawing", description="Must roll back", is_retired=True)
        self.assertEqual(status, 400, body)
        if transport == "mcp":
            self.assertEqual(body["error"]["code"], "invalid_request")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        # The existing repair joins the retained row to the current namespace;
        # both historical projects contribute without changing their categories.
        status, body = self.edit(transport, self.actor, retained, name="Art")
        self.assertEqual(status, 200, body)
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
        earned = self.snapshot()
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
        self.assertEqual(self.snapshot(), earned)
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assertEqual(RPGContentOverride.objects.get(
            model_label="achievements.skillcategory", object_id=retained.pk).source_lookup, {"name": "Art"})

    def test_mcp_same_family_cannot_remove_last_current_repair_namespace(self):
        self.assert_departure_rejected_and_repair_pays_once("mcp", self.actor)

    def test_mcp_other_family_cannot_remove_last_current_repair_namespace(self):
        self.assert_departure_rejected_and_repair_pays_once("mcp", self.other)

    def test_rest_same_family_cannot_remove_last_current_repair_namespace(self):
        self.assert_departure_rejected_and_repair_pays_once("rest", self.actor)

    def test_rest_other_family_cannot_remove_last_current_repair_namespace(self):
        self.assert_departure_rejected_and_repair_pays_once("rest", self.other)

    def test_first_mcp_edit_without_override_cannot_create_two_retained_aliases(self):
        for actor in (self.actor, self.other):
            with self.subTest(actor=actor.username), transaction.atomic():
                try:
                    self.assert_departure_rejected_and_repair_pays_once("mcp", actor, own_source=False)
                finally:
                    transaction.set_rollback(True)

    def test_first_rest_edit_without_override_cannot_create_two_retained_aliases(self):
        for actor in (self.actor, self.other):
            with self.subTest(actor=actor.username), transaction.atomic():
                try:
                    self.assert_departure_rejected_and_repair_pays_once("rest", actor, own_source=False)
                finally:
                    transaction.set_rollback(True)

    def test_ignored_source_cannot_be_promoted_into_second_retained_alias(self):
        for transport in ("mcp", "rest"):
            for actor in (self.actor, self.other):
                for marker in ({}, {"version": 2, "source": "mcp"}, {"version": True, "source": "mcp"}):
                    with self.subTest(transport=transport, actor=actor.username, marker=marker), transaction.atomic():
                        try:
                            retained = SkillCategory.objects.create(name="Visual Arts")
                            ignored = SkillCategory.objects.create(name="Drawing")
                            self.override(retained, "Art")
                            self.override(ignored, "ART", actor=actor, marker=marker)
                            badge = self.history(retained)
                            self.assertTrue(BadgeService._check_criteria(self.child, badge))
                            before = self.snapshot()
                            status, body = self.edit(transport, actor, ignored, description="Would activate ignored alias")
                            self.assertEqual(status, 400, body)
                            self.assertEqual(self.snapshot(), before)
                            self.assertTrue(BadgeService._check_criteria(self.child, badge))
                        finally:
                            transaction.set_rollback(True)

    def test_existing_two_retained_sources_keep_metadata_and_retirement_permissions(self):
        retained = SkillCategory.objects.create(name="Visual Arts")
        other = SkillCategory.objects.create(name="Drawing")
        self.override(retained, "Art")
        self.override(other, "ART", actor=self.other)
        badge = self.history(retained, other)
        before_sources = list(RPGContentOverride.objects.order_by("pk").values_list("object_id", "source_lookup"))
        for transport, actor, category in (("mcp", self.actor, retained), ("rest", self.other, other)):
            status, body = self.edit(transport, actor, category, description="Preserve legacy metadata", is_retired=True)
            self.assertEqual(status, 200, body)
        self.assertEqual(list(RPGContentOverride.objects.order_by("pk").values_list("object_id", "source_lookup")), before_sources)
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])

    def test_existing_first_source_controls_safe_departure_from_intermediate_name(self):
        retained = SkillCategory.objects.create(name="Visual Arts")
        current = SkillCategory.objects.create(name="ART")
        self.override(retained, "Art")
        self.override(current, "Heritage", actor=self.other)
        badge = self.history(retained)
        self.assertFalse(BadgeService._check_criteria(self.child, badge))
        status, body = self.edit("rest", self.other, current, name="Drawing")
        self.assertEqual(status, 200, body)
        self.assertEqual(RPGContentOverride.objects.get(
            model_label="achievements.skillcategory", object_id=current.pk).source_lookup, {"name": "Heritage"})
        self.assertTrue(BadgeService._check_criteria(self.child, badge))
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])

    def test_untrusted_inexact_or_dangling_sources_do_not_block_a_safe_departure(self):
        for source_kind in ("ignored", "boolean-version", "inexact", "dangling"):
            with self.subTest(source_kind=source_kind), transaction.atomic():
                try:
                    ignored = SkillCategory.objects.create(name="Visual Arts")
                    current = SkillCategory.objects.create(name="ART")
                    source = self.override(ignored, "Art", marker={} if source_kind == "ignored" else None)
                    if source_kind == "boolean-version":
                        source.values = {"_authoring": {"version": True, "source": "mcp"}}
                    elif source_kind == "inexact":
                        source.source_lookup = {"name": "Art", "extra": True}
                    elif source_kind == "dangling":
                        source.object_id = 1000000
                    source.save()
                    self.override(current, "ART", actor=self.other)
                    badge = self.history(current)
                    self.assertTrue(BadgeService._check_criteria(self.child, badge))
                    status, body = self.edit("mcp", self.other, current, name="Drawing")
                    self.assertEqual(status, 200, body)
                    self.assertTrue(BadgeService._check_criteria(self.child, badge))
                    self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
                    self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])
                finally:
                    transaction.set_rollback(True)
