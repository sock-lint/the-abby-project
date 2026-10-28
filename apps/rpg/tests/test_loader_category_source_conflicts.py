"""Startup defers retained category conflicts without admitting new identities."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
import yaml

from apps.achievements import criteria
from apps.achievements.models import Badge, Skill, SkillCategory, SkillPrerequisite, Subject, UserBadge
from apps.achievements.services import BadgeService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.projects.models import Project
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.models import ContentPackEntry, ContentPackPublication, ItemDefinition, RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoaderCategorySourceConflictTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Loader category conflict", parents=[{
            "username": "loader-conflict-parent", "is_staff": True,
        }], children=[{"username": "loader-conflict-child"}])
        self.actor, self.child = family.parents[0], family.children[0]
        self.temporary = TemporaryDirectory(prefix="abby-loader-category-conflict-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def wire(self, name, params):
        with override_user(self.actor, scopes=frozenset({"mcp:catalog", "mcp:author", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        result = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", result, result)
        return result

    def retained(self, source="cooking", name="Baking"):
        category = SkillCategory.objects.get(pk=self.wire("create_category", {"name": source})["id"])
        self.wire("update_category", {"category_id": category.pk, "name": name})
        return category

    def pack(self, name="first", **sections):
        path = self.root / name
        path.mkdir(exist_ok=True)
        for filename, data in sections.items():
            (path / f"{filename}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    def startup(self, *paths, **options):
        out = StringIO()
        with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", tuple((path, "") for path in paths)), \
                patch("apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
            call_command("loadrpgcontent", stdout=out, **options)
        return out.getvalue()

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            SkillCategory, Subject, Skill, SkillPrerequisite, Badge, UserBadge, QuestDefinition,
            QuestRewardItem, QuestSkillTag, ItemDefinition, RPGContentOverride, ContentPackEntry, ContentPackPublication,
        )}

    def project_badge(self, category):
        Project.objects.create(title="Retained completed project", assigned_to=self.child,
            created_by=self.actor, category=category, status=Project.Status.COMPLETED)
        return Badge.objects.create(name="Saved Cooking project goal", description="Original goal",
            criteria_type="category_projects", criteria_value={"category": "Cooking", "count": 1}, award_coins=False)

    def tree(self):
        return {"categories": [{"name": "Cooking"}],
            "subjects": [{"name": "Kitchen", "category": "Cooking"}],
            "skills": [{"name": "Oven", "category": "Cooking", "subject": "Kitchen"}]}

    def test_manual_unkeyed_conflict_rejects_whole_load_atomically(self):
        retained = self.retained()
        badge = self.project_badge(retained)
        source = self.tree()
        source["categories"].insert(0, {"name": "Safe sibling"})
        path = self.pack(skill_tree=source, items={"items": [{"slug": "partial-food", "name": "Partial", "item_type": "food"}]})
        before = self.snapshot()
        with self.assertRaises(ContentPackError):
            ContentPack(path).load()
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(criteria.check(self.child, badge))
        with self.assertRaises(CommandError):
            call_command("loadrpgcontent", pack=str(path), stdout=StringIO())
        self.assertEqual(self.snapshot(), before)

    def test_default_startup_defers_category_children_and_named_badges(self):
        retained = self.retained()
        badge = self.project_badge(retained)
        path = self.pack(skill_tree=self.tree(), badges={"badges": [
            {"name": "New Cooking mastery", "criteria_type": "category_mastery", "criteria_value": {"category": "Cooking", "min_level": 1}},
            {"name": "New Cooking project", "criteria_type": "category_projects", "criteria_value": {"category": "Cooking", "count": 1}},
            {"name": "Independent plural project", "criteria_type": "category_projects", "criteria_value": {"category": "Cooking", "categories": 2}},
            {"name": "Independent uncategorized project", "criteria_type": "category_projects", "criteria_value": {"count": 1}},
        ]}, items={"items": [{"slug": "safe-food", "name": "Safe food", "item_type": "food"}]})
        output = self.startup(path)
        self.assertFalse(SkillCategory.objects.filter(name="Cooking").exists())
        self.assertFalse(Subject.objects.filter(name="Kitchen").exists())
        self.assertFalse(Skill.objects.filter(name="Oven").exists())
        self.assertFalse(Badge.objects.filter(name__startswith="New Cooking").exists())
        self.assertTrue(Badge.objects.filter(name="Independent plural project").exists())
        self.assertTrue(Badge.objects.filter(name="Independent uncategorized project").exists())
        self.assertTrue(ItemDefinition.objects.filter(slug="safe-food").exists())
        self.assertIn("category_source_conflict_category: 1", output)
        self.assertIn("Cooking", output)
        self.assertTrue(criteria.check(self.child, badge))
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [badge])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"project"}), [])

    def test_real_bundled_startup_never_introduces_retained_current_tie(self):
        retained = self.retained()
        badge = self.project_badge(retained)
        output = StringIO()
        call_command("loadrpgcontent", stdout=output)
        self.assertFalse(SkillCategory.objects.filter(name="Cooking").exists())
        self.assertTrue(criteria.check(self.child, badge))
        self.assertIn("category_source_conflict_category", output.getvalue())
        self.assertFalse(Badge.objects.filter(criteria_type="category_mastery", criteria_value__category="Cooking").exists())
        ids = {model: list(model.objects.order_by("pk").values_list("pk", flat=True)) for model in (SkillCategory, Subject, Skill, Badge)}
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(ids, {model: list(model.objects.order_by("pk").values_list("pk", flat=True)) for model in ids})

    def test_project_selector_case_variants_defer_but_exact_mastery_keeps_its_identity(self):
        self.retained()
        path = self.pack(skill_tree=self.tree(), badges={"badges": [
            {"name": "Uppercase Cooking project", "criteria_type": "category_projects", "criteria_value": {"category": "COOKING", "count": 1}},
            {"name": "Mixed Cooking project", "criteria_type": "category_projects", "criteria_value": {"category": "cOoKiNg", "count": 1}},
            {"name": "Exact retained mastery", "criteria_type": "category_mastery", "criteria_value": {"category": "cooking", "min_level": 1}},
        ]})
        self.startup(path)
        self.assertFalse(Badge.objects.filter(name__in=["Uppercase Cooking project", "Mixed Cooking project"]).exists())
        self.assertTrue(Badge.objects.filter(name="Exact retained mastery").exists())

    def test_cross_pack_forward_prerequisites_quests_and_bare_names_defer(self):
        self.retained()
        safe = SkillCategory.objects.create(name="Safe")
        old_target = Skill.objects.create(category=safe, name="Saved target")
        Skill.objects.create(category=safe, name="Oven")  # Must not acquire a deferred bare tag.
        dependent = Skill.objects.create(category=safe, name="Dependent", description="Saved rules", is_locked_by_default=True)
        SkillPrerequisite.objects.create(skill=dependent, required_skill=old_target, required_level=3)
        quest = QuestDefinition.objects.create(name="Dependent challenge", description="Saved challenge", quest_type="collection", target_value=4, required_skill=old_target, required_skill_level=1, is_system=True)
        first = self.pack(skill_tree=self.tree())
        second = self.pack("second", skill_tree={"categories": [{"name": "Safe"}], "skills": [
            {"name": "Forward dependent", "category": "Safe", "prereqs": ["Dependent"]},
            {"name": "Dependent", "category": "Safe", "description": "Must not apply", "locked": False, "prereqs": ["Cooking::Oven"]},
            {"name": "Independent", "category": "Safe"},
        ]})
        third = self.pack("third", quests={"quests": [
            {"name": "Dependent challenge", "description": "Must not apply", "quest_type": "collection", "target_value": 99, "required_skill": "Safe::Forward dependent", "required_skill_level": 1},
            {"name": "Later challenge", "quest_type": "collection", "target_value": 1, "prerequisite_quest": "Dependent challenge"},
            {"name": "Bare tag challenge", "quest_type": "collection", "target_value": 1, "skill_tags": ["Oven"]},
            {"name": "Independent challenge", "quest_type": "collection", "target_value": 1},
        ]})
        try:
            self.startup(first, second, third)
        except CommandError as error:
            self.fail(f"Known conflicting source dependencies must defer without blocking startup: {error}")
        dependent.refresh_from_db()
        quest.refresh_from_db()
        self.assertEqual((dependent.description, dependent.is_locked_by_default), ("Saved rules", True))
        self.assertEqual(list(dependent.prerequisites.values_list("required_skill_id", "required_level")), [(old_target.pk, 3)])
        self.assertFalse(Skill.objects.filter(name="Forward dependent").exists())
        self.assertTrue(Skill.objects.filter(name="Independent").exists())
        self.assertEqual((quest.description, quest.target_value, quest.required_skill_id), ("Saved challenge", 4, old_target.pk))
        self.assertFalse(QuestDefinition.objects.filter(name__in=["Later challenge", "Bare tag challenge"]).exists())
        self.assertTrue(QuestDefinition.objects.filter(name="Independent challenge").exists())

    def test_late_deferred_tag_rolls_back_existing_quest_scalars_rewards_and_tags(self):
        self.retained()
        safe = SkillCategory.objects.create(name="Safe")
        skill = Skill.objects.create(category=safe, name="Saved skill")
        item = ItemDefinition.objects.create(slug="saved-food", name="Saved food", item_type="food")
        quest = QuestDefinition.objects.create(name="Saved challenge", description="Saved promise", quest_type="collection", target_value=2, coin_reward=7, is_system=True)
        QuestSkillTag.objects.create(quest_definition=quest, skill=skill, xp_weight=3)
        reward = QuestRewardItem.objects.create(quest_definition=quest, item=item, quantity=2)
        path = self.pack(skill_tree=self.tree(), quests={"quests": [{"name": quest.name,
            "description": "Must roll back", "quest_type": "collection", "target_value": 99, "coin_reward": 90,
            "reward_items": [{"slug": item.slug, "quantity": 9}], "skill_tags": ["Cooking::Oven"]}]})
        self.startup(path)
        quest.refresh_from_db()
        reward.refresh_from_db()
        self.assertEqual((quest.description, quest.target_value, quest.coin_reward), ("Saved promise", 2, 7))
        self.assertEqual(reward.quantity, 2)
        self.assertEqual(list(quest.skill_tags.values_list("skill_id", "xp_weight")), [(skill.pk, 3)])

    def test_deferred_named_badge_blocks_cross_pack_required_badge(self):
        self.retained()
        first = self.pack(skill_tree=self.tree(), badges={"badges": [{"name": "Cooking mastery",
            "criteria_type": "category_mastery", "criteria_value": {"category": "Cooking", "min_level": 1}}]})
        second = self.pack("second", quests={"quests": [{"name": "Badge challenge", "quest_type": "collection",
            "target_value": 1, "required_badge": "Cooking mastery"}]})
        self.startup(first, second)
        self.assertFalse(Badge.objects.filter(name="Cooking mastery").exists())
        self.assertFalse(QuestDefinition.objects.filter(name="Badge challenge").exists())

    def test_current_case_union_and_exact_retained_source_remain_idempotent(self):
        current = [self.wire("create_category", {"name": name})["id"] for name in ("Practice", "PRACTICE")]
        retained = self.retained()
        path = self.pack(skill_tree={"categories": [{"name": name} for name in ("Practice", "PRACTICE", "cooking")],
            "skills": [{"name": "Exact source child", "category": "cooking"}]})
        self.startup(path)
        self.startup(path)
        self.assertEqual(set(SkillCategory.objects.values_list("pk", flat=True)), {*current, retained.pk})
        self.assertEqual(Skill.objects.get(name="Exact source child").category_id, retained.pk)
        self.assertEqual(RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=retained.pk).source_lookup, {"name": "cooking"})

    def test_retirement_and_fresh_archived_bootstrap_keep_existing_policy(self):
        path = self.pack(skill_tree={"categories": [{"name": "Archived", "is_retired": True}],
            "skills": [{"name": "Archived child", "category": "Archived", "is_retired": True}]})
        ContentPack(path).load()
        self.startup(path)
        self.assertTrue(SkillCategory.objects.get(name="Archived").is_retired)
        self.assertTrue(Skill.objects.get(name="Archived child").is_retired)

    def test_unknown_reference_is_strict_despite_a_known_category_conflict(self):
        self.retained()
        tree = self.tree()
        tree["categories"].append({"name": "Safe"})
        tree["skills"].append({"name": "Invalid", "category": "Safe", "prereqs": ["Unknown prerequisite"]})
        path = self.pack(skill_tree=tree)
        before = self.snapshot()
        with self.assertRaises(CommandError):
            self.startup(path)
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_and_repair_do_not_leak_deferral_markers(self):
        retained = self.retained()
        path = self.pack(skill_tree=self.tree())
        before = self.snapshot()
        self.startup(path, dry_run=True)
        self.assertEqual(self.snapshot(), before)
        self.startup(path)
        self.assertFalse(SkillCategory.objects.filter(name="Cooking").exists())
        self.wire("update_category", {"category_id": retained.pk, "name": "cooking"})
        self.startup(path)
        self.assertTrue(SkillCategory.objects.filter(name="Cooking").exists())
        self.assertTrue(Skill.objects.filter(name="Oven", category__name="Cooking").exists())

    def test_multiple_legacy_retained_aliases_are_reported_without_new_namesake(self):
        for name, source in (("First legacy", "Cooking"), ("Second legacy", "COOKING")):
            category = SkillCategory.objects.create(name=name)
            RPGContentOverride.objects.create(family=self.actor.family, model_label="achievements.skillcategory",
                object_id=category.pk, source_lookup={"name": source}, values={"_authoring": {"version": 1, "source": "mcp"}})
        path = self.pack(skill_tree={"categories": [{"name": "cooking"}]},
            items={"items": [{"slug": "unrelated", "name": "Unrelated", "item_type": "food"}]})
        self.startup(path)
        self.assertFalse(SkillCategory.objects.filter(name="cooking").exists())
        self.assertTrue(ItemDefinition.objects.filter(slug="unrelated").exists())

    def test_keyed_new_alias_stays_strict_without_claim_or_partial_rows(self):
        self.retained()
        path = self.pack(skill_tree=self.tree())
        before = self.snapshot()
        with self.assertRaises(ContentPackError):
            ContentPack(path, pack_key="reviewed", family=self.actor.family).load()
        self.assertEqual(self.snapshot(), before)
