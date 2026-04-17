"""Tests for the RPG content pack loader.

Exercises:
- Parity: the initial pack reproduces the catalog that ``seed_data.py``
  used to produce (counts + key FK resolutions).
- Idempotency: loading the same pack twice produces no net row changes.
- Dry-run: parses + runs inside a rolled-back transaction, zero writes.
- Namespace: a third-party pack prefixed with ``--namespace`` coexists
  with core content without slug collisions.
- Validation: malformed cross-references surface as ``ContentPackError``
  before any writes commit.
"""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.achievements.models import Badge, Skill, SkillPrerequisite
from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import QuestDefinition, QuestRewardItem
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.models import DropTable, ItemDefinition


INITIAL_PACK = Path("content/rpg/initial")


def _counts() -> dict[str, int]:
    return {
        "pet_species": PetSpecies.objects.count(),
        "potion_types": PotionType.objects.count(),
        "items": ItemDefinition.objects.count(),
        "drops": DropTable.objects.count(),
        "quests": QuestDefinition.objects.count(),
        "quest_rewards": QuestRewardItem.objects.count(),
        "badges": Badge.objects.count(),
        "skills": Skill.objects.count(),
        "skill_prereqs": SkillPrerequisite.objects.count(),
    }


class ContentPackInitialSeedTest(TestCase):
    """The initial pack reproduces the full catalog."""

    def test_fresh_load_creates_expected_catalog(self):
        call_command("loadrpgcontent")

        counts = _counts()
        # Parity floor — these are the minimum counts after seed_data.py's
        # old Python lists have been moved into content/rpg/initial/*.yaml.
        self.assertEqual(counts["pet_species"], 8)
        self.assertEqual(counts["potion_types"], 6)
        self.assertEqual(counts["quests"], 4)
        self.assertGreaterEqual(counts["badges"], 27)
        self.assertGreaterEqual(counts["skills"], 40)
        # Items: 8 eggs + 6 potions + 6 food + 3 pouches + 4 frames
        # + 4 titles + 3 themes + 3 accessories = 37
        self.assertEqual(counts["items"], 37)

    def test_eggs_have_pet_species_fk_and_slugs(self):
        call_command("loadrpgcontent")
        eggs = ItemDefinition.objects.filter(item_type=ItemDefinition.ItemType.EGG)
        self.assertEqual(eggs.count(), 8)
        for egg in eggs:
            self.assertTrue(egg.slug, f"{egg.name} has no slug")
            self.assertIsNotNone(
                egg.pet_species_id,
                f"{egg.name} has no pet_species FK — metadata-string lookup would fail",
            )

    def test_potion_items_have_potion_type_fk(self):
        call_command("loadrpgcontent")
        potions = ItemDefinition.objects.filter(item_type=ItemDefinition.ItemType.POTION)
        self.assertEqual(potions.count(), 6)
        for p in potions:
            self.assertIsNotNone(p.potion_type_id)

    def test_food_items_have_food_species_fk(self):
        call_command("loadrpgcontent")
        food = ItemDefinition.objects.filter(item_type=ItemDefinition.ItemType.FOOD)
        self.assertEqual(food.count(), 6)
        for f in food:
            self.assertIsNotNone(f.food_species_id)

    def test_pet_species_have_all_potions_by_default(self):
        call_command("loadrpgcontent")
        wolf = PetSpecies.objects.get(slug="wolf")
        # YAML doesn't specify available_potions → default to all potions.
        self.assertEqual(wolf.available_potions.count(), 6)

    def test_quest_reward_items_resolve(self):
        call_command("loadrpgcontent")
        quest = QuestDefinition.objects.get(name="Dragon Slayer")
        self.assertTrue(
            quest.reward_items.filter(item__slug="wolf-egg").exists(),
            "Dragon Slayer should have wolf-egg reward (from quests.yaml)",
        )


class IdempotencyTest(TestCase):
    def test_loading_twice_is_a_no_op_on_counts(self):
        call_command("loadrpgcontent")
        before = _counts()
        call_command("loadrpgcontent")
        after = _counts()
        self.assertEqual(before, after)


