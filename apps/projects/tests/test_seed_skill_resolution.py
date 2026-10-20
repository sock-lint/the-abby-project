"""Synthetic seed calls never select skills by an ambiguous display name."""
import io
from unittest.mock import patch

from django.test import TestCase

from apps.achievements.models import ProjectSkillTag, Skill, SkillCategory
from apps.movement.models import MovementType
from apps.projects.management.commands.seed_data import Command
from config.tests.factories import make_family


class SeedSkillResolutionTests(TestCase):
    def setUp(self):
        self.command = Command(stdout=io.StringIO())

    def skill(self, category, name="Endurance"):
        category, _ = SkillCategory.objects.get_or_create(name=category)
        return Skill.objects.create(category=category, name=name)

    def test_ambiguous_bare_alias_is_omitted_but_unique_names_remain_available(self):
        self.skill("Physical")
        self.skill("ZZ other")
        unique = self.skill("Physical", "Unique practice")
        mapping = self.command._resolve_skill_map()
        self.assertNotIn("Endurance", mapping)
        self.assertEqual(mapping["Unique practice"].pk, unique.pk)

    def test_movement_seed_uses_physical_skill_despite_another_category(self):
        canonical = self.skill("Physical")
        self.skill("ZZ other")
        self.command._create_sample_movement_types(self.command._resolve_skill_map())
        walk = MovementType.objects.get(slug="walk")
        self.assertEqual(list(walk.skill_tags.values_list("skill_id", flat=True)), [canonical.pk])

    def test_movement_seed_does_not_substitute_a_unique_foreign_skill_when_physical_is_missing(self):
        self.skill("Other category")
        self.command._create_sample_movement_types(self.command._resolve_skill_map())
        self.assertFalse(MovementType.objects.get(slug="walk").skill_tags.exists())

    def test_project_seed_qualified_identity_cannot_be_overwritten_by_a_literal_skill_name(self):
        canonical = self.skill("Physical")
        self.skill("ZZ other", "Physical::Endurance")
        make_family(parents=[{"username": "dad"}], children=[{"username": "abby"}])
        sample = {"title": "Synthetic exact-category project", "description": "Synthetic",
                  "category": "Physical", "difficulty": 1, "bonus_amount": "0",
                  "materials_budget": "0", "milestones": [], "materials": [], "skills": [("Endurance", 1)]}
        with patch("apps.projects.management.commands.seed_data.SAMPLE_PROJECTS", [sample]):
            self.command._create_sample_projects(
                {"Physical": canonical.category}, self.command._resolve_skill_map(),
            )
        self.assertEqual(list(ProjectSkillTag.objects.filter(project__title=sample["title"])
                              .values_list("skill_id", flat=True)), [canonical.pk])
