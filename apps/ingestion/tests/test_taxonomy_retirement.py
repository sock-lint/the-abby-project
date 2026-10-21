"""Imported new choices exclude retired taxonomy without changing saved projects."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.ingestion.models import ProjectIngestionJob
from apps.ingestion.pipeline.base import IngestionResult
from apps.ingestion.pipeline.category import resolve_category_id
from apps.ingestion.pipeline.enrich import EnrichStage
from apps.projects.management.commands.seed_data import Command
from apps.projects.suggestions import get_project_suggestions
from config.tests.factories import make_family


class TaxonomyRetirementSuggestionTests(TestCase):
    def setUp(self):
        self.family = make_family(parents=[{'username': 'retirement-import-parent', 'is_staff': True}], children=[{'username': 'retirement-import-child'}])
        self.parent, self.child = self.family.parents[0], self.family.children[0]
        self.active = SkillCategory.objects.create(name='Cooking')
        self.retired = SkillCategory.objects.create(name='Woodworking')
        # Keep the control independent of serializers and mutation services.
        self.retired.is_retired = True
        self.retired.save(update_fields=['is_retired'])

    def test_auto_category_does_not_resolve_a_retired_choice(self):
        self.assertIsNone(resolve_category_id('woodworking'))
        self.assertEqual(resolve_category_id('cooking'), self.active.pk)

    def test_enrichment_prompt_omits_retired_categories(self):
        item = IngestionResult(title='Synthetic new project', description='Cook something')
        with patch('config.llm.complete_json', return_value={'category': 'Cooking'}) as llm:
            EnrichStage()(item, {})
        prompt = llm.call_args.kwargs['prompt']
        self.assertIn('Available categories: Cooking', prompt)
        self.assertNotIn('Woodworking', prompt)

    def test_suggestions_filter_retired_ai_output_and_skill_adjacent_fallback(self):
        from apps.achievements.models import SkillProgress
        skill = Skill.objects.create(category=self.retired, name='Sawing')
        SkillProgress.objects.create(user=self.child, skill=skill, level=1)
        with patch('config.llm.complete_json', return_value={'suggestions': [
            {'title': 'Retired choice', 'category': 'Woodworking'},
            {'title': 'Active choice', 'category': 'Cooking'},
        ]}):
            self.assertEqual([s['category'] for s in get_project_suggestions(self.child)], ['Cooking'])
        from config.llm import LLMUnavailable
        with patch('config.llm.complete_json', side_effect=LLMUnavailable()):
            self.assertTrue(all(s['category'] == 'Cooking' for s in get_project_suggestions(self.child)))

    def test_seed_filters_availability_after_resolving_ambiguous_names(self):
        retired_skill = Skill.objects.create(category=self.retired, name='Shared practice')
        active_skill = Skill.objects.create(category=self.active, name='Shared practice')
        own_retired = Skill.objects.create(category=self.active, name='Old practice')
        own_retired.is_retired = True
        own_retired.save(update_fields=['is_retired'])
        mapping = Command()._resolve_skill_map()
        self.assertNotIn('Shared practice', mapping)
        self.assertNotIn(('Woodworking', retired_skill.name), mapping)
        self.assertNotIn(('Cooking', own_retired.name), mapping)
        self.assertEqual(mapping[('Cooking', active_skill.name)].pk, active_skill.pk)
        self.assertNotIn('Woodworking', Command()._resolve_categories())

    def test_retired_explicit_import_category_rejected_but_saved_commit_replays(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent, source_type='url', status='ready',
            result_json={'title': 'Synthetic import', 'category_hint': 'Cooking'},
        )
        url = f'/api/projects/ingest/{job.pk}/commit/'
        rejected = client.post(url, {'category_id': self.retired.pk}, format='json')
        self.assertEqual(rejected.status_code, 400, rejected.content)
        created = client.post(url, {'category_id': self.active.pk}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.active.is_retired = True
        self.active.save(update_fields=['is_retired'])
        replay = client.post(url, {}, format='json')
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.data['id'], created.data['id'])
        self.assertEqual(replay.data['category']['id'], self.active.pk)

    def test_mcp_import_rejects_new_retired_category(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.errors import MCPValidationError
        from apps.mcp_server.schemas import CommitIngestionJobIn
        from apps.mcp_server.tools.ingestion import commit_ingestion_job
        from apps.projects.models import Project
        job = ProjectIngestionJob.objects.create(
            created_by=self.parent, source_type='url', status='ready',
            result_json={'title': 'Synthetic MCP import'},
        )
        with override_user(self.parent), self.assertRaisesMessage(MCPValidationError, 'Retired'):
            commit_ingestion_job(CommitIngestionJobIn(job_id=str(job.pk), category_id=self.retired.pk))
        self.assertFalse(Project.objects.filter(title='Synthetic MCP import').exists())
        job.refresh_from_db()
        self.assertEqual(job.status, 'ready')
