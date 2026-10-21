"""Optional taxonomy lifecycle fields survive loader and publication boundaries."""
import io
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.publication import preview_content_pack, publish_content_pack
from apps.quests.models import QuestDefinition
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyRetirementContentTests(TestCase):
    def source(self, retired=None):
        flag = "" if retired is None else f"\n    is_retired: {str(retired).lower()}"
        return (f"categories:\n  - name: Lifecycle{flag}\nsubjects:\n  - name: Group\n    category: Lifecycle{flag}"
                f"\nskills:\n  - name: Practice\n    category: Lifecycle\n    subject: Group\n    levels: {{'1': Beginner}}{flag}\n")

    def test_loader_explicit_flags_omit_preserves_and_false_restores(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "skill_tree.yaml"
            source.write_text(self.source(False))
            ContentPack(directory).load()
            source.write_text(self.source(True))
            ContentPack(directory).load()
            for model in (SkillCategory, Subject, Skill):
                self.assertIs(getattr(model.objects.get(), "is_retired", None), True)
            source.write_text(self.source())
            ContentPack(directory).load()
            for model in (SkillCategory, Subject, Skill):
                self.assertIs(model.objects.get().is_retired, True)
            source.write_text(self.source(False))
            ContentPack(directory).load()
            for model in (SkillCategory, Subject, Skill):
                self.assertIs(model.objects.get().is_retired, False)

    def test_owned_pack_accepts_typed_retirement_flags(self):
        parent = make_family(parents=[{"username": "retire-pack", "is_staff": True}]).parents[0]
        with TemporaryDirectory() as directory:
            source = Path(directory) / "skill_tree.yaml"
            source.write_text(self.source(False))
            ContentPack(directory, pack_key="lifecycle", family=parent.family).load()
            source.write_text(self.source(True))
            ContentPack(directory, pack_key="lifecycle", family=parent.family).load()
            self.assertIs(getattr(Skill.objects.get(), "is_retired", None), True)
            source.write_text(self.source())
            ContentPack(directory, pack_key="lifecycle", family=parent.family).load()
            self.assertTrue(Skill.objects.get().is_retired)

    def test_new_subject_cannot_select_a_retired_category(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "skill_tree.yaml"
            source.write_text(self.source())
            ContentPack(directory).load()
            SkillCategory.objects.update(is_retired=True)
            source.write_text(self.source().replace("subjects:", "subjects:\n  - name: New group\n    category: Lifecycle"))
            with self.assertRaises(ContentPackError):
                ContentPack(directory).load()
            self.assertFalse(Subject.objects.filter(name="New group").exists())

    def test_new_prerequisite_cannot_select_a_retired_skill(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "skill_tree.yaml"
            source.write_text(self.source())
            ContentPack(directory).load()
            Skill.objects.update(is_retired=True)
            source.write_text(self.source() + "  - name: Next\n    category: Lifecycle\n    prereqs: [Practice]\n")
            with self.assertRaises(ContentPackError):
                ContentPack(directory).load()
            self.assertFalse(Skill.objects.filter(name="Next").exists())

    def test_new_quest_cannot_select_retired_reward_skill_but_existing_links_reload(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "skill_tree.yaml"
            source.write_text(self.source())
            quests = Path(directory) / "quests.yaml"
            quests.write_text("quests:\n  - name: Existing\n    quest_type: collection\n    target_value: 1\n    skill_tags: ['Lifecycle::Practice']\n")
            ContentPack(directory).load()
            Skill.objects.update(is_retired=True)
            ContentPack(directory).load()
            self.assertEqual(QuestDefinition.objects.get(name="Existing").skill_tags.count(), 1)
            quests.write_text(quests.read_text() + "  - name: Fresh\n    quest_type: collection\n    target_value: 1\n    skill_tags: ['Lifecycle::Practice']\n")
            with self.assertRaises(ContentPackError):
                ContentPack(directory).load()
            self.assertFalse(QuestDefinition.objects.filter(name="Fresh").exists())

    def test_wrong_type_retirement_rejects_atomically(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "skill_tree.yaml").write_text(self.source().replace("- name: Lifecycle", "- name: Lifecycle\n    is_retired: 'false'"))
            with self.assertRaises(ContentPackError):
                ContentPack(directory).load()
            self.assertFalse(SkillCategory.objects.exists())

    def test_rest_retirement_survives_actual_default_reload_and_restoration(self):
        parent = make_family(parents=[{"username": "retire-bundled", "is_staff": True}]).parents[0]
        call_command("loadrpgcontent", stdout=io.StringIO())
        skill = Skill.objects.get(category__name="Physical", name="Endurance")
        client = APIClient()
        client.force_authenticate(parent)
        for retired in (True, False):
            response = client.patch(f"/api/skills/{skill.pk}/", {"is_retired": retired}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertIs(response.data.get("is_retired"), retired)
            call_command("loadrpgcontent", stdout=io.StringIO())
            skill.refresh_from_db()
            self.assertIs(skill.is_retired, retired)

    def test_retirement_changes_invalidate_an_existing_reviewed_publication(self):
        parent = make_family(parents=[{"username": "retire-preview", "is_staff": True}]).parents[0]
        with TemporaryDirectory() as directory:
            source = Path(directory) / "skill_tree.yaml"
            source.write_text(self.source())
            ContentPack(directory, pack_key="lifecycle", family=parent.family).load()
            plan = preview_content_pack(directory, "lifecycle", parent)
            Skill.objects.update(is_retired=True)
            with self.assertRaisesMessage(ContentPackError, "state changed"):
                publish_content_pack(directory, "lifecycle", parent, plan["preview_id"], plan["content_digest"])
            self.assertTrue(Skill.objects.get().is_retired)

    def test_new_quest_filter_cannot_select_retired_category(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "skill_tree.yaml").write_text(self.source())
            ContentPack(directory).load()
            category = SkillCategory.objects.get()
            SkillCategory.objects.filter(pk=category.pk).update(is_retired=True)
            (Path(directory) / "quests.yaml").write_text(
                f"quests:\n  - name: Fresh filtered\n    quest_type: collection\n    target_value: 1\n    trigger_filter: {{skill_category_id: {category.pk}}}\n")
            with self.assertRaises(ContentPackError):
                ContentPack(directory).load()
            self.assertFalse(QuestDefinition.objects.filter(name="Fresh filtered").exists())
