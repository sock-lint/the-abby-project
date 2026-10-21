"""Shared taxonomy deletes preserve private reusable homework skill identities."""
from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.homework.models import HomeworkTemplate
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HomeworkTemplateTaxonomyDeletionTests(TestCase):
    def test_rest_preserves_skill_used_only_by_other_household_template(self):
        self.assert_template_preserved("rest")

    def test_mcp_preserves_skill_used_only_by_other_household_template(self):
        self.assert_template_preserved("mcp")

    def assert_template_preserved(self, surface):
        actor = make_family(parents=[{"username": "template-deleter", "is_staff": True}]).parents[0]
        owner = make_family(parents=[{"username": "private-template-owner"}]).parents[0]
        category = SkillCategory.objects.create(name="Template-only category")
        for stringify in (False, True):
            with self.subTest(stringify=stringify):
                skill = Skill.objects.create(name=f"Template-only skill {stringify}", category=category)
                tags = [{"skill_id": str(skill.pk) if stringify else skill.pk, "xp_amount": 15}]
                template = HomeworkTemplate.objects.create(title="Private reusable schoolwork", subject="math",
                    created_by=owner, skill_tags=tags)
                if surface == "rest":
                    client = APIClient()
                    client.force_authenticate(actor)
                    response = client.delete(f"/api/skills/{skill.pk}/")
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.data, {"detail": "This taxonomy entry is in use and cannot be deleted.",
                                                     "code": "taxonomy_in_use"})
                else:
                    with override_user(actor):
                        response = async_to_sync(mcp.call_tool)("delete_skill", {
                            "params": {"skill_id": skill.pk}, "confirmation": True})
                    payload = response.structuredContent if hasattr(response, "structuredContent") else response[1]
                    self.assertIn("error", payload)
                    self.assertEqual(payload["error"]["code"], "taxonomy_in_use")
                    self.assertEqual(payload["error"]["field_errors"], {})
                self.assertTrue(Skill.objects.filter(pk=skill.pk).exists())
                template.refresh_from_db()
                self.assertEqual(template.skill_tags, tags)
