"""Bundled startup defers retired new references; reviewed packs stay strict."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillPrerequisite, Subject
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.models import ItemDefinition
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RetiredTaxonomyStartupSafetyTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{
            "username": "retired-startup-parent", "is_staff": True,
        }]).parents[0]
        self.client = APIClient()
        self.client.force_authenticate(self.actor)

    def load_default(self, directory, **options):
        output = StringIO()
        with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", ((directory, ""),)):
            call_command("loadrpgcontent", stdout=output, **options)
        return output.getvalue()

    def seed_and_retire(self, directory, *, keyed):
        root = Path(directory)
        (root / "skill_tree.yaml").write_text(
            "categories:\n  - name: Startup practice\n"
            "skills:\n  - name: Saved practice\n    category: Startup practice\n"
            "    levels: {'1': Beginner}\n",
        )
        ContentPack(directory, **({"pack_key": "retired-startup", "family": self.actor.family} if keyed else {})).load()
        skill = Skill.objects.get(name="Saved practice")
        response = self.client.patch(f"/api/skills/{skill.pk}/", {"is_retired": True}, format="json")
        self.assertEqual(response.status_code, 200)
        (root / "items.yaml").write_text(
            "items:\n  - slug: unrelated-startup-food\n    name: Unrelated startup snack\n"
            "    item_type: food\n",
        )
        (root / "quests.yaml").write_text(
            "quests:\n  - name: Future practice\n    description: Synthetic future practice\n    quest_type: collection\n"
            "    target_value: 1\n    duration_days: 7\n    xp_reward: 10\n"
            "    trigger_filter: {allowed_triggers: [habit_log]}\n"
            "    skill_tags: ['Startup practice::Saved practice']\n",
        )
        return skill

    def test_default_startup_defers_new_retired_reference_and_loads_unrelated_content(self):
        with TemporaryDirectory() as directory:
            skill = self.seed_and_retire(directory, keyed=False)
            output = self.load_default(directory)
            skill.refresh_from_db()
            self.assertTrue(skill.is_retired)
            self.assertTrue(ItemDefinition.objects.filter(slug="unrelated-startup-food").exists())
            self.assertFalse(QuestDefinition.objects.filter(name="Future practice").exists())
            self.assertIn("skipped retired_reference_quest: 1", output)
            self.assertIn("Left quest 'Future practice' unchanged", output)

    def test_keyed_pack_rejects_same_reference_without_partial_publication(self):
        with TemporaryDirectory() as directory:
            skill = self.seed_and_retire(directory, keyed=True)
            with self.assertRaisesMessage(ContentPackError, "Retired taxonomy entries"):
                ContentPack(directory, pack_key="retired-startup", family=self.actor.family).load()
            skill.refresh_from_db()
            self.assertTrue(skill.is_retired)
            self.assertFalse(ItemDefinition.objects.filter(slug="unrelated-startup-food").exists())
            self.assertFalse(QuestDefinition.objects.filter(name="Future practice").exists())

    def test_explicit_manual_pack_load_stays_strict(self):
        with TemporaryDirectory() as directory:
            self.seed_and_retire(directory, keyed=False)
            with self.assertRaisesMessage(CommandError, "Retired taxonomy entries"):
                call_command("loadrpgcontent", pack=directory, stdout=StringIO())
            self.assertFalse(ItemDefinition.objects.filter(slug="unrelated-startup-food").exists())

    def test_retired_new_parents_defer_whole_subject_and_skill_rows(self):
        with TemporaryDirectory() as directory:
            skill = self.seed_and_retire(directory, keyed=False)
            self.assertEqual(self.client.patch(f"/api/categories/{skill.category_id}/", {
                "is_retired": True,
            }, format="json").status_code, 200)
            root = Path(directory)
            content = yaml.safe_load((root / "skill_tree.yaml").read_text())
            content["subjects"] = [{"name": "New subject", "category": "Startup practice"}]
            content["skills"] += [{"name": "New child", "category": "Startup practice", "subject": "New subject"}]
            (root / "skill_tree.yaml").write_text(yaml.safe_dump(content))
            output = self.load_default(directory)
            self.assertFalse(Subject.objects.filter(name="New subject").exists())
            self.assertFalse(Skill.objects.filter(name="New child").exists())
            self.assertTrue(Skill.objects.filter(pk=skill.pk, is_retired=True).exists())
            self.assertIn("retired_reference_subject: 1", output)
            self.assertIn("retired_reference_skill: 1", output)
            self.assertTrue(ItemDefinition.objects.filter(slug="unrelated-startup-food").exists())

    def test_existing_quest_scalar_and_all_links_rollback_on_new_retired_tag(self):
        with TemporaryDirectory() as directory:
            retired = self.seed_and_retire(directory, keyed=False)
            available = Skill.objects.create(name="Available practice", category=retired.category)
            item = ItemDefinition.objects.create(slug="saved-practice-food", name="Saved snack", item_type="food")
            quest = QuestDefinition.objects.create(name="Future practice", description="Saved promise", is_system=True,
                quest_type="collection", target_value=2, coin_reward=7,
                trigger_filter={"allowed_triggers": ["habit_log"]})
            QuestSkillTag.objects.create(quest_definition=quest, skill=available, xp_weight=3)
            reward = QuestRewardItem.objects.create(quest_definition=quest, item=item, quantity=2)
            root = Path(directory)
            content = yaml.safe_load((root / "quests.yaml").read_text())
            content["quests"][0]["reward_items"] = [{"slug": item.slug, "quantity": 9}]
            (root / "quests.yaml").write_text(yaml.safe_dump(content))
            output = self.load_default(directory)
            quest.refresh_from_db()
            reward.refresh_from_db()
            self.assertEqual((quest.description, quest.target_value, quest.coin_reward), ("Saved promise", 2, 7))
            self.assertEqual(reward.quantity, 2)
            self.assertEqual(list(quest.skill_tags.values_list("skill_id", "xp_weight")), [(available.pk, 3)])
            self.assertNotIn("updated quest:", output)
            self.assertNotIn("updated quest_reward:", output)
            self.assertIn("retired_reference_quest: 1", output)

    def test_existing_retired_tag_is_retained_and_can_receive_safe_metadata_update(self):
        with TemporaryDirectory() as directory:
            retired = self.seed_and_retire(directory, keyed=False)
            quest = QuestDefinition.objects.create(name="Future practice", is_system=True, quest_type="collection",
                target_value=1, trigger_filter={"allowed_triggers": ["habit_log"]})
            QuestSkillTag.objects.create(quest_definition=quest, skill=retired)
            self.load_default(directory)
            quest.refresh_from_db()
            self.assertEqual(quest.description, "Synthetic future practice")
            self.assertEqual(list(quest.skill_tags.values_list("skill_id", flat=True)), [retired.pk])

    def test_retired_new_prerequisite_preserves_existing_skill_scalars_and_full_set(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            content = {"categories": [{"name": "Startup practice"}], "skills": [
                {"name": name, "category": "Startup practice", **values} for name, values in (
                    ("Saved target", {}), ("Retired target", {}),
                    ("Dependent", {"description": "Saved rules", "locked": True, "prereqs": [{"skill": "Saved target", "level": 3}]}),
                )]}
            (root / "skill_tree.yaml").write_text(yaml.safe_dump(content))
            ContentPack(root).load()
            target = Skill.objects.get(name="Retired target")
            self.assertEqual(self.client.patch(f"/api/skills/{target.pk}/", {"is_retired": True}, format="json").status_code, 200)
            dependent = Skill.objects.get(name="Dependent")
            before = list(SkillPrerequisite.objects.filter(skill=dependent).values_list("required_skill_id", "required_level"))
            content["skills"][-1].update(description="Changed rules", locked=False,
                prereqs=[{"skill": "Saved target", "level": 5}, "Retired target"])
            (root / "skill_tree.yaml").write_text(yaml.safe_dump(content))
            output = self.load_default(directory)
            dependent.refresh_from_db()
            self.assertEqual((dependent.description, dependent.is_locked_by_default), ("Saved rules", True))
            self.assertEqual(list(SkillPrerequisite.objects.filter(skill=dependent).values_list("required_skill_id", "required_level")), before)
            self.assertIn("retired_reference_skill: 1", output)

    def test_unknown_reference_is_still_a_strict_atomic_failure(self):
        with TemporaryDirectory() as directory:
            self.seed_and_retire(directory, keyed=False)
            root = Path(directory)
            content = yaml.safe_load((root / "quests.yaml").read_text())
            content["quests"][0]["skill_tags"] = ["Missing skill"]
            (root / "quests.yaml").write_text(yaml.safe_dump(content))
            with self.assertRaisesMessage(CommandError, "unknown or ambiguous skill"):
                self.load_default(directory)
            self.assertFalse(ItemDefinition.objects.filter(slug="unrelated-startup-food").exists())
            self.assertFalse(QuestDefinition.objects.filter(name="Future practice").exists())

    def test_transitive_forward_retired_dependency_defers_existing_and_new_dependents(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            content = {"categories": [{"name": "Startup practice"}], "skills": [
                {"name": "Retired target", "category": "Startup practice"},
                {"name": "Saved target", "category": "Startup practice"},
                {"name": "Dependent", "category": "Startup practice", "description": "Saved rules",
                 "locked": True, "prereqs": [{"skill": "Saved target", "level": 3}]},
            ]}
            (root / "skill_tree.yaml").write_text(yaml.safe_dump(content))
            ContentPack(root).load()
            target = Skill.objects.get(name="Retired target")
            self.assertEqual(self.client.patch(f"/api/skills/{target.pk}/", {"is_retired": True}, format="json").status_code, 200)
            dependent = Skill.objects.get(name="Dependent")
            before = list(SkillPrerequisite.objects.filter(skill=dependent).values_list("required_skill_id", "required_level"))
            content["skills"] = [
                {"name": name, "category": "Startup practice", "description": "Changed rules", "prereqs": ["Forward target"]}
                for name in ("Dependent", "New dependent")
            ] + [{"name": "Forward target", "category": "Startup practice", "prereqs": ["Retired target"]}] + content["skills"][:2]
            (root / "skill_tree.yaml").write_text(yaml.safe_dump(content))
            output = self.load_default(directory)
            dependent.refresh_from_db()
            self.assertEqual((dependent.description, dependent.is_locked_by_default), ("Saved rules", True))
            self.assertEqual(list(SkillPrerequisite.objects.filter(skill=dependent).values_list("required_skill_id", "required_level")), before)
            self.assertFalse(Skill.objects.filter(name__in=["New dependent", "Forward target"]).exists())
            self.assertIn("retired_reference_skill: 3", output)

    def test_default_can_bootstrap_new_archived_ancestry_and_prerequisites(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skill_tree.yaml").write_text(yaml.safe_dump({
                "categories": [{"name": "Archived category", "is_retired": True}],
                "subjects": [{"name": "Archived subject", "category": "Archived category", "is_retired": True}],
                "skills": [{"name": name, "category": "Archived category", "subject": "Archived subject",
                            "is_retired": True, **extra} for name, extra in (
                                ("Archived dependent", {"prereqs": ["Archived target"]}), ("Archived target", {}),
                            )],
            }))
            self.load_default(directory)
            dependent = Skill.objects.get(name="Archived dependent")
            self.assertTrue(dependent.is_retired)
            self.assertEqual(list(SkillPrerequisite.objects.filter(skill=dependent).values_list("required_skill__name", flat=True)), ["Archived target"])

    def test_deferred_new_skill_and_quest_dependencies_do_not_stop_safe_entries(self):
        with TemporaryDirectory() as directory:
            self.seed_and_retire(directory, keyed=False)
            root = Path(directory)
            content = yaml.safe_load((root / "skill_tree.yaml").read_text())
            content["skills"] += [{"name": "Deferred skill", "category": "Startup practice", "prereqs": ["Saved practice"]}]
            (root / "skill_tree.yaml").write_text(yaml.safe_dump(content))
            quests = yaml.safe_load((root / "quests.yaml").read_text())
            quests["quests"][0]["skill_tags"] = ["Startup practice::Deferred skill"]
            quests["quests"] += [{"name": "Dependent quest", "description": "Deferred chain", "quest_type": "collection",
                "target_value": 1, "prerequisite_quest": "Future practice", "trigger_filter": {"allowed_triggers": ["habit_log"]}}]
            (root / "quests.yaml").write_text(yaml.safe_dump(quests))
            output = self.load_default(directory)
            self.assertFalse(Skill.objects.filter(name="Deferred skill").exists())
            self.assertFalse(QuestDefinition.objects.filter(name__in=["Future practice", "Dependent quest"]).exists())
            self.assertTrue(ItemDefinition.objects.filter(slug="unrelated-startup-food").exists())
            self.assertIn("retired_reference_skill: 1", output)
            self.assertIn("retired_reference_quest: 2", output)

    def test_same_named_deferred_skill_elsewhere_does_not_hide_unknown_prerequisite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skill_tree.yaml").write_text(yaml.safe_dump({
                "categories": [{"name": "Retired category"}, {"name": "Active category"}],
            }))
            ContentPack(root).load()
            from apps.achievements.models import SkillCategory
            retired = SkillCategory.objects.get(name="Retired category")
            self.assertEqual(self.client.patch(f"/api/categories/{retired.pk}/", {"is_retired": True}, format="json").status_code, 200)
            content = yaml.safe_load((root / "skill_tree.yaml").read_text())
            content["skills"] = [
                {"name": "Target", "category": "Retired category"},
                {"name": "Dependent", "category": "Active category", "prereqs": ["Target"]},
            ]
            (root / "skill_tree.yaml").write_text(yaml.safe_dump(content))
            with self.assertRaisesMessage(CommandError, "unknown prereq"):
                self.load_default(directory)
            self.assertFalse(Skill.objects.filter(name="Dependent").exists())
