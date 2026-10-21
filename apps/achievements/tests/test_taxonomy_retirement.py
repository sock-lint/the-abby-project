"""Retirement withdraws new choices without deleting earned or saved identity."""
from asgiref.sync import async_to_sync
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory, SkillPrerequisite, SkillProgress, Subject
from apps.achievements.services import SkillService
from apps.achievements.serializers import SkillWriteSerializer
from apps.achievements.taxonomy import validate_new_taxonomy_references
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyRetirementTests(TestCase):
    def setUp(self):
        household = make_family(parents=[{"username": "retirement-author", "is_staff": True}],
                                children=[{"username": "retirement-child"}])
        self.parent, self.child = household.parents[0], household.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.category = SkillCategory.objects.create(name="Retirement category")
        self.subject = Subject.objects.create(category=self.category, name="Retirement subject")
        self.skill = Skill.objects.create(category=self.category, subject=self.subject, name="Retirement skill")

    def patch(self, kind, obj, retired):
        response = self.client.patch(f"/api/{kind}/{obj.pk}/", {"is_retired": retired}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIs(response.data.get("is_retired"), retired)
        return response.data

    def rows(self, kind, include=False):
        response = self.client.get(f"/api/{kind}/", {"include_retired": "true"} if include else {})
        self.assertEqual(response.status_code, 200)
        return response.data.get("results", response.data) if isinstance(response.data, dict) else response.data

    def test_active_catalog_rows_expose_both_lifecycle_fields(self):
        for kind in ("categories", "subjects", "skills"):
            for row in self.rows(kind):
                self.assertIs(row.get("is_retired"), False)
                self.assertIs(row.get("available_for_new_choices"), True)

    def test_retiring_category_hides_descendants_without_changing_history_or_awards(self):
        progress = SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=300, level=2)
        successor = Skill.objects.create(category=self.category, name="Successor")
        edge = SkillPrerequisite.objects.create(skill=successor, required_skill=self.skill)
        self.patch("categories", self.category, True)
        for kind in ("categories", "subjects", "skills"):
            self.assertEqual(self.rows(kind), [])
            self.assertTrue(self.rows(kind, include=True))
            self.assertTrue(all(not row["available_for_new_choices"] for row in self.rows(kind, include=True)))
        self.assertTrue(SkillPrerequisite.objects.filter(pk=edge.pk).exists())
        SkillService.award_xp(self.child, self.skill, 10)
        progress.refresh_from_db()
        self.assertEqual(progress.xp_points, 310)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get(f"/api/skills/{self.skill.pk}/").status_code, 200)
        tree = SkillService.get_skill_tree(self.child, self.category)
        self.assertIn(self.skill.pk, [skill["id"] for subject in tree for skill in subject["skills"]])
        self.assertTrue(self.rows("skills", include=True))

    def test_restore_parent_preserves_independent_child_retirement(self):
        self.patch("skills", self.skill, True)
        self.patch("subjects", self.subject, True)
        self.patch("categories", self.category, True)
        self.patch("categories", self.category, False)
        self.assertTrue(self.rows("categories"))
        self.assertEqual(self.rows("subjects"), [])
        self.assertEqual(self.rows("skills"), [])
        self.patch("subjects", self.subject, False)
        self.assertTrue(self.rows("subjects"))
        self.assertEqual(self.rows("skills"), [])
        self.patch("skills", self.skill, False)
        self.assertEqual([row["id"] for row in self.rows("skills")], [self.skill.pk])

    def test_rest_foreign_override_cannot_be_retired_or_restored(self):
        other = make_family(parents=[{"username": "retirement-other", "is_staff": True}]).parents[0]
        RPGContentOverride.objects.create(family=other.family, model_label="achievements.skill", object_id=self.skill.pk,
            source_lookup={"name": self.skill.name, "category_id": self.category.pk},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        response = self.client.patch(f"/api/skills/{self.skill.pk}/", {"is_retired": True}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_rest_retirement_rechecks_current_actor_authority(self):
        other = make_family("Moved retirement actor").family
        for changed in ({"is_active": False}, {"is_staff": False}, {"role": "child"}, {"family_id": other.pk}):
            with self.subTest(changed=changed):
                User.objects.filter(pk=self.parent.pk).update(**changed)
                response = self.client.patch(f"/api/skills/{self.skill.pk}/", {"is_retired": True}, format="json")
                self.assertEqual(response.status_code, 403)
                User.objects.filter(pk=self.parent.pk).update(is_active=True, is_staff=True, role="parent",
                                                              family_id=self.parent.family_id)

    def test_actual_mcp_update_and_lists_support_retirement_and_restore(self):
        with override_user(self.parent):
            for kind, obj in (("category", self.category), ("subject", self.subject), ("skill", self.skill)):
                with self.subTest(kind=kind):
                    result = async_to_sync(mcp.call_tool)(f"update_{kind}", {
                        "params": {f"{kind}_id": obj.pk, "is_retired": True}, "confirmation": True})
                    self.assertFalse(getattr(result, "isError", False), result)
                    payload = result.structuredContent if hasattr(result, "structuredContent") else result[1]
                    self.assertIs(payload["is_retired"], True)
                    restored = async_to_sync(mcp.call_tool)(f"update_{kind}", {
                        "params": {f"{kind}_id": obj.pk, "is_retired": False}, "confirmation": True})
                    self.assertFalse(getattr(restored, "isError", False), restored)
            self.patch("categories", self.category, True)
            active = async_to_sync(mcp.call_tool)("list_skills", {"params": {}})
            active_payload = active.structuredContent if hasattr(active, "structuredContent") else active[1]
            self.assertEqual(active_payload["skills"], [])
            all_rows = async_to_sync(mcp.call_tool)("list_skills", {"params": {"include_retired": True}})
            payload = all_rows.structuredContent if hasattr(all_rows, "structuredContent") else all_rows[1]
            self.assertEqual(payload["skills"][0]["id"], self.skill.pk)
            self.assertIs(payload["skills"][0]["available_for_new_choices"], False)

    def test_rest_candidate_refreshes_a_subject_reparented_after_request_validation(self):
        Skill.objects.filter(pk=self.skill.pk).update(subject=None)
        other_category = SkillCategory.objects.create(name="Moved subject category")
        original = SkillWriteSerializer.is_valid

        def validate_then_move(serializer, **kwargs):
            result = original(serializer, **kwargs)
            Subject.objects.filter(pk=self.subject.pk).update(category=other_category)
            return result

        with patch.object(SkillWriteSerializer, "is_valid", validate_then_move):
            response = self.client.patch(f"/api/skills/{self.skill.pk}/", {"subject": self.subject.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.skill.refresh_from_db()
        self.assertIsNone(self.skill.subject_id)

    def test_mcp_prerequisite_admission_rejects_new_retired_links_and_retains_existing(self):
        successor = Skill.objects.create(category=self.category, name="Prerequisite successor")
        Skill.objects.filter(pk=self.skill.pk).update(is_retired=True)
        with override_user(self.parent):
            rejected = async_to_sync(mcp.call_tool)("add_skill_prerequisite", {"params": {
                "skill_id": successor.pk, "required_skill_id": self.skill.pk}, "confirmation": True})
            self.assertTrue(getattr(rejected, "isError", False), rejected)
            self.assertFalse(SkillPrerequisite.objects.exists())
            created = async_to_sync(mcp.call_tool)("create_skill", {"params": {
                "name": "Cannot create", "category_id": self.category.pk,
                "prerequisites": [{"required_skill_id": self.skill.pk}]}, "confirmation": True})
            self.assertTrue(getattr(created, "isError", False), created)
            self.assertFalse(Skill.objects.filter(name="Cannot create").exists())
            edge = SkillPrerequisite.objects.create(skill=successor, required_skill=self.skill)
            retained = async_to_sync(mcp.call_tool)("add_skill_prerequisite", {"params": {
                "skill_id": successor.pk, "required_skill_id": self.skill.pk, "required_level": 3}, "confirmation": True})
            self.assertFalse(getattr(retained, "isError", False), retained)
            edge.refresh_from_db()
            self.assertEqual(edge.required_level, 3)

    def test_new_taxonomy_parent_rejects_retirement_but_exact_saved_parent_is_editable(self):
        self.patch("categories", self.category, True)
        denied = self.client.post("/api/subjects/", {"name": "New unavailable group", "category": self.category.pk}, format="json")
        self.assertEqual(denied.status_code, 400)
        retained = self.client.patch(f"/api/subjects/{self.subject.pk}/", {"description": "Retain saved parent"}, format="json")
        self.assertEqual(retained.status_code, 200)
        self.assertFalse(retained.data["available_for_new_choices"])
        self.assertEqual(retained.data["category"], self.category.pk)

    def test_retained_ids_must_exist_and_cannot_exempt_a_new_retired_selection(self):
        Skill.objects.filter(pk=self.skill.pk).update(is_retired=True)
        validate_new_taxonomy_references(Skill, [self.skill.pk], retained_ids=[self.skill.pk])
        with self.assertRaises(ValidationError):
            validate_new_taxonomy_references(Skill, [self.skill.pk], retained_ids=[999999])
        with self.assertRaises(ValidationError):
            validate_new_taxonomy_references(Skill, [999999], retained_ids=[999999])

    def test_admission_rejects_changed_ancestry_instead_of_using_old_locked_parents(self):
        from apps.achievements import taxonomy
        other = SkillCategory.objects.create(name="Concurrent parent")
        original = taxonomy._share_lock

        def share_then_reparent(model, ids):
            original(model, ids)
            if model is SkillCategory:
                Skill.objects.filter(pk=self.skill.pk).update(category=other, subject=None)

        with patch.object(taxonomy, "_share_lock", share_then_reparent):
            with self.assertRaisesMessage(ValidationError, "taxonomy changed"):
                validate_new_taxonomy_references(Skill, [self.skill.pk])
