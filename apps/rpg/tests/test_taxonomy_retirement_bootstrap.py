"""Fresh archived source graphs remain loadable without admitting new work."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase

from apps.achievements.models import Skill, SkillCategory, SkillPrerequisite, Subject
from apps.achievements.taxonomy import available_categories, available_skills, available_subjects
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, ContentPackError
from config.tests.factories import make_family


class TaxonomyRetirementBootstrapTests(TestCase):
    @staticmethod
    def source(retired=True):
        flag = f"\n    is_retired: {str(retired).lower()}"
        return (
            f"categories:\n  - name: Lifecycle{flag}\n"
            f"subjects:\n  - name: Group\n    category: Lifecycle{flag}\n"
            "skills:\n  - name: Practice\n    category: Lifecycle\n"
            f"    subject: Group\n    levels: {{'1': Beginner}}{flag}\n"
        )

    def test_fresh_load_of_retired_tree(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "skill_tree.yaml").write_text(self.source(True))
            ContentPack(directory).load()
            for model in (SkillCategory, Subject, Skill):
                self.assertTrue(model.objects.get().is_retired)
            self.assertFalse(available_categories().exists())
            self.assertFalse(available_subjects().exists())
            self.assertFalse(available_skills().exists())

    def test_fresh_owned_pack_loads_archived_tree_and_reloads_same_identities(self):
        parent = make_family(parents=[{"username": "archive-bootstrap", "is_staff": True}]).parents[0]
        with TemporaryDirectory() as directory:
            (Path(directory) / "skill_tree.yaml").write_text(self.source(True))
            pack = ContentPack(directory, pack_key="archive-bootstrap", family=parent.family)
            pack.load()
            identities = {model: model.objects.get().pk for model in (SkillCategory, Subject, Skill)}
            pack.load()
            for model, pk in identities.items():
                self.assertEqual(model.objects.get().pk, pk)
                self.assertTrue(model.objects.get().is_retired)

    def test_new_children_inherit_retirement_without_changing_their_own_flags(self):
        with TemporaryDirectory() as directory:
            source = self.source(False).replace("name: Lifecycle\n    is_retired: false", "name: Lifecycle\n    is_retired: true")
            (Path(directory) / "skill_tree.yaml").write_text(source)
            ContentPack(directory).load()
            self.assertTrue(SkillCategory.objects.get().is_retired)
            self.assertFalse(Subject.objects.get().is_retired)
            self.assertFalse(Skill.objects.get().is_retired)
            self.assertFalse(available_subjects().exists())
            self.assertFalse(available_skills().exists())

    def test_new_archived_prerequisite_graph_loads_but_remains_unavailable(self):
        with TemporaryDirectory() as directory:
            source = self.source(True) + (
                "  - name: Next\n    category: Lifecycle\n    subject: Group\n"
                "    is_retired: false\n    prereqs: [{skill: Practice, level: 3}]\n"
            )
            (Path(directory) / "skill_tree.yaml").write_text(source)
            ContentPack(directory).load()
            edge = SkillPrerequisite.objects.get()
            self.assertEqual(edge.skill.name, "Next")
            self.assertEqual(edge.required_skill.name, "Practice")
            self.assertEqual(edge.required_level, 3)
            self.assertFalse(available_skills().exists())

    def test_new_active_dependent_cannot_select_new_retired_prerequisite(self):
        with TemporaryDirectory() as directory:
            source = self.source(False).replace(
                "levels: {'1': Beginner}\n    is_retired: false",
                "levels: {'1': Beginner}\n    is_retired: true",
            ) + "  - name: Next\n    category: Lifecycle\n    prereqs: [Practice]\n"
            (Path(directory) / "skill_tree.yaml").write_text(source)
            with self.assertRaisesMessage(ContentPackError, "Retired taxonomy entries"):
                ContentPack(directory).load()
            self.assertFalse(SkillCategory.objects.exists())
            self.assertFalse(Skill.objects.exists())

    def test_new_archived_dependent_cannot_select_existing_retired_prerequisite(self):
        with TemporaryDirectory() as directory:
            source_path = Path(directory) / "skill_tree.yaml"
            source_path.write_text(self.source(False))
            ContentPack(directory).load()
            Skill.objects.update(is_retired=True)
            source_path.write_text(self.source(False).replace(
                "levels: {'1': Beginner}\n    is_retired: false",
                "levels: {'1': Beginner}\n    is_retired: true",
            ) + "  - name: Next\n    category: Lifecycle\n    is_retired: true\n    prereqs: [Practice]\n")
            with self.assertRaisesMessage(ContentPackError, "Retired taxonomy entries"):
                ContentPack(directory).load()
            self.assertFalse(Skill.objects.filter(name="Next").exists())

    def test_successful_reused_loader_cannot_add_to_previously_created_retired_parent(self):
        with TemporaryDirectory() as directory:
            source_path = Path(directory) / "skill_tree.yaml"
            source_path.write_text(self.source(True))
            pack = ContentPack(directory)
            pack.load()
            source_path.write_text(self.source(True).replace(
                "subjects:\n", "subjects:\n  - name: Fresh\n    category: Lifecycle\n",
            ))
            with self.assertRaisesMessage(ContentPackError, "Retired taxonomy entries"):
                pack.load()
            self.assertFalse(Subject.objects.filter(name="Fresh").exists())

    def test_failed_reused_loader_cannot_admit_existing_parent_with_reused_id(self):
        self._assert_rolled_back_loader_does_not_retain_parent(dry_run=False)

    def test_dry_run_reused_loader_cannot_admit_existing_parent_with_reused_id(self):
        self._assert_rolled_back_loader_does_not_retain_parent(dry_run=True)

    def _assert_rolled_back_loader_does_not_retain_parent(self, *, dry_run):
        with TemporaryDirectory() as directory:
            (Path(directory) / "skill_tree.yaml").write_text(self.source(True))
            pack = ContentPack(directory)
            created_ids = []

            def after_tree(*_args):
                created_ids.append(SkillCategory.objects.get().pk)
                if not dry_run:
                    raise ContentPackError("Later section rejected")

            with patch.object(pack, "_load_badges", side_effect=after_tree):
                if dry_run:
                    pack.load(dry_run=True)
                else:
                    with self.assertRaisesMessage(ContentPackError, "Later section rejected"):
                        pack.load()
            self.assertFalse(SkillCategory.objects.exists())
            self.assertFalse(Subject.objects.exists())
            self.assertFalse(Skill.objects.exists())
            SkillCategory.objects.create(pk=created_ids[0], name="Lifecycle", is_retired=True)
            with self.assertRaisesMessage(ContentPackError, "Retired taxonomy entries"):
                pack.load()
            self.assertFalse(Subject.objects.exists())

    def test_new_quest_cannot_select_skill_created_in_fresh_archived_graph(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "skill_tree.yaml").write_text(self.source(True))
            (Path(directory) / "quests.yaml").write_text(
                "quests:\n  - name: Fresh\n    quest_type: collection\n    target_value: 1\n"
                "    skill_tags: ['Lifecycle::Practice']\n"
            )
            with self.assertRaisesMessage(ContentPackError, "Retired taxonomy entries"):
                ContentPack(directory).load()
            self.assertFalse(SkillCategory.objects.exists())
            self.assertFalse(QuestDefinition.objects.exists())
