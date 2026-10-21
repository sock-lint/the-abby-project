"""Actual reversible taxonomy responses shared with the React editor."""
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress, Subject
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared


@override_settings(ALLOWED_HOSTS=['testserver'])
class TaxonomyRetirementResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        family = make_family(
            'Synthetic retirement studio', family_id=48,
            parents=[{'id': 81, 'username': 'fixture-taxonomy-designer', 'is_staff': True}],
            children=[{'id': 82, 'username': 'fixture-taxonomy-child'}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.category = SkillCategory.objects.create(id=951, name='Retained practice', icon='🛠️')
        self.subject = Subject.objects.create(id=952, category=self.category, name='Saved subject')
        self.skill = Skill.objects.create(id=953, category=self.category, subject=self.subject, name='Saved skill')
        self.active_category = SkillCategory.objects.create(id=954, name='New practice')
        self.active_skill = Skill.objects.create(id=955, category=self.active_category, name='New skill')
        self.client.force_authenticate(self.parent)

    def test_retire_restore_lists_and_retained_tree_match_shared_contract(self):
        retired = self.assert_response_fixture(self.client.patch(
            f'/api/categories/{self.category.pk}/', {'is_retired': True}, format='json',
        ), 'taxonomy-category-retired.json')
        self.assertTrue(retired['is_retired'])
        self.assertFalse(retired['available_for_new_choices'])
        choices = self.assert_response_fixture(self.client.get('/api/skills/'), 'taxonomy-skills-active.json')
        self.assertEqual([row['id'] for row in choices['results']], [self.active_skill.pk])
        management = self.assert_response_fixture(
            self.client.get('/api/skills/?include_retired=true'), 'taxonomy-skills-retired-management.json',
        )
        saved = next(row for row in management['results'] if row['id'] == self.skill.pk)
        self.assertFalse(saved['is_retired'])
        self.assertFalse(saved['available_for_new_choices'])
        SkillProgress.objects.create(id=956, user=self.child, skill=self.skill, xp_points=75, level=1, unlocked=True)
        self.client.force_authenticate(self.child)
        history = self.assert_response_fixture(self.client.get(
            f'/api/skills/tree/{self.category.pk}/',
        ), 'taxonomy-tree-retired-history.json')
        self.assertEqual(history['category']['id'], self.category.pk)
        self.assertTrue(history['category']['is_retired'])
        self.assertEqual(SkillProgress.objects.get(pk=956).xp_points, 75)
        self.client.force_authenticate(self.parent)
        restored = self.assert_response_fixture(self.client.patch(
            f'/api/categories/{self.category.pk}/', {'is_retired': False}, format='json',
        ), 'taxonomy-category-restored.json')
        self.assertFalse(restored['is_retired'])
        self.assertTrue(restored['available_for_new_choices'])
        self.assertEqual(Skill.objects.get(pk=953).subject_id, self.subject.pk)
        self.assertEqual(SkillProgress.objects.get(pk=956).xp_points, 75)
