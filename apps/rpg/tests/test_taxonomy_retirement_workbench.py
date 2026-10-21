"""New catalog choices respect retirement while retained exact links stay editable."""
from django.test import TestCase

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.mcp_server.catalog import catalog_row
from apps.quests.models import QuestDefinition, QuestSkillTag
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.workbench import create_draft, save_draft, preview_draft
from apps.rpg.progression.catalog import snapshot_catalog
from config.tests.factories import make_family


class TaxonomyRetirementWorkbenchTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{'username': 'taxonomy-workbench', 'is_staff': True}]).parents[0]
        self.category = SkillCategory.objects.create(name='Archive category')
        self.subject = Subject.objects.create(category=self.category, name='Archive subject')
        self.skill = Skill.objects.create(category=self.category, subject=self.subject, name='Archive skill')
        self.quest = QuestDefinition.objects.create(name='Saved challenge', is_system=True,
            quest_type='collection', target_value=2,
            trigger_filter={'allowed_triggers': ['chore_complete'], 'skill_category_id': self.category.pk})
        QuestSkillTag.objects.create(quest_definition=self.quest, skill=self.skill)
        self.category.is_retired = True
        self.category.save(update_fields=['is_retired'])

    def change(self, values, object_id=None):
        draft = create_draft(self.actor, 'Taxonomy choice review')
        return save_draft(self.actor, draft['id'], draft['revision'], [{
            'section': 'quests', 'object_id': object_id, 'key': 'practice', 'values': values,
        }])

    def test_new_draft_rejects_retired_required_skill_filter_and_tag(self):
        base = {'name': 'New challenge', 'quest_type': 'collection', 'target_value': 2, 'description': 'Synthetic practice',
                'trigger_filter': {'allowed_triggers': ['chore_complete']}}
        for values in (
            {'required_skill': self.skill.pk, 'required_skill_level': 1},
            {'trigger_filter': {'allowed_triggers': ['chore_complete'], 'skill_category_id': self.category.pk}},
            {'skill_tags': [{'skill_id': self.skill.pk, 'xp_weight': 1}]},
        ):
            with self.subTest(values=values), self.assertRaisesMessage(ContentPackError, 'Retired'):
                self.change({**base, **values})

    def test_unchanged_saved_links_allow_prose_edit_and_preview(self):
        draft = self.change({'description': 'New retained-history explanation',
            'skill_tags': [{'skill_id': self.skill.pk, 'xp_weight': 1}],
            'trigger_filter': self.quest.trigger_filter}, self.quest.pk)
        reviewed = preview_draft(self.actor, draft['id'], draft['revision'])
        self.assertIsNotNone(reviewed['preview'])
        self.quest.refresh_from_db()
        self.assertIsNone(self.quest.required_skill_id)
        self.assertEqual(list(self.quest.skill_tags.values_list('skill_id', flat=True)), [self.skill.pk])
        gate = QuestDefinition.objects.create(name='Saved Reading milestone', description='Saved gate',
            is_system=True, quest_type='collection', target_value=2,
            trigger_filter={'allowed_triggers': ['reading_logged']},
            required_skill=self.skill, required_skill_level=1)
        gate_draft = self.change({'description': 'Retained required skill', 'required_skill': self.skill.pk}, gate.pk)
        self.assertIsNotNone(preview_draft(self.actor, gate_draft['id'], gate_draft['revision'])['preview'])

    def test_retiring_after_save_is_rechecked_at_preview(self):
        self.category.is_retired = False
        self.category.save(update_fields=['is_retired'])
        draft = self.change({'name': 'Future challenge', 'quest_type': 'collection', 'target_value': 2, 'description': 'Synthetic practice',
            'trigger_filter': {'allowed_triggers': ['chore_complete']},
            'skill_tags': [{'skill_id': self.skill.pk, 'xp_weight': 1}]})
        self.category.is_retired = True
        self.category.save(update_fields=['is_retired'])
        with self.assertRaisesMessage(ContentPackError, 'Retired'):
            preview_draft(self.actor, draft['id'], draft['revision'])
        self.assertFalse(QuestDefinition.objects.filter(name='Future challenge').exists())

    def test_authoring_catalog_reports_direct_and_inherited_availability(self):
        for section, obj in [('categories', self.category), ('subjects', self.subject), ('skills', self.skill)]:
            row = catalog_row(section, obj)
            self.assertEqual(row['is_retired'], section == 'categories')
            self.assertFalse(row['available_for_new_choices'])

    def test_simulation_retains_reward_identity_but_hides_retired_new_gate_choices(self):
        from apps.rpg.progression.challenge_gates import challenge_gate_choices
        snapshot = snapshot_catalog()
        self.assertIn(self.skill.pk, snapshot.skills)
        self.assertNotIn(self.skill.pk, [row['id'] for row in challenge_gate_choices(snapshot)['skills']])
