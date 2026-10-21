"""Startup retirement respects published identities and runs only once."""
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.db.models import ProtectedError, Sum
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.workbench import (
    create_draft, preview_draft, publish_draft, save_draft, simulate_draft,
)
from apps.rpg.models import ItemDefinition, RPGContentOverride, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RetirementStartupTests(TestCase):
    def accessory(self):
        return ItemDefinition.objects.create(
            slug="accessory-party-hat", name="Party Hat", icon="H",
            item_type="cosmetic_pet_accessory",
        )

    def load_default(self, **options):
        output = StringIO()
        call_command("loadrpgcontent", stdout=output, stderr=output, **options)
        return output.getvalue()

    def held_redemption(self, user, item):
        offer = Reward.objects.create(
            family=user.family, name="Synthetic startup retirement reward", cost_coins=7,
            fulfillment_kind="digital_item", item_definition=item,
        )
        receipt = RewardRedemption.objects.create(user=user, reward=offer, coin_cost_snapshot=7)
        CoinLedger.objects.create(user=user, amount=-7, reason="redemption", redemption=receipt)
        return receipt

    def test_published_retired_item_rename_is_reported_and_does_not_stop_startup(self):
        # A generic load prepares the existing catalog without consuming the
        # default command's one-time upgrade. Publish through the real staff
        # workflow rather than inventing an override that the editor cannot save.
        ContentPack("content/rpg/initial").load(stdout=StringIO())
        actor = make_family("Retirement editor", parents=[{
            "username": "retirement-editor", "is_staff": True,
        }]).parents[0]
        item = self.accessory()
        draft = create_draft(actor, "Keep an edited catalog identity")
        draft = save_draft(actor, draft["id"], draft["revision"], [{
            "section": "items", "object_id": item.pk, "key": "party-hat",
            "values": {"name": "A Parent's Celebration Hat"},
        }])
        draft = preview_draft(actor, draft["id"], draft["revision"])
        plan = draft["preview"]
        simulate_draft(actor, draft["id"], draft["revision"], plan["preview_id"], {
            "horizon_days": 30, "trials": 1,
        })
        publish_draft(actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])
        item.refresh_from_db()
        self.assertEqual(item.name, "A Parent's Celebration Hat")
        override = RPGContentOverride.objects.get(model_label="rpg.itemdefinition", object_id=item.pk)
        before_item = ItemDefinition.objects.values().get(pk=item.pk)
        before_override = RPGContentOverride.objects.values().get(pk=override.pk)

        output = self.load_default()

        self.assertIn("retirement", output.lower())
        self.assertIn("skip", output.lower())
        self.assertEqual(ItemDefinition.objects.values().get(pk=item.pk), before_item)
        self.assertEqual(RPGContentOverride.objects.values().get(pk=override.pk), before_override)
        self.assertEqual(PetSpecies.objects.count(), 15)
        self.assertTrue(ItemDefinition.objects.filter(slug="collector-reading-2026-title-pagefinder").exists())

    def test_later_explicit_authoring_is_not_deleted_by_another_startup(self):
        original = self.accessory()
        self.load_default()
        self.assertFalse(ItemDefinition.objects.filter(pk=original.pk).exists())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "items.yaml").write_text(
                "items:\n  - slug: accessory-party-hat\n    name: Party Hat\n"
                "    icon: H\n    item_type: cosmetic_pet_accessory\n"
                "    description: Explicitly authored after retirement.\n",
                encoding="utf-8",
            )
            ContentPack(path).load(stdout=StringIO())
        authored = ItemDefinition.objects.get(slug="accessory-party-hat")
        before = ItemDefinition.objects.values().get(pk=authored.pk)

        self.load_default()

        self.assertTrue(ItemDefinition.objects.filter(pk=authored.pk).exists())
        self.assertEqual(ItemDefinition.objects.values().get(pk=authored.pk), before)

    def test_default_dry_run_does_not_consume_the_cleanup(self):
        item = self.accessory()
        before = ItemDefinition.objects.values().get(pk=item.pk)

        self.load_default(dry_run=True)

        self.assertEqual(ItemDefinition.objects.values().get(pk=item.pk), before)
        self.assertFalse(PetSpecies.objects.exists())
        self.load_default()
        self.assertFalse(ItemDefinition.objects.filter(pk=item.pk).exists())
        self.assertEqual(PetSpecies.objects.count(), 15)

    def test_first_startup_retires_only_the_exact_known_optional_pack_namespace(self):
        # Reproduce the loader's actual slug expansion for the old optional
        # Party Horn. A matching suffix/name in another namespace establishes
        # no authority to retire an independently authored record.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "items.yaml").write_text(
                "items:\n  - slug: accessory-party-horn\n    name: Party Horn\n"
                "    icon: H\n    item_type: cosmetic_pet_accessory\n",
                encoding="utf-8",
            )
            for namespace in ("birthday-pack-", "owner-birthday-", "birthday-2026-"):
                ContentPack(path, namespace=namespace).load(stdout=StringIO())
        exact = ItemDefinition.objects.get(slug="birthday-pack-accessory-party-horn")
        other_namespaces = [
            ItemDefinition.objects.values().get(slug=slug)
            for slug in ("owner-birthday-accessory-party-horn", "birthday-2026-accessory-party-horn")
        ]

        self.load_default()

        self.assertFalse(ItemDefinition.objects.filter(pk=exact.pk).exists())
        for before in other_namespaces:
            self.assertEqual(ItemDefinition.objects.values().get(pk=before["id"]), before)

    def test_malformed_saved_loot_skips_startup_cleanup_and_can_be_corrected_for_retry(self):
        user = make_family("Malformed retirement receipt", children=[{
            "username": "startup-malformed-child",
        }]).children[0]
        base = PotionType.objects.create(slug="base", name="Base")
        wolf = PetSpecies.objects.create(slug="wolf", name="Wolf", sprite_key="wolf")
        egg = ItemDefinition.objects.create(
            slug="wolf-egg", name="Wolf Egg", item_type="egg", pet_species=wolf,
            metadata={"species": "wolf"},
        )
        food = ItemDefinition.objects.create(slug="food-birdseed", name="Birdseed", item_type="food")
        receipt = self.held_redemption(user, egg)
        mount = UserMount.objects.create(user=user, species=wolf, potion=base)
        expedition = MountExpedition.objects.create(
            mount=mount, tier="short", returns_at=timezone.now(),
            loot={"coins": "17", "items": [{"item_id": food.pk, "quantity": 3}]},
        )
        before_receipt = RewardRedemption.objects.values().get(pk=receipt.pk)
        before_expedition = MountExpedition.objects.values().get(pk=expedition.pk)
        before_ledger = list(CoinLedger.objects.filter(user=user).order_by("pk").values())

        output = self.load_default()

        self.assertIn("retirement skipped", output.lower())
        self.assertIn("malformed saved loot", output.lower())
        self.assertEqual(RewardRedemption.objects.values().get(pk=receipt.pk), before_receipt)
        self.assertEqual(MountExpedition.objects.values().get(pk=expedition.pk), before_expedition)
        self.assertEqual(list(CoinLedger.objects.filter(user=user).order_by("pk").values()), before_ledger)
        self.assertTrue(UserMount.objects.filter(pk=mount.pk).exists())
        self.assertTrue(PetSpecies.objects.filter(pk=wolf.pk).exists())
        self.assertFalse(UserInventory.objects.filter(user=user, item=food).exists())
        self.assertEqual(PetSpecies.objects.count(), 16)
        self.assertTrue(ItemDefinition.objects.filter(slug="collector-reading-2026-title-pagefinder").exists())

        # The earlier refund in the same attempt must have rolled back. Once
        # the actual saved receipt is repaired, startup can settle it once.
        MountExpedition.objects.filter(pk=expedition.pk).update(
            loot={"coins": 17, "items": [{"item_id": food.pk, "quantity": 3}]},
        )
        self.load_default()

        self.assertFalse(RewardRedemption.objects.filter(pk=receipt.pk).exists())
        self.assertFalse(MountExpedition.objects.filter(pk=expedition.pk).exists())
        self.assertFalse(PetSpecies.objects.filter(pk=wolf.pk).exists())
        self.assertEqual(CoinLedger.objects.get(user=user, reason="refund").amount, 7)
        self.assertEqual(CoinLedger.objects.filter(user=user).aggregate(total=Sum("amount"))["total"], 17)
        self.assertEqual(UserInventory.objects.get(user=user, item=food).quantity, 3)
        settled_ledger = list(CoinLedger.objects.filter(user=user).order_by("pk").values())
        self.load_default()
        self.assertEqual(list(CoinLedger.objects.filter(user=user).order_by("pk").values()), settled_ledger)
        self.assertEqual(UserInventory.objects.get(user=user, item=food).quantity, 3)

    def test_protected_cleanup_rolls_back_refund_and_continues_until_next_startup(self):
        user = make_family("Protected retirement receipt", children=[{
            "username": "startup-protected-child",
        }]).children[0]
        item = self.accessory()
        receipt = self.held_redemption(user, item)
        before_receipt = RewardRedemption.objects.values().get(pk=receipt.pk)
        before_ledger = list(CoinLedger.objects.filter(user=user).order_by("pk").values())
        original_delete = QuerySet.delete
        protected_calls = []

        def protect_retired_item(queryset):
            if queryset.model is ItemDefinition and queryset.filter(pk=item.pk).exists():
                protected_calls.append(item.pk)
                raise ProtectedError("Synthetic protected retirement dependency", {item})
            return original_delete(queryset)

        # Fail late, after the real retirement refund/cancellation work, while
        # ordinary bundled loading and unrelated queryset deletes still run.
        with patch.object(QuerySet, "delete", autospec=True, side_effect=protect_retired_item):
            output = self.load_default()

        self.assertEqual(protected_calls, [item.pk])
        self.assertIn("retirement skipped", output.lower())
        self.assertIn("Synthetic protected retirement dependency", output)
        self.assertTrue(ItemDefinition.objects.filter(pk=item.pk).exists())
        self.assertEqual(RewardRedemption.objects.values().get(pk=receipt.pk), before_receipt)
        self.assertEqual(list(CoinLedger.objects.filter(user=user).order_by("pk").values()), before_ledger)
        self.assertEqual(PetSpecies.objects.count(), 15)
        self.assertTrue(ItemDefinition.objects.filter(slug="collector-reading-2026-title-pagefinder").exists())

        self.load_default()

        self.assertFalse(ItemDefinition.objects.filter(pk=item.pk).exists())
        self.assertFalse(RewardRedemption.objects.filter(pk=receipt.pk).exists())
        self.assertEqual(CoinLedger.objects.get(user=user, reason="refund").amount, 7)
        self.assertEqual(CoinLedger.objects.filter(user=user).aggregate(total=Sum("amount"))["total"], 0)

    def test_later_pack_failure_rolls_back_cleanup_so_next_startup_can_apply_it(self):
        item = self.accessory()
        before = ItemDefinition.objects.values().get(pk=item.pk)
        original_load = ContentPack.load

        def fail_second_bundle(pack, *args, **kwargs):
            if pack.path.name == "reading-adventures":
                raise ContentPackError("Synthetic later bundled pack failure")
            return original_load(pack, *args, **kwargs)

        with patch.object(ContentPack, "load", autospec=True, side_effect=fail_second_bundle):
            with self.assertRaisesMessage(CommandError, "Synthetic later bundled pack failure"):
                self.load_default()

        self.assertEqual(ItemDefinition.objects.values().get(pk=item.pk), before)
        self.assertFalse(PetSpecies.objects.exists())
        self.load_default()
        self.assertFalse(ItemDefinition.objects.filter(pk=item.pk).exists())
        self.assertEqual(PetSpecies.objects.count(), 15)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExplicitRetirementMarkerTests(TestCase):
    def accessory(self):
        return ItemDefinition.objects.create(
            slug="accessory-party-hat", name="Party Hat", icon="H",
            item_type="cosmetic_pet_accessory",
        )

    def marker_applied(self):
        from apps.rpg.models import RPGContentRetirement
        return RPGContentRetirement.objects.filter(applied_at__isnull=False).exists()

    def test_explicit_retry_completes_the_transition_for_later_startups(self):
        original = self.accessory()
        call_command("retire_unused_rpg_content", stdout=StringIO())
        self.assertFalse(ItemDefinition.objects.filter(pk=original.pk).exists())
        self.assertTrue(self.marker_applied())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "items.yaml").write_text(
                "items:\n  - slug: accessory-party-hat\n    name: Party Hat\n"
                "    icon: H\n    item_type: cosmetic_pet_accessory\n"
                "    description: Explicitly authored after an operator retry.\n",
                encoding="utf-8",
            )
            ContentPack(path).load(stdout=StringIO())
        authored = ItemDefinition.objects.get(slug="accessory-party-hat")
        before = ItemDefinition.objects.values().get(pk=authored.pk)

        call_command("loadrpgcontent", stdout=StringIO(), stderr=StringIO())

        self.assertEqual(ItemDefinition.objects.values().get(pk=authored.pk), before)

    def test_explicit_dry_run_does_not_complete_the_transition(self):
        item = self.accessory()
        call_command("retire_unused_rpg_content", "--dry-run", stdout=StringIO())
        self.assertTrue(ItemDefinition.objects.filter(pk=item.pk).exists())
        self.assertFalse(self.marker_applied())

    def test_explicit_retry_locks_the_marker_before_retirement_locks(self):
        # Startup takes the marker before user/catalog locks; the explicit
        # retry must use the same order so overlapping runs cannot deadlock.
        from apps.rpg import retired_catalog
        from apps.rpg.models import RPGContentRetirement
        real = retired_catalog.retire_unused_catalog
        seen = []

        def observe(*args, **kwargs):
            seen.append(RPGContentRetirement.objects.filter(key=retired_catalog.RETIREMENT_KEY).exists())
            return real(*args, **kwargs)

        with patch.object(retired_catalog, "retire_unused_catalog", side_effect=observe):
            call_command("retire_unused_rpg_content", stdout=StringIO())
        self.assertEqual(seen, [True])
        self.assertTrue(self.marker_applied())