class DryRunTest(TestCase):
    def test_dry_run_does_not_commit(self):
        before = _counts()
        call_command("loadrpgcontent", "--dry-run")
        after = _counts()
        self.assertEqual(before, after)
        self.assertEqual(after["pet_species"], 0)  # DB untouched


class NamespaceTest(TestCase):
    def test_namespaced_pack_coexists_with_core(self):
        # Seed core first.
        call_command("loadrpgcontent")
        core_species = set(PetSpecies.objects.values_list("slug", flat=True))

        # Build a minimal third-party pack in a tmp dir.
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            (pack_path / "potion_types.yaml").write_text(
                textwrap.dedent(
                    """
                    potions:
                      - slug: rainbow
                        name: Rainbow
                        rarity: epic
                    """
                ).strip(),
                encoding="utf-8",
            )
            (pack_path / "pet_species.yaml").write_text(
                textwrap.dedent(
                    """
                    species:
                      - slug: koi
                        name: Koi
                        icon: "fish"
                        food_preference: fish
                    """
                ).strip(),
                encoding="utf-8",
            )

            ContentPack(pack_path, namespace="alt-").load()

        # Core wolf still there.
        self.assertIn("wolf", core_species)
        self.assertTrue(PetSpecies.objects.filter(slug="wolf").exists())
        # New species has prefixed slug — doesn't collide.
        self.assertTrue(PetSpecies.objects.filter(slug="alt-koi").exists())
        # Egg item auto-materialized and is also namespaced.
        self.assertTrue(
            ItemDefinition.objects.filter(slug="alt-koi-egg").exists()
        )
        self.assertTrue(
            ItemDefinition.objects.filter(slug="alt-rainbow-potion").exists()
        )
        # Core potion slugs untouched.
        self.assertTrue(PotionType.objects.filter(slug="fire").exists())


class ValidationTest(TestCase):
    def test_missing_potion_reference_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            (pack_path / "pet_species.yaml").write_text(
                textwrap.dedent(
                    """
                    species:
                      - slug: gryphon
                        name: Gryphon
                        icon: "eagle"
                        available_potions: [does-not-exist]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ContentPackError) as ctx:
                ContentPack(pack_path).load()
            self.assertIn("does-not-exist", str(ctx.exception))

        # Nothing committed.
        self.assertFalse(PetSpecies.objects.filter(slug="gryphon").exists())

    def test_bad_yaml_path_raises(self):
        with self.assertRaises(ContentPackError):
            ContentPack("/nonexistent/path").load()

    def test_unknown_trigger_in_drops_rules_raises(self):
        """A typo in drops.yaml 'triggers:' list should fail loading, not
        silently create DropTable rows with invalid trigger_type values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            # Need at least one item to reference
            (pack_path / "items.yaml").write_text(
                textwrap.dedent(
                    """
                    items:
                      - slug: test-pouch
                        name: Test Pouch
                        icon: "💰"
                        item_type: coin_pouch
                        rarity: common
                        coin_value: 10
                    """
                ).strip(),
                encoding="utf-8",
            )
            (pack_path / "drops.yaml").write_text(
                textwrap.dedent(
                    """
                    rules:
                      - triggers: [clock_ou]
                        item_slugs: [test-pouch]
                        weight: 5
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ContentPackError) as ctx:
                ContentPack(pack_path).load()
            self.assertIn("clock_ou", str(ctx.exception))

        self.assertFalse(DropTable.objects.filter(trigger_type="clock_ou").exists())

    def test_unknown_trigger_in_drops_macros_raises(self):
        """Same validation applies to the macros shape."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_path = Path(tmpdir)
            (pack_path / "items.yaml").write_text(
                textwrap.dedent(
                    """
                    items:
                      - slug: test-egg
                        name: Test Egg
                        icon: "🥚"
                        item_type: egg
                        rarity: common
                    """
                ).strip(),
                encoding="utf-8",
            )
            (pack_path / "drops.yaml").write_text(
                textwrap.dedent(
                    """
                    macros:
                      - triggers: [project_completion]
                        item_type: egg
                        weight_by_rarity: {common: 5}
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ContentPackError) as ctx:
                ContentPack(pack_path).load()
            self.assertIn("project_completion", str(ctx.exception))
