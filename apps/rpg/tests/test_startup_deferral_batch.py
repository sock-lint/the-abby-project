"""One bundled startup carries deferred identities without partial dependents."""
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillPrerequisite, Subject
from apps.achievements.services import SkillService
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack
from apps.rpg.management.commands.loadrpgcontent import Command
from apps.rpg.models import ItemDefinition
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StartupDeferralBatchTests(TestCase):
    def setUp(self):
        household = make_family(parents=[{"username": "batch-deferral-parent", "is_staff": True}],
                                children=[{"username": "batch-deferral-child"}])
        self.actor = household.parents[0]
        self.child = household.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.actor)

    def write(self, directory, filename, value):
        (Path(directory) / filename).write_text(yaml.safe_dump(value))

    def default(self, *directories, command="loadrpgcontent", **options):
        output = StringIO()
        packs = tuple((str(path), "" if index == 0 else f"later-{index}-") for index, path in enumerate(directories))
        with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", packs):
            call_command(command, stdout=output, **options)
        return output.getvalue()

    def retire(self, kind, obj):
        response = self.client.patch(f"/api/{kind}/{obj.pk}/", {"is_retired": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def quest(self, name, **extra):
        return {"name": name, "description": "Synthetic startup dependency", "quest_type": "collection",
                "target_value": 1, "trigger_filter": {"allowed_triggers": ["habit_log"]}, **extra}

    def test_later_bundle_tagging_a_deferred_initial_skill_keeps_startup_and_safe_items(self):
        category = SkillCategory.objects.create(name="Physical")
        self.retire("categories", category)
        with TemporaryDirectory() as first, TemporaryDirectory() as later:
            self.write(first, "skill_tree.yaml", {"categories": [{"name": "Physical"}], "skills": [
                {"name": "Rowing", "category": "Physical"},
            ]})
            self.write(first, "items.yaml", {"items": [{"slug": "batch-safe-food", "name": "Safe snack", "item_type": "food"}]})
            self.write(later, "quests.yaml", {"quests": [self.quest("Later rowing", skill_tags=["Physical::Rowing"])]})
            output = self.default(first, later)
            self.assertTrue(ItemDefinition.objects.filter(slug="batch-safe-food").exists())
            self.assertFalse(Skill.objects.filter(name="Rowing").exists())
            self.assertFalse(QuestDefinition.objects.filter(name="Later rowing").exists())
            self.assertIn("retired_reference_skill: 1", output)
            self.assertIn("retired_reference_quest: 1", output)

    def test_later_bundle_gating_on_a_deferred_initial_quest_is_deferred_too(self):
        category = SkillCategory.objects.create(name="Cooking")
        skill = Skill.objects.create(name="Knife Skills", category=category)
        self.retire("skills", skill)
        with TemporaryDirectory() as first, TemporaryDirectory() as later:
            self.write(first, "quests.yaml", {"quests": [self.quest("Knife week", skill_tags=["Cooking::Knife Skills"])]})
            self.write(first, "items.yaml", {"items": [{"slug": "batch-safe-food", "name": "Safe snack", "item_type": "food"}]})
            self.write(later, "quests.yaml", {"quests": [self.quest("Later knife week", prerequisite_quest="Knife week")]})
            output = self.default(first, later)
            self.assertTrue(ItemDefinition.objects.filter(slug="batch-safe-food").exists())
            self.assertFalse(QuestDefinition.objects.filter(name__in=["Knife week", "Later knife week"]).exists())
            self.assertEqual(output.count("retired_reference_quest: 1"), 2)

    def dependent_case(self, *, existing, target_first):
        with TemporaryDirectory() as directory:
            initial = {"categories": [{"name": "Cooking"}], "skills": [
                {"name": "Knife Skills", "category": "Cooking"},
                {"name": "Heat Control", "category": "Cooking", "description": "Saved heat rules"},
                {"name": "Saved target", "category": "Cooking"},
            ]}
            if existing:
                initial["skills"].append({"name": "Dependent", "category": "Cooking", "description": "Saved dependent rules",
                                          "prereqs": [{"skill": "Saved target", "level": 3}]})
            self.write(directory, "skill_tree.yaml", initial)
            ContentPack(directory).load()
            self.retire("skills", Skill.objects.get(name="Knife Skills"))
            previous = Skill.objects.filter(name="Dependent").first()
            before = None if previous is None else (
                previous.description, previous.is_locked_by_default,
                list(SkillPrerequisite.objects.filter(skill=previous).values_list("pk", "required_skill_id", "required_level")),
            )
            dependent = {"name": "Dependent", "category": "Cooking", "description": "Changed dependent rules", "locked": True,
                         "prereqs": [{"skill": "Heat Control", "level": 2}]}
            target = {"name": "Heat Control", "category": "Cooking", "description": "Changed heat rules", "prereqs": ["Knife Skills"]}
            source = deepcopy(initial)
            source["skills"] = ([target, dependent] if target_first else [dependent, target]) + [initial["skills"][0], initial["skills"][2]]
            self.write(directory, "skill_tree.yaml", source)
            output = self.default(directory)
            if previous:
                previous.refresh_from_db()
                after = (previous.description, previous.is_locked_by_default,
                         list(SkillPrerequisite.objects.filter(skill=previous).values_list("pk", "required_skill_id", "required_level")))
                self.assertEqual(after, before)
                # An ordinary saved skill award remains payable: changing the
                # locked flag without its gate would silently suppress this XP.
                progress = SkillService.award_xp(self.child, previous, 300)
                self.assertEqual(progress.xp_points, 300)
            else:
                self.assertFalse(Skill.objects.filter(name="Dependent").exists())
            heat = Skill.objects.get(name="Heat Control")
            self.assertEqual(heat.description, "Saved heat rules")
            self.assertFalse(SkillPrerequisite.objects.filter(skill=heat).exists())
            self.assertIn("retired_reference_skill: 2", output)
            self.assertNotIn("retired_reference_skill_prerequisites", output)

    def test_new_dependent_before_existing_deferred_target_is_not_created(self):
        self.dependent_case(existing=False, target_first=False)

    def test_new_dependent_after_existing_deferred_target_is_not_created(self):
        self.dependent_case(existing=False, target_first=True)

    def test_existing_dependent_before_existing_deferred_target_is_unchanged(self):
        self.dependent_case(existing=True, target_first=False)

    def test_existing_dependent_after_existing_deferred_target_is_unchanged(self):
        self.dependent_case(existing=True, target_first=True)

    def context_lifetime(self, *, dry_run=False, failure=False):
        category = SkillCategory.objects.create(name="Physical")
        self.retire("categories", category)
        contexts = []

        def capture(path, namespace="", *, defer_retired_references=False, startup_deferrals=None):
            contexts.append(startup_deferrals)
            return ContentPack(path, namespace=namespace, defer_retired_references=defer_retired_references,
                               startup_deferrals=startup_deferrals)

        command = Command()
        with TemporaryDirectory() as first, TemporaryDirectory() as later:
            self.write(first, "skill_tree.yaml", {"categories": [{"name": "Physical"}], "skills": [
                {"name": "Rowing", "category": "Physical"},
            ]})
            self.write(first, "items.yaml", {"items": [{"slug": "batch-safe-food", "name": "Safe snack", "item_type": "food"}]})
            self.write(later, "quests.yaml", {"quests": [self.quest("Later rowing", skill_tags=[
                "Physical::Rowing" if not failure else "Physical::Unknown",
            ])]})
            with patch("apps.rpg.management.commands.loadrpgcontent.ContentPack", side_effect=capture):
                if failure:
                    with self.assertRaisesMessage(CommandError, "unknown or ambiguous skill"):
                        self.default(first, later, command=command)
                else:
                    self.default(first, later, command=command, dry_run=dry_run)
                self.assertEqual(len(contexts), 2)
                self.assertIsNotNone(contexts[0])
                self.assertIs(contexts[0], contexts[1])
                self.assertEqual((contexts[0].skills, contexts[0].quests), (set(), set()))
                self.assertEqual(ItemDefinition.objects.filter(slug="batch-safe-food").exists(), not (dry_run or failure))

                # Reusing a management Command cannot carry the old deferred
                # identity into a new batch where the reference is just unknown.
                self.write(later, "quests.yaml", {"quests": [self.quest("Later rowing", skill_tags=["Physical::Rowing"])]})
                with self.assertRaisesMessage(CommandError, "unknown or ambiguous skill"):
                    self.default(later, command=command)
                self.assertIsNot(contexts[0], contexts[-1])
                self.assertEqual((contexts[-1].skills, contexts[-1].quests), (set(), set()))

                response = self.client.patch(f"/api/categories/{category.pk}/", {"is_retired": False}, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                self.default(first, later, command=command)
                self.assertTrue(Skill.objects.filter(name="Rowing", category=category).exists())
                self.assertTrue(QuestDefinition.objects.filter(name="Later rowing").exists())
                self.assertEqual((contexts[-1].skills, contexts[-1].quests), (set(), set()))

    def test_default_batch_clears_context_after_success_and_on_command_reuse(self):
        self.context_lifetime()

    def test_default_batch_clears_context_after_dry_run_and_on_command_reuse(self):
        self.context_lifetime(dry_run=True)

    def test_default_batch_clears_context_after_failure_and_on_command_reuse(self):
        self.context_lifetime(failure=True)

    def test_deferred_names_do_not_swallow_other_ambiguous_references(self):
        category = SkillCategory.objects.create(name="Physical")
        self.retire("categories", category)
        for name in ("Other practice", "Another practice"):
            Skill.objects.create(name="Rowing", category=SkillCategory.objects.create(name=name))
        with TemporaryDirectory() as first, TemporaryDirectory() as later:
            self.write(first, "skill_tree.yaml", {"categories": [{"name": "Physical"}], "skills": [
                {"name": "Rowing", "category": "Physical"},
            ]})
            self.write(first, "items.yaml", {"items": [{"slug": "batch-safe-food", "name": "Safe snack", "item_type": "food"}]})
            self.write(later, "quests.yaml", {"quests": [self.quest("Ambiguous rowing", skill_tags=["Rowing"])]})
            with self.assertRaisesMessage(CommandError, "unknown or ambiguous skill"):
                self.default(first, later)
            self.assertFalse(ItemDefinition.objects.filter(slug="batch-safe-food").exists())
            self.assertFalse(QuestDefinition.objects.filter(name="Ambiguous rowing").exists())

    def test_restored_prerequisite_applies_complete_new_dependent_rules(self):
        with TemporaryDirectory() as directory:
            source = {"categories": [{"name": "Cooking"}], "skills": [
                {"name": "Knife Skills", "category": "Cooking"},
                {"name": "Heat Control", "category": "Cooking"},
            ]}
            self.write(directory, "skill_tree.yaml", source)
            ContentPack(directory).load()
            knife = Skill.objects.get(name="Knife Skills")
            self.retire("skills", knife)
            source["skills"].insert(0, {"name": "Dependent", "category": "Cooking", "locked": True,
                                        "prereqs": [{"skill": "Heat Control", "level": 2}]})
            source["skills"][2]["prereqs"] = ["Knife Skills"]
            self.write(directory, "skill_tree.yaml", source)
            self.default(directory)
            self.assertFalse(Skill.objects.filter(name="Dependent").exists())
            response = self.client.patch(f"/api/skills/{knife.pk}/", {"is_retired": False}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.default(directory)
            dependent = Skill.objects.get(name="Dependent")
            heat = Skill.objects.get(name="Heat Control")
            self.assertTrue(dependent.is_locked_by_default)
            self.assertEqual(list(dependent.prerequisites.values_list("required_skill_id", "required_level")), [(heat.pk, 2)])
            self.assertEqual(list(heat.prerequisites.values_list("required_skill_id", "required_level")), [(knife.pk, 2)])

    def test_existing_target_moving_to_deferred_subject_preserves_whole_dependent(self):
        with TemporaryDirectory() as directory:
            source = {"categories": [{"name": "Cooking"}],
                      "subjects": [{"name": "Saved subject", "category": "Cooking"}], "skills": [
                {"name": "Heat Control", "category": "Cooking", "subject": "Saved subject", "description": "Saved target"},
                {"name": "Dependent", "category": "Cooking", "description": "Saved dependent", "locked": True,
                 "prereqs": [{"skill": "Heat Control", "level": 2}]},
            ]}
            self.write(directory, "skill_tree.yaml", source)
            ContentPack(directory).load()
            category = SkillCategory.objects.get(name="Cooking")
            self.retire("categories", category)
            dependent = Skill.objects.get(name="Dependent")
            target = Skill.objects.get(name="Heat Control")

            def snapshot():
                return (Skill.objects.filter(pk=dependent.pk).values().get(),
                        Skill.objects.filter(pk=target.pk).values().get(),
                        list(dependent.prerequisites.values_list("pk", "required_skill_id", "required_level")))

            before = snapshot()
            source["subjects"].append({"name": "Deferred subject", "category": "Cooking"})
            source["skills"] = [
                {"name": "Dependent", "category": "Cooking", "description": "Changed dependent", "locked": False,
                 "prereqs": [{"skill": "Heat Control", "level": 5}]},
                {"name": "Heat Control", "category": "Cooking", "subject": "Deferred subject", "description": "Changed target"},
            ]
            self.write(directory, "skill_tree.yaml", source)
            output = self.default(directory)
            self.assertEqual(snapshot(), before)
            self.assertFalse(Subject.objects.filter(name="Deferred subject").exists())
            self.assertIn("retired_reference_skill: 2", output)
            self.assertNotIn("retired_reference_skill_prerequisites", output)
