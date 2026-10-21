"""Normal deployment loads additive first-party paths without editing the seed."""
from io import StringIO
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import yaml
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge
from apps.quests.models import Quest, QuestDefinition, QuestRewardItem
from apps.rpg.content.loader import ContentPackError
from apps.rpg.models import CharacterProfile, ContentPackEntry, DropTable, ItemDefinition, UserInventory
from apps.rpg.progression.catalog import snapshot_catalog
from apps.rpg.progression.engine import Trial
from apps.rpg.services import ConsumableService, DropService
from apps.pets.expeditions import ExpeditionService
from config.tests.factories import make_family


class BundledProgressionContentTests(TestCase):
    def test_first_default_load_preserves_parent_definition_and_accepted_rewards(self):
        family = make_family("Parent reading", parents=[{"username": "reading-parent"}])
        parent = QuestDefinition.objects.create(
            name="Reading Routine", description="Our own reading promise", created_by=family.parents[0],
            quest_type="collection", target_value=2, coin_reward=50, xp_reward=7,
        )
        food = ItemDefinition.objects.create(slug="parent-reading-food", name="Parent food", item_type="food")
        link = QuestRewardItem.objects.create(quest_definition=parent, item=food, quantity=3)
        accepted = Quest.objects.create(definition=parent, end_date=timezone.now() + timedelta(days=7))
        original = QuestDefinition.objects.filter(pk=parent.pk).values().get()

        call_command("loadrpgcontent", stdout=StringIO())

        self.assertEqual(QuestDefinition.objects.filter(pk=parent.pk).values().get(), original)
        self.assertEqual(list(parent.reward_items.values_list("pk", "item_id", "quantity")), [(link.pk, food.pk, 3)])
        accepted.refresh_from_db()
        self.assertEqual(accepted.definition_id, parent.pk)
        self.assertEqual([(row["item_id"], row["quantity"]) for row in accepted.reward_items_snapshot], [(food.pk, 3)])
        system = QuestDefinition.objects.get(name="Reading Routine", is_system=True, created_by=None)
        self.assertNotEqual(system.pk, parent.pk)
        self.assertEqual((system.target_value, system.coin_reward), (5, 0))
        visitor = make_family("Other reading family", parents=[{"username": "other-reading-parent"}]).parents[0]
        client = APIClient()
        client.force_authenticate(visitor)
        response = client.get("/api/quests/available/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(system.pk, {row["id"] for row in response.data})
        self.assertNotIn(parent.pk, {row["id"] for row in response.data})

    def test_default_reload_ignores_later_parent_names_even_with_system_flag(self):
        call_command("loadrpgcontent", stdout=StringIO())
        system = QuestDefinition.objects.get(name="Reading Routine", is_system=True, created_by=None)
        family = make_family("Later parent reading", parents=[{"username": "later-reading-parent"}])
        parents = [QuestDefinition.objects.create(
            name="Reading Routine", description="A saved family promise", created_by=family.parents[0],
            quest_type="collection", target_value=2, coin_reward=50, is_system=flag,
        ) for flag in (False, True)]
        original = list(QuestDefinition.objects.filter(pk__in=[p.pk for p in parents]).order_by("pk").values())

        call_command("loadrpgcontent", stdout=StringIO())

        self.assertEqual(list(QuestDefinition.objects.filter(pk__in=[p.pk for p in parents]).order_by("pk").values()), original)
        self.assertEqual(QuestDefinition.objects.get(name="Reading Routine", is_system=True, created_by=None).pk, system.pk)

    def test_default_load_leaves_a_published_quest_unchanged_without_failing_startup(self):
        published = QuestDefinition.objects.create(
            name="Reading Routine", description="A separately published promise", is_system=True,
            quest_type="collection", target_value=2, coin_reward=50,
        )
        claim = ContentPackEntry.objects.create(
            pack="published-reading", kind="questdefinition", key="reading", model_label="quests.questdefinition",
            object_id=published.pk,
        )
        original = QuestDefinition.objects.filter(pk=published.pk).values().get()
        out = StringIO()

        call_command("loadrpgcontent", stdout=out)

        self.assertEqual(QuestDefinition.objects.filter(pk=published.pk).values().get(), original)
        self.assertEqual(ContentPackEntry.objects.get(pk=claim.pk).object_id, published.pk)
        self.assertEqual(QuestDefinition.objects.filter(name="Reading Routine").count(), 1)
        self.assertTrue(ItemDefinition.objects.exists(), "the rest of the bundled batch still loads")
        self.assertIn("owned by published-reading", out.getvalue())

    def test_ambiguous_global_quest_names_are_left_unchanged_without_failing_startup(self):
        for target in (2, 9):
            QuestDefinition.objects.create(
                name="Reading Routine", description="Ambiguous existing catalog", is_system=True,
                quest_type="collection", target_value=target,
            )
        original = list(QuestDefinition.objects.filter(name="Reading Routine").order_by("pk").values())
        out = StringIO()

        call_command("loadrpgcontent", stdout=out)

        self.assertEqual(list(QuestDefinition.objects.filter(name="Reading Routine").order_by("pk").values()), original)
        self.assertTrue(ItemDefinition.objects.exists(), "the rest of the bundled batch still loads")
        self.assertIn("more than one definition matches", out.getvalue())

    def test_default_reload_keeps_accepted_rules_for_active_global_legacy_quest(self):
        call_command("loadrpgcontent", stdout=StringIO())
        system = QuestDefinition.objects.get(name="Reading Routine", is_system=True, created_by=None)
        system.coin_reward = 50
        system.save(update_fields=["coin_reward"])
        accepted = Quest.objects.create(definition=system, end_date=timezone.now() + timedelta(days=7))
        # Links the active quest relies on also differ from the YAML; a
        # skipped definition must not have them reconciled underneath it.
        QuestRewardItem.objects.filter(quest_definition=system).update(quantity=5)
        system.skill_tags.all().delete()
        out = StringIO()

        # A later YAML/admin change must not stop the deploy-time load that
        # runs before gunicorn; the accepted rules are kept instead.
        call_command("loadrpgcontent", stdout=out)

        system.refresh_from_db()
        self.assertEqual(system.coin_reward, 50)
        self.assertEqual(list(system.reward_items.values_list("quantity", flat=True)), [5])
        self.assertFalse(system.skill_tags.exists())
        self.assertIn("active legacy quest(s) retain its accepted coin_reward", out.getvalue())
        accepted.refresh_from_db()
        self.assertIsNotNone(accepted.reward_items_snapshot, "accepted item promises are frozen")

        accepted.status = Quest.Status.COMPLETED
        accepted.save(update_fields=["status"])
        call_command("loadrpgcontent", stdout=StringIO())
        system.refresh_from_db()
        self.assertEqual(system.coin_reward, 0, "the bundled change applies once no active quest relies on it")
        self.assertEqual(list(system.reward_items.values_list("quantity", flat=True)), [2])
        self.assertEqual(system.skill_tags.count(), 1)

    def test_previously_taken_over_parent_row_never_fails_a_later_startup(self):
        # main's name-only loader could adopt a family's same-name quest in
        # place (is_system=True with its creator kept). Deleting that parent
        # later leaves two creatorless global rows.
        family = make_family("Taken over", parents=[{"username": "taken-over-parent"}])
        adopted = QuestDefinition.objects.create(
            name="Reading Routine", description="Adopted by an earlier loader", is_system=True,
            created_by=family.parents[0], quest_type="collection", target_value=5,
        )
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(QuestDefinition.objects.filter(name="Reading Routine", created_by=None).count(), 1)

        family.parents[0].delete()
        adopted.refresh_from_db()
        self.assertIsNone(adopted.created_by_id)
        before = list(QuestDefinition.objects.filter(name="Reading Routine").order_by("pk").values())
        out = StringIO()

        call_command("loadrpgcontent", stdout=out)

        self.assertEqual(list(QuestDefinition.objects.filter(name="Reading Routine").order_by("pk").values()), before)
        self.assertIn("more than one definition matches", out.getvalue())

    def test_default_load_reads_no_pack_from_a_runtime_bind_mount(self):
        # Production bind-mounts the host's content/rpg/packs over the image
        # copy for MCP-authored packs. A default pack under a mount is missing
        # there, and its "Pack directory not found" stops gunicorn from starting.
        from apps.rpg.management.commands.loadrpgcontent import BUNDLED_PACKS
        compose_file = Path(settings.BASE_DIR) / "docker-compose.yml"
        if not compose_file.exists():
            # .dockerignore leaves the compose file out of the image, so an
            # in-container test run has no mounts to compare against.
            self.skipTest("docker-compose.yml is not part of this checkout")
        compose = yaml.safe_load(compose_file.read_text())
        mounted = [
            Path(volume.split(":")[1]).relative_to("/app")
            for volume in compose["services"]["django"]["volumes"]
            if isinstance(volume, str) and volume.startswith("./") and volume.split(":")[1].startswith("/app/")
        ]
        self.assertIn(Path("content/rpg/packs"), mounted)
        for pack, _namespace in BUNDLED_PACKS:
            self.assertTrue((Path(settings.BASE_DIR) / pack).is_dir(), pack)
            for target in mounted:
                self.assertFalse(Path(pack).is_relative_to(target), f"{pack} is hidden by the {target} bind mount")

    def test_default_load_includes_registered_additive_packs_with_stable_namespaces(self):
        calls = []
        class Pack:
            def __init__(self, path, namespace):
                calls.append((Path(path).name, namespace))
            def load(self, **kwargs):
                pass
        with patch("apps.rpg.management.commands.loadrpgcontent.ContentPack", Pack), patch.object(Path, "is_dir", return_value=True):
            call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(calls, [("initial", ""), ("reading-adventures", "reading-adventures-"),
                                 ("collector-reading-2026", "collector-reading-2026-")])

    def test_explicit_pack_remains_single_and_does_not_inject_default_extras(self):
        calls = []
        class Pack:
            def __init__(self, path, namespace):
                calls.append((Path(path).name, namespace))
            def load(self, **kwargs):
                pass
        with patch("apps.rpg.management.commands.loadrpgcontent.ContentPack", Pack), patch.object(Path, "is_dir", return_value=True):
            call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())
        self.assertEqual(calls, [("initial", "")])

    def test_later_pack_failure_rolls_back_the_entire_default_batch(self):
        class Pack:
            def __init__(self, path, namespace):
                self.name = Path(path).name
            def load(self, **kwargs):
                if self.name == "collector-reading-2026":
                    raise ContentPackError("invalid final pack")
                ItemDefinition.objects.create(slug=self.name, name=self.name, item_type="food")
        with patch("apps.rpg.management.commands.loadrpgcontent.ContentPack", Pack), patch.object(Path, "is_dir", return_value=True):
            with self.assertRaises(CommandError):
                call_command("loadrpgcontent", stdout=StringIO())
        self.assertFalse(ItemDefinition.objects.exists())

    def test_real_default_reload_installs_paths_once_with_their_cross_pack_gates(self):
        call_command("loadrpgcontent", stdout=StringIO())
        names = {"Reading Companion", "Reading Routine", "Reading Voyager", "Collector's Reading: Fresh Pages",
                 "Collector's Reading: Far Horizons", "Collector's Reading: Living Atlas"}
        definitions = dict(QuestDefinition.objects.filter(name__in=names).values_list("name", "pk"))
        self.assertEqual(set(definitions), names)
        items = dict(ItemDefinition.objects.filter(slug__startswith="collector-reading-2026-").values_list("slug", "pk"))
        self.assertEqual(set(items), {"collector-reading-2026-title-pagefinder", "collector-reading-2026-frame-far-horizons",
                                      "collector-reading-2026-title-living-atlas"})
        badges = dict(Badge.objects.filter(name__startswith="Collector's Reading:").values_list("name", "pk"))
        self.assertEqual(len(badges), 3)
        original_drop_count = DropTable.objects.count()
        self.assertFalse(DropTable.objects.filter(item_id__in=items.values()).exists())
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(dict(QuestDefinition.objects.filter(name__in=names).values_list("name", "pk")), definitions)
        self.assertEqual(dict(ItemDefinition.objects.filter(slug__startswith="collector-reading-2026-").values_list("slug", "pk")), items)
        self.assertEqual(dict(Badge.objects.filter(name__startswith="Collector's Reading:").values_list("name", "pk")), badges)
        self.assertEqual(DropTable.objects.count(), original_drop_count)
        self.assertFalse(DropTable.objects.filter(item_id__in=items.values()).exists())
        first = QuestDefinition.objects.get(name="Collector's Reading: Fresh Pages")
        self.assertEqual(first.required_badge_id, Badge.objects.get(name="Full Ark").pk)

    def test_drop_macro_exclusion_preserves_other_pack_cosmetics(self):
        call_command("loadrpgcontent", stdout=StringIO())
        ordinary = ItemDefinition.objects.create(
            slug="other-pack-ordinary-frame", name="Other pack frame", item_type="cosmetic_frame",
        )
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertTrue(DropTable.objects.filter(item=ordinary).exists())
        self.assertFalse(DropTable.objects.filter(item__slug__startswith="collector-reading-2026-").exists())

    def test_real_default_dry_run_preserves_legacy_promises_and_household_state(self):
        # Start with the seed only: the dry run must not leave additive rows.
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())
        child = make_family("Dry-run reader", children=[{"username": "dry-reader", "theme": "winter"}]).children[0]
        definition = QuestDefinition.objects.get(name="Ghost Trail")
        quest = Quest.objects.create(definition=definition, end_date=timezone.now() + timedelta(days=7))
        original_links = list(QuestRewardItem.objects.filter(quest_definition=definition).values("id", "item_id", "quantity"))
        self.assertTrue(original_links)
        original_item_ids = list(ItemDefinition.objects.values_list("pk", flat=True))
        original_quest_ids = list(QuestDefinition.objects.values_list("pk", flat=True))
        original_badge_ids = list(Badge.objects.values_list("pk", flat=True))
        original_profile = CharacterProfile.objects.get(user=child)
        original_theme = original_profile.active_theme_id
        original_inventory = list(UserInventory.objects.filter(user=child).values("pk", "item_id", "quantity"))

        call_command("loadrpgcontent", dry_run=True, stdout=StringIO())

        quest.refresh_from_db()
        child.refresh_from_db()
        original_profile.refresh_from_db()
        self.assertIsNone(quest.reward_items_snapshot)
        self.assertEqual(list(QuestRewardItem.objects.filter(quest_definition=definition).values("id", "item_id", "quantity")), original_links)
        self.assertEqual(list(ItemDefinition.objects.values_list("pk", flat=True)), original_item_ids)
        self.assertEqual(list(QuestDefinition.objects.values_list("pk", flat=True)), original_quest_ids)
        self.assertEqual(list(Badge.objects.values_list("pk", flat=True)), original_badge_ids)
        self.assertEqual(list(UserInventory.objects.filter(user=child).values("pk", "item_id", "quantity")), original_inventory)
        self.assertEqual((child.theme, original_profile.active_theme_id), ("winter", original_theme))
        self.assertFalse(QuestDefinition.objects.filter(name="Reading Companion").exists())

    def test_actual_default_reload_freezes_existing_legacy_item_promises_before_new_content(self):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())
        definition = QuestDefinition.objects.get(name="Ghost Trail")
        quest = Quest.objects.create(definition=definition, end_date=timezone.now() + timedelta(days=7))
        promised = list(definition.reward_items.values_list("item_id", "quantity"))
        self.assertTrue(promised)
        old_updated_at = quest.updated_at

        call_command("loadrpgcontent", stdout=StringIO())

        quest.refresh_from_db()
        self.assertEqual([(row["item_id"], row["quantity"]) for row in quest.reward_items_snapshot], promised)
        self.assertEqual(quest.updated_at, old_updated_at)
        self.assertEqual((quest.status, quest.current_progress), ("active", 0))

    def test_finite_targets_require_a_reachable_full_collection_before_reading_coda(self):
        call_command("loadrpgcontent", stdout=StringIO())
        catalog = snapshot_catalog()
        config = {"reading_minutes": 10, "project_minutes": 0, "chores_per_day": 0,
                  "habits_per_day": 0, "journal_per_day": False, "creations_per_day": 0,
                  "movement_sessions_per_day": 0, "expeditions_per_day": 0}
        grounded = Trial(config, catalog, 42)
        traveling = Trial({**config, "expeditions_per_day": 1, "journal_per_day": True}, catalog, 42)
        initial = QuestDefinition.objects.get(name="Reading Companion")
        self.assertIn(f"quest:{initial.pk}", grounded.finite_keys)
        chapters = QuestDefinition.objects.filter(name__startswith="Collector's Reading:")
        for chapter in chapters:
            with self.subTest(chapter=chapter.name):
                self.assertNotIn(f"quest:{chapter.pk}", grounded.finite_keys)
                self.assertIn(f"quest:{chapter.pk}", traveling.finite_keys)
                for reward in chapter.reward_items.all():
                    self.assertNotIn(f"cosmetic:{reward.item_id}", grounded.finite_keys)
                    self.assertIn(f"cosmetic:{reward.item_id}", traveling.finite_keys)

    def test_chapter_cosmetics_cannot_be_randomly_granted_or_consume_a_lucky_dip(self):
        call_command("loadrpgcontent", stdout=StringIO())
        child = make_family("No chapter shortcuts", children=[{"username": "no-shortcut-reader"}]).children[0]
        ItemDefinition.objects.filter(item_type__startswith="cosmetic_").exclude(
            slug__startswith="collector-reading-2026-",
        ).delete()
        dip = ItemDefinition.objects.create(
            slug="fixture-chapter-lucky-dip", name="Lucky dip", item_type="consumable", metadata={"effect": "lucky_dip"},
        )
        inventory = UserInventory.objects.create(user=child, item=dip)
        with self.assertRaisesRegex(ValueError, "no eligible cosmetics"):
            ConsumableService.use(child, dip.pk)
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=child, item__slug__startswith="collector-reading-2026-").exists())
        DropTable.objects.all().delete()
        item = ItemDefinition.objects.get(slug="collector-reading-2026-title-pagefinder")
        for trigger in ("clock_out", "expedition_returned"):
            DropTable.objects.create(trigger_type=trigger, item=item)
        with patch("apps.rpg.services.random.random", return_value=0):
            self.assertEqual(DropService.process_drops(child, "clock_out"), [])
        self.assertEqual(ExpeditionService._roll_loot(child, "long")["items"], [])
