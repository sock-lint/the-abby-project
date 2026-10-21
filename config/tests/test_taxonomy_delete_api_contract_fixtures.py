"""A real protected taxonomy deletion has one non-leaking client contract."""
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyDeleteApiFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def test_delete_in_use_skill_preserves_other_family_progress(self):
        parent = make_family(parents=[{"username": "taxonomy-fixture-author", "is_staff": True}]).parents[0]
        child = make_family(children=[{"username": "taxonomy-fixture-child"}]).children[0]
        category = SkillCategory.objects.create(name="Fixture taxonomy")
        skill = Skill.objects.create(name="Fixture skill", category=category)
        progress = SkillProgress.objects.create(user=child, skill=skill, xp_points=300, level=2)
        self.client.force_authenticate(parent)
        self.assert_response_fixture(self.client.delete(f"/api/skills/{skill.pk}/"),
                                     "taxonomy-delete-in-use.json", status=409)
        self.assertEqual(SkillProgress.objects.get(pk=progress.pk).xp_points, 300)
