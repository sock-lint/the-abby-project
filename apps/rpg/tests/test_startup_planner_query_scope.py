"""Startup planning resolves saved rows only when an admission edge needs them."""
from collections import Counter
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.test import TestCase

from apps.achievements.models import Badge, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, StartupDeferrals
from apps.rpg.models import RPGContentOverride


class StartupPlannerQueryScopeTests(TestCase):
    def source(self, quests, badges):
        return {'skill_tree': {'categories': [{'name': 'Planner Archive'}],
                    'skills': [{'name': 'Fresh', 'category': 'Planner Archive'}]},
                'quests': {'quests': quests}, 'badges': {'badges': badges}}

    def quest(self, name, **values):
        return {'name': name, 'description': 'Synthetic planner source', 'quest_type': 'collection',
                'target_value': 2, **values}

    def write(self, root, source):
        path = Path(root) / 'pack'
        path.mkdir()
        for section, value in source.items():
            (path / (section + '.yaml')).write_text(yaml.safe_dump(value))
        return path

    def test_unaffected_terminal_sources_do_not_resolve_saved_admission_rows(self):
        SkillCategory.objects.create(name='Planner Archive', is_retired=True)
        quest_names = {f'Independent quest {i}' for i in range(24)}
        badge_names = {f'Independent badge {i}' for i in range(24)}
        source = self.source(
            [self.quest('Blocked source', skill_tags=['Planner Archive::Fresh'])]
            + [self.quest(name) for name in sorted(quest_names)],
            [{'name': name, 'description': 'Independent badge', 'criteria_type': 'first_project'}
             for name in sorted(badge_names)])
        calls = Counter()
        original = ContentPack._source_reference_matches

        def resolve(pack, model, **lookup):
            if model in (Badge, QuestDefinition):
                calls[model._meta.label_lower, lookup.get('name')] += 1
            return original(pack, model, **lookup)

        with TemporaryDirectory() as root:
            state = StartupDeferrals()
            pack = ContentPack(self.write(root, source), defer_retired_references=True, startup_deferrals=state)
            with patch.object(ContentPack, '_source_reference_matches', resolve):
                ContentPack.prepare_startup_dependencies([pack])
            self.assertEqual(state.planned_quests, {'Blocked source': False})
            self.assertEqual(state.planned_badges, {})
            terminal_lookups = {name: calls['quests.questdefinition', name] for name in quest_names}
            terminal_lookups.update({name: calls['achievements.badge', name] for name in badge_names})
            self.assertFalse(any(terminal_lookups.values()), terminal_lookups)
            state.clear()

    def test_unaffected_dependency_graph_does_not_resolve_saved_admission_rows(self):
        SkillCategory.objects.create(name='Planner Archive', is_retired=True)
        source = self.source(
            [self.quest('Available root'), self.quest('Available gate', required_badge='Available badge')],
            [{'name': 'Available badge', 'criteria_type': 'quest_completed',
              'criteria_value': {'quest_name': 'Available root'}}])
        calls = Counter()
        original = ContentPack._source_reference_matches

        def resolve(pack, model, **lookup):
            if model in (Badge, QuestDefinition):
                calls[model._meta.label_lower, lookup.get('name')] += 1
            return original(pack, model, **lookup)

        with TemporaryDirectory() as root:
            state = StartupDeferrals()
            pack = ContentPack(self.write(root, source), defer_retired_references=True, startup_deferrals=state)
            with patch.object(ContentPack, '_source_reference_matches', resolve):
                ContentPack.prepare_startup_dependencies([pack])
            self.assertEqual(state.planned_quests, {})
            self.assertEqual(state.planned_badges, {})
            self.assertEqual(calls, {})
            state.clear()

    def test_needed_completion_capacity_still_resolves_retained_source_alias(self):
        SkillCategory.objects.create(name='Planner Archive', is_retired=True)
        saved = QuestDefinition.objects.create(name='Current repeated challenge', description='Saved rule',
            quest_type='collection', target_value=2, is_system=True, is_repeatable=True)
        before = QuestDefinition.objects.filter(pk=saved.pk).values().get()
        RPGContentOverride.objects.create(model_label='quests.questdefinition', object_id=saved.pk,
            source_lookup={'name': 'Legacy repeated challenge'}, values={'name': saved.name})
        source = self.source(
            [self.quest('Missing challenge', skill_tags=['Planner Archive::Fresh']),
             self.quest('Reachable gate', required_badge='Repeated completion')],
            [{'name': 'Repeated completion', 'criteria_type': 'quest_completed',
              'criteria_value': {'quest_names': ['Missing challenge', 'Legacy repeated challenge'], 'count': 200}}])
        with TemporaryDirectory() as root:
            state = StartupDeferrals()
            pack = ContentPack(self.write(root, source), defer_retired_references=True, startup_deferrals=state)
            ContentPack.prepare_startup_dependencies([pack])
            self.assertNotIn('Repeated completion', state.planned_badges)
            self.assertNotIn('Reachable gate', state.planned_quests)
            pack.load(stdout=StringIO())
            badge = Badge.objects.get(name='Repeated completion')
            self.assertEqual(QuestDefinition.objects.get(name='Reachable gate').required_badge_id, badge.pk)
            self.assertFalse(QuestDefinition.objects.filter(name='Missing challenge').exists())
            self.assertEqual(QuestDefinition.objects.filter(pk=saved.pk).values().get(), before)
            state.clear()
