"""Future reward attribution preserves actual payouts and atomic promises."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.achievements.services import AwardService
from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import InventoryItemService
from config.tests.factories import make_family


class CoinAttributionTests(TestCase):
    def setUp(self):
        self.family = make_family(children=[{"username": "source-child"}])
        self.child = self.family.children[0]

    def test_unattributed_awards_remain_unknown_and_keep_existing_amount(self):
        entry = CoinService.award_coins(self.child, 17, CoinLedger.Reason.ADJUSTMENT)
        self.assertEqual(entry.source, "")
        self.assertEqual(entry.amount, 17)

    def test_only_known_positive_sources_with_matching_reasons_are_accepted(self):
        invalid = [
            ("invented", 5, CoinLedger.Reason.ADJUSTMENT),
            ("coin_pouch", -5, CoinLedger.Reason.ADJUSTMENT),
            ("coin_pouch", 5, CoinLedger.Reason.HOURLY),
            ("expedition", 5, CoinLedger.Reason.ADJUSTMENT),
            ("expedition_salvage", 5, CoinLedger.Reason.EXPEDITION),
        ]
        for source, amount, reason in invalid:
            with self.subTest(source=source, amount=amount, reason=reason):
                with self.assertRaises(ValueError):
                    CoinService.award_coins(self.child, amount, reason, source=source)
        self.assertFalse(CoinLedger.objects.exists())

    def test_new_adjustment_sources_preserve_exact_credit_under_lucky_coin(self):
        profile = CharacterProfile.objects.get(user=self.child)
        profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        profile.save(update_fields=["coin_boost_expires_at"])
        sources = (
            "daily_check_in", "automatic_challenge", "perfect_day", "writing", "savings",
            "birthday", "legacy_quest", "cosmetic_salvage", "consumable_salvage", "manual_grant",
        )
        for source in sources:
            with self.subTest(source=source):
                entry = CoinService.award_coins(self.child, 7, CoinLedger.Reason.ADJUSTMENT, source=source)
                self.assertEqual((entry.amount, entry.reason, entry.source), (7, "adjustment", source))
                for amount, reason in ((0, "adjustment"), (-7, "adjustment"), (7, "reading")):
                    with self.assertRaises(ValueError):
                        CoinService.award_coins(self.child, amount, reason, source=source)
        self.assertEqual(CoinService.get_balance(self.child), 70)

    def test_optional_award_source_preserves_positive_and_zero_award_behavior(self):
        AwardService.grant(
            self.child, coins=9, coin_reason="adjustment", coin_source="automatic_challenge",
            badge_scopes=set(),
        )
        entry = CoinLedger.objects.get(user=self.child)
        self.assertEqual((entry.amount, entry.reason, entry.source), (9, "adjustment", "automatic_challenge"))
        AwardService.grant(
            self.child, coins=0, coin_reason="adjustment", coin_source="automatic_challenge",
            badge_scopes=set(),
        )
        self.assertEqual(CoinLedger.objects.count(), 1)
        self.assertEqual(CoinService.get_balance(self.child), 9)

    def test_untyped_zero_and_negative_adjustments_keep_existing_behavior(self):
        CoinService.award_coins(self.child, 17, CoinLedger.Reason.ADJUSTMENT)
        self.assertIsNone(CoinService.award_coins(self.child, 0, CoinLedger.Reason.ADJUSTMENT))
        entry = CoinService.award_coins(self.child, -3, CoinLedger.Reason.ADJUSTMENT)
        self.assertEqual((entry.amount, entry.reason, entry.source), (-3, "adjustment", ""))
        self.assertEqual(CoinService.get_balance(self.child), 14)

    def test_pouch_attribution_does_not_cap_or_boost_existing_promise(self):
        profile = CharacterProfile.objects.get(user=self.child)
        profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        profile.save(update_fields=["coin_boost_expires_at"])
        pouch = ItemDefinition.objects.create(
            slug="promised-pouch", name="Promised pouch", item_type="coin_pouch",
            metadata={"coins": 500}, coin_value=50,
        )
        UserInventory.objects.create(user=self.child, item=pouch, quantity=1)
        result = InventoryItemService.open_coin_pouch(self.child, pouch.pk)
        entry = CoinLedger.objects.get(user=self.child)
        self.assertEqual((entry.source, entry.reason, entry.amount), ("coin_pouch", "adjustment", 500))
        self.assertEqual(result["coins_awarded"], 500)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=pouch).exists())

    def test_pouch_and_attributed_credit_roll_back_together(self):
        pouch = ItemDefinition.objects.create(
            slug="rollback-pouch", name="Rollback pouch", item_type="coin_pouch", metadata={"coins": 50},
        )
        UserInventory.objects.create(user=self.child, item=pouch, quantity=1)
        with patch.object(CoinService, "_record_activity", side_effect=RuntimeError("late failure")):
            with self.assertRaises(RuntimeError):
                InventoryItemService.open_coin_pouch(self.child, pouch.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=pouch).quantity, 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_expedition_and_salvage_sources_keep_boost_and_retry_behavior(self):
        profile = CharacterProfile.objects.get(user=self.child)
        profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        profile.save(update_fields=["coin_boost_expires_at"])
        species = PetSpecies.objects.create(slug="saved-source-species", name="Saved species")
        potion = PotionType.objects.create(slug="source-base", name="Base")
        mount = UserMount.objects.create(user=self.child, species=species, potion=potion)
        cosmetic = ItemDefinition.objects.create(
            slug="saved-source-frame", name="Saved frame", item_type="cosmetic_frame", coin_value=250,
        )
        UserInventory.objects.create(user=self.child, item=cosmetic, quantity=1)
        trip = MountExpedition.objects.create(
            mount=mount, tier="long", started_at=timezone.now() - timedelta(hours=9),
            returns_at=timezone.now() - timedelta(hours=1),
            loot={"coins": 75, "items": [{"item_id": cosmetic.pk, "quantity": 1}]},
        )
        first = ExpeditionService.claim(self.child, trip.pk)
        second = ExpeditionService.claim(self.child, trip.pk)
        amounts = dict(CoinLedger.objects.filter(user=self.child).values_list("source", "amount"))
        self.assertEqual(amounts, {"expedition": 150, "expedition_salvage": 250})
        self.assertEqual(first["coins_awarded"], 150)
        self.assertFalse(second["freshly_claimed"])
        self.assertEqual(CoinService.get_balance(self.child), 400)
