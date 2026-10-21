"""Unused-content removal settles saved resources without inventing rewards."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.db.models import Sum
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.pets.models import MountExpedition, PetIncubation, PetSpecies, PotionType, UserMount
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.retired_catalog import retire_unused_catalog
from apps.rpg.retirement_resources import (
    RETURN_MARKER, RetirementResourceError, collect_retirement_resource_user_ids, settle_retirement_resources,
)
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class _RetirementResourceCase(TestCase):
    def setUp(self):
        self.user = make_family(children=[{"username": "resource-child"}]).children[0]
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.wolf = PetSpecies.objects.create(slug="wolf", name="Wolf", sprite_key="wolf")
        self.egg = ItemDefinition.objects.create(
            slug="wolf-egg", name="Wolf Egg", item_type="egg", pet_species=self.wolf,
        )
        self.potion = ItemDefinition.objects.create(
            slug="base-potion", name="Base Potion", item_type="potion", potion_type=self.base,
        )
        self.food = ItemDefinition.objects.create(slug="food-birdseed", name="Birdseed", item_type="food")

    def balance(self):
        return CoinLedger.objects.filter(user=self.user).aggregate(total=Sum("amount"))["total"] or 0

    def redemption(self, *, status="pending", debit=10):
        offer = Reward.objects.create(
            family=self.user.family, name=f"Old offer {Reward.objects.count()}", cost_coins=10,
            fulfillment_kind="digital_item", item_definition=self.egg,
        )
        receipt = RewardRedemption.objects.create(
            user=self.user, reward=offer, coin_cost_snapshot=10, status=status,
        )
        if debit:
            CoinLedger.objects.create(user=self.user, amount=-debit, reason="redemption", redemption=receipt)
        return receipt

    def incubation(self, *, completed=False, potion=None):
        potion = potion or self.potion
        now = timezone.now()
        return PetIncubation.objects.create(
            user=self.user, request_id=uuid4(), species=self.wolf, potion_type=potion.potion_type,
            egg_item=self.egg, potion_item=potion,
            accepted_pair={"egg": {"id": self.egg.pk}, "potion": {"id": potion.pk}},
            started_at=now, ready_at=now + timedelta(hours=24),
            hatched_at=now if completed else None,
        )

    def expedition(self, *, status="active", ready=False):
        mount = UserMount.objects.create(user=self.user, species=self.wolf, potion=self.base)
        return MountExpedition.objects.create(
            mount=mount, tier="short", status=status,
            returns_at=timezone.now() + timedelta(hours=-1 if ready else 1),
            loot={"coins": 17, "items": [
                {"item_id": self.food.pk, "quantity": 3}, {"item_id": self.egg.pk, "quantity": 1},
            ]},
        )


class RetirementResourceLossTests(_RetirementResourceCase):
    def test_retirement_refunds_the_actual_held_redemption_debit(self):
        self.redemption(debit=7)

        retire_unused_catalog()

        self.assertEqual(self.balance(), 0)
        self.assertEqual(CoinLedger.objects.get(reason="refund").amount, 7)

    def test_retirement_returns_the_unfinished_incubations_consumed_base_potion(self):
        self.incubation()

        retire_unused_catalog()

        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.potion).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.user, item_id=self.egg.pk).exists())

    def test_retirement_returns_a_supported_egg_from_an_unfinished_retired_potion_pair(self):
        chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        egg = ItemDefinition.objects.create(slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=chick, metadata={"species": "chick"})
        shadow = PotionType.objects.create(slug="shadow", name="Shadow")
        potion = ItemDefinition.objects.create(slug="shadow-potion", name="Shadow Potion", item_type="potion", potion_type=shadow)
        now = timezone.now()
        PetIncubation.objects.create(
            user=self.user, request_id=uuid4(), species=chick, potion_type=shadow, egg_item=egg, potion_item=potion,
            accepted_pair={"egg": {"id": egg.pk}, "potion": {"id": potion.pk}}, started_at=now, ready_at=now,
        )

        retire_unused_catalog()

        self.assertEqual(UserInventory.objects.get(user=self.user, item=egg).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.user, item_id=potion.pk).exists())

    def test_dry_run_rolls_back_settlements_and_repeated_apply_cannot_credit_twice(self):
        receipt = self.redemption(debit=7)
        incubation = self.incubation()
        expedition = self.expedition()

        retire_unused_catalog(dry_run=True)

        self.assertEqual(self.balance(), -7)
        self.assertFalse(UserInventory.objects.filter(user=self.user).exists())
        receipt.refresh_from_db()
        incubation.refresh_from_db()
        expedition.refresh_from_db()
        self.assertEqual(receipt.status, "pending")
        self.assertNotIn(RETURN_MARKER, incubation.accepted_pair)
        self.assertEqual(expedition.status, "active")
        retire_unused_catalog()
        retire_unused_catalog()
        self.assertEqual(self.balance(), 17)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.potion).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.food).quantity, 3)


class RetirementResourceSettlementTests(_RetirementResourceCase):
    def settle(self, *, redemptions=(), incubations=(), mounts=()):
        return settle_retirement_resources(
            redemption_ids=[row.pk for row in redemptions], incubation_ids=[row.pk for row in incubations],
            mount_ids=[row.pk for row in mounts], retired_item_ids=[self.egg.pk],
        )

    def test_pending_and_approved_refunds_use_net_actual_debits_and_run_once(self):
        rows = [self.redemption(status=status, debit=7) for status in ("pending", "approved")]
        for row in rows:
            RewardRedemption.objects.filter(pk=row.pk).update(coin_cost_snapshot=999)
            CoinLedger.objects.create(user=self.user, amount=2, reason="refund", redemption=row)

        result = self.settle(redemptions=rows)
        repeat = self.settle(redemptions=rows)

        self.assertEqual(self.balance(), 0)
        self.assertEqual([row["coins"] for row in result["refunds"]], [5, 5])
        self.assertEqual(repeat["refunds"], [])
        self.assertEqual(repeat["redemption_cancellations"], [])
        self.assertEqual(set(RewardRedemption.objects.values_list("status", flat=True)), {"canceled"})

    def test_synthetic_completed_or_already_refunded_requests_cannot_invent_coins(self):
        synthetic = self.redemption(debit=0)
        fulfilled = self.redemption(status="fulfilled", debit=5)
        denied = self.redemption(status="denied", debit=6)
        CoinLedger.objects.create(user=self.user, amount=6, reason="refund", redemption=denied)
        refunded = self.redemption(debit=7)
        CoinLedger.objects.create(user=self.user, amount=7, reason="refund", redemption=refunded)
        delivered = self.redemption(status="approved", debit=8)
        RewardRedemption.objects.filter(pk=delivered.pk).update(delivered_at=timezone.now())
        before = list(CoinLedger.objects.order_by("pk").values_list("pk", "amount"))

        result = self.settle(redemptions=[synthetic, fulfilled, denied, refunded, delivered])

        self.assertEqual(result["refunds"], [])
        self.assertEqual(list(CoinLedger.objects.order_by("pk").values_list("pk", "amount")), before)
        fulfilled.refresh_from_db()
        delivered.refresh_from_db()
        self.assertEqual(fulfilled.status, "fulfilled")
        self.assertEqual(delivered.status, "approved")

    def test_actual_reserved_stock_is_restored_once(self):
        receipt = self.redemption()
        RewardRedemption.objects.filter(pk=receipt.pk).update(stock_reserved=True)
        Reward.objects.filter(pk=receipt.reward_id).update(stock=0)

        self.settle(redemptions=[receipt])
        self.settle(redemptions=[receipt])

        self.assertEqual(Reward.objects.get(pk=receipt.reward_id).stock, 1)
        self.assertFalse(RewardRedemption.objects.get(pk=receipt.pk).stock_reserved)

    def test_unfinished_potion_returns_once_and_completed_hatches_do_not_return(self):
        unfinished = self.incubation()
        completed = self.incubation(completed=True)
        UserInventory.objects.create(user=self.user, item=self.potion, quantity=4)

        result = self.settle(incubations=[unfinished, completed])
        repeat = self.settle(incubations=[unfinished, completed])

        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.potion).quantity, 5)
        self.assertEqual(len(result["potion_returns"]), 1)
        self.assertEqual(repeat["potion_returns"], [])
        self.assertFalse(UserInventory.objects.filter(user=self.user, item=self.egg).exists())

    def test_retired_potions_are_not_returned(self):
        shadow = PotionType.objects.create(slug="shadow", name="Shadow")
        old_potion = ItemDefinition.objects.create(slug="shadow-potion", name="Shadow Potion", item_type="potion", potion_type=shadow)
        row = self.incubation(potion=old_potion)

        result = settle_retirement_resources(incubation_ids=[row.pk], retired_item_ids=[self.egg.pk, old_potion.pk])

        self.assertEqual(result["potion_returns"], [])
        self.assertFalse(UserInventory.objects.filter(user=self.user).exists())

    def test_mismatched_ingredient_snapshot_or_receiving_type_holds_without_a_grant(self):
        incubation = self.incubation()
        for snapshot in ({"id": self.food.pk}, {"id": self.potion.pk, "item_type": "egg"},
                         {"id": self.potion.pk, "slug": "different-potion"}):
            with self.subTest(snapshot=snapshot):
                PetIncubation.objects.filter(pk=incubation.pk).update(accepted_pair={"potion": snapshot})
                with self.assertRaises(RetirementResourceError):
                    self.settle(incubations=[incubation])
                self.assertFalse(UserInventory.objects.filter(user=self.user).exists())
        PetIncubation.objects.filter(pk=incubation.pk).update(accepted_pair={"potion": {"id": self.potion.pk}})
        ItemDefinition.objects.filter(pk=self.potion.pk).update(item_type="food")
        with self.assertRaisesRegex(RetirementResourceError, "changed consumed-potion identity"):
            self.settle(incubations=[incubation])
        self.assertFalse(UserInventory.objects.filter(user=self.user).exists())

    def test_active_expedition_settles_saved_loot_once_without_buffs_or_effort_hooks(self):
        from apps.achievements.models import SkillProgress, UserBadge
        from apps.activity.models import ActivityEvent
        from apps.chronicle.models import ChronicleEntry
        from apps.rpg.models import CharacterProfile

        expedition = self.expedition(ready=False)
        UserInventory.objects.create(user=self.user, item=self.food, quantity=2)
        CharacterProfile.objects.filter(user=self.user).update(coin_boost_expires_at=timezone.now() + timedelta(days=1))
        profile_before = CharacterProfile.objects.values().get(user=self.user)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as loop, patch("apps.rewards.services.CoinService.award_coins") as award:
            result = self.settle(mounts=[expedition.mount])
            repeat = self.settle(mounts=[expedition.mount])

        self.assertEqual(self.balance(), 17)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.food).quantity, 5)
        self.assertEqual(result["expeditions"][0]["coins"], 17)
        self.assertEqual(repeat["expeditions"], [])
        self.assertFalse(UserInventory.objects.filter(user=self.user, item=self.egg).exists())
        expedition.refresh_from_db()
        self.assertEqual(expedition.status, "claimed")
        self.assertIsNotNone(expedition.claimed_at)
        self.assertEqual(CharacterProfile.objects.values().get(user=self.user), profile_before)
        for model in [SkillProgress, UserBadge, ActivityEvent, ChronicleEntry]:
            self.assertEqual(model.objects.count(), 0)
        loop.assert_not_called()
        award.assert_not_called()

    def test_claimed_expired_or_already_marked_expeditions_never_award_again(self):
        claimed = self.expedition(status="claimed")
        MountExpedition.objects.create(mount=claimed.mount, tier="short", status="expired", returns_at=timezone.now(), loot=claimed.loot)
        MountExpedition.objects.create(mount=claimed.mount, tier="short", status="active", claimed_at=timezone.now(), returns_at=timezone.now(), loot=claimed.loot)

        result = self.settle(mounts=[claimed.mount])

        self.assertEqual(result["expeditions"], [])
        self.assertEqual(self.balance(), 0)
        self.assertFalse(UserInventory.objects.filter(user=self.user).exists())

    def test_duplicate_cosmetic_uses_existing_deterministic_salvage_rule(self):
        expedition = self.expedition()
        frame = ItemDefinition.objects.create(slug="frame-current", name="Current frame", item_type="cosmetic_frame", coin_value=11)
        UserInventory.objects.create(user=self.user, item=frame, quantity=1)
        expedition.loot["items"].append({"item_id": frame.pk, "quantity": 1})
        expedition.save(update_fields=["loot"])

        result = self.settle(mounts=[expedition.mount])

        self.assertEqual(self.balance(), 28)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=frame).quantity, 1)
        self.assertEqual(result["expeditions"][0]["salvage_coins"], 11)
        self.assertEqual(CoinLedger.objects.get(source="expedition_salvage").amount, 11)

    def test_invalid_saved_resources_roll_back_refunds_and_markers_before_deletion(self):
        receipt = self.redemption(debit=7)
        incubation = self.incubation()
        expedition = self.expedition()
        MountExpedition.objects.filter(pk=expedition.pk).update(loot={"coins": "17", "items": []})

        with self.assertRaisesRegex(RetirementResourceError, "malformed saved loot"):
            self.settle(redemptions=[receipt], incubations=[incubation], mounts=[expedition.mount])

        self.assertEqual(self.balance(), -7)
        self.assertFalse(UserInventory.objects.filter(user=self.user).exists())
        receipt.refresh_from_db()
        incubation.refresh_from_db()
        self.assertEqual(receipt.status, "pending")
        self.assertNotIn(RETURN_MARKER, incubation.accepted_pair)

    def test_exact_candidates_and_recorded_debits_do_not_credit_another_family(self):
        other = make_family("Other resource family", children=[{"username": "other-resource-child"}]).children[0]
        receipt = self.redemption(debit=7)
        CoinLedger.objects.create(user=other, amount=-20, reason="redemption", redemption=receipt)

        self.assertEqual(collect_retirement_resource_user_ids(redemption_ids=[receipt.pk]), {self.user.pk})
        result = self.settle(redemptions=[receipt])

        self.assertEqual(self.balance(), 0)
        self.assertEqual(result["refunds"][0]["coins"], 7)
        self.assertEqual(CoinLedger.objects.filter(user=other).aggregate(total=Sum("amount"))["total"], -20)

    def test_retirement_settles_persisted_loot_before_deleting_an_unclaimed_mount(self):
        self.expedition(ready=True)

        retire_unused_catalog()

        self.assertEqual(self.balance(), 17)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.food).quantity, 3)
        self.assertFalse(UserInventory.objects.filter(user=self.user, item_id=self.egg.pk).exists())
