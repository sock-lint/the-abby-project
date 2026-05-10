"""Tests for the Mount Expedition (Finch-inspired offline play) feature.

Pinned behaviours:

* Start: cooldown enforcement (one expedition per mount per local day),
  cross-user 404 (existence-leak prevention), tier validation, daily-cap
  blocking even when the prior expedition has been claimed (so a
  start-claim-start cycle on the same day still blocks).
* Claim: idempotency (second claim returns same shape with
  ``coins_awarded=0``), too-early rejection, GameLoopService called with
  ``drops_allowed=False`` so the trigger doesn't re-roll on top of the
  pre-rolled loot, Lucky Coin doubles the haul (boost-whitelist regression),
  cosmetic-dupe salvage path mirrors ``DropService``.
* Mount lookup is family-scoped on every endpoint.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.pets.expeditions import ExpeditionError, ExpeditionService, TIER_CONFIG
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.rpg.models import (
    CharacterProfile, DropTable, ItemDefinition, UserInventory,
)


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


def _make_species(slug, name=None):
    return PetSpecies.objects.create(slug=slug, name=name or slug.title())


def _make_potion(slug, name=None, rarity="common"):
    return PotionType.objects.create(slug=slug, name=name or slug.title(), rarity=rarity)


def _make_item(slug, *, item_type="food", rarity="common", coin_value=0, name=None):
    return ItemDefinition.objects.create(
        slug=slug,
        name=name or slug.title(),
        icon="🎁",
        item_type=item_type,
        rarity=rarity,
        coin_value=coin_value,
    )


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ExpeditionStartTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.species = _make_species("wolf")
        self.potion = _make_potion("base")
        self.mount = UserMount.objects.create(
            user=self.user, species=self.species, potion=self.potion,
        )
        # Add a fallback drop table entry so loot rolling has something
        # to draw from. Uses CLOCK_OUT trigger to exercise the fallback path.
        self.food = _make_item("training-snack", item_type="food")
        DropTable.objects.create(
            trigger_type="clock_out", item=self.food, weight=10,
        )

    def test_start_creates_active_expedition(self):
        expedition = ExpeditionService.start(self.user, self.mount.pk, "short")
        self.assertEqual(expedition.status, MountExpedition.Status.ACTIVE)
        self.assertEqual(expedition.tier, "short")
        self.assertEqual(expedition.mount, self.mount)
        # Returns_at sits in the future by tier duration.
        delta_minutes = (expedition.returns_at - expedition.started_at).total_seconds() / 60
        self.assertAlmostEqual(delta_minutes, TIER_CONFIG["short"]["duration_minutes"], delta=1)
        # Loot pre-rolled.
        self.assertGreater(expedition.loot.get("coins", 0), 0)

    def test_unknown_tier_rejected(self):
        with self.assertRaises(ExpeditionError):
            ExpeditionService.start(self.user, self.mount.pk, "marathon")

    def test_cross_user_mount_lookup_raises_not_found(self):
        other = User.objects.create_user(
            username="rival", password="pw", role="child",
        )
        # Same-shape error string the view layer turns into 404.
        with self.assertRaises(ExpeditionError) as ctx:
            ExpeditionService.start(other, self.mount.pk, "short")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_cannot_start_two_at_once(self):
        ExpeditionService.start(self.user, self.mount.pk, "short")
        with self.assertRaises(ExpeditionError) as ctx:
            ExpeditionService.start(self.user, self.mount.pk, "short")
        self.assertIn("already out", str(ctx.exception))

    def test_daily_cap_blocks_second_start_even_after_claim(self):
        first = ExpeditionService.start(self.user, self.mount.pk, "short")
        # Fast-forward: mark the first expedition as claimed by hand.
        first.status = MountExpedition.Status.CLAIMED
        first.claimed_at = timezone.now()
        first.save()
        with self.assertRaises(ExpeditionError) as ctx:
            ExpeditionService.start(self.user, self.mount.pk, "short")
        self.assertIn("already been out today", str(ctx.exception).lower())


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ExpeditionClaimTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.species = _make_species("wolf")
        self.potion = _make_potion("base")
        self.mount = UserMount.objects.create(
            user=self.user, species=self.species, potion=self.potion,
        )
        self.food = _make_item("training-snack", item_type="food")
        DropTable.objects.create(
            trigger_type="clock_out", item=self.food, weight=10,
        )

    def _start_and_fast_forward(self, tier="short"):
        expedition = ExpeditionService.start(self.user, self.mount.pk, tier)
        # Shift returns_at into the past.
        expedition.returns_at = timezone.now() - timedelta(seconds=5)
        expedition.save(update_fields=["returns_at"])
        return expedition

    def test_claim_too_early_rejected(self):
        expedition = ExpeditionService.start(self.user, self.mount.pk, "short")
        with self.assertRaises(ExpeditionError) as ctx:
            ExpeditionService.claim(self.user, expedition.pk)
        self.assertIn("still out", str(ctx.exception))

    def test_claim_materializes_coins_and_items(self):
        expedition = self._start_and_fast_forward("short")
        result = ExpeditionService.claim(self.user, expedition.pk)
        self.assertTrue(result["freshly_claimed"])
        self.assertGreater(result["coins_awarded"], 0)

        # Coin ledger row written with the dedicated reason.
        ledger = CoinLedger.objects.filter(
            user=self.user, reason=CoinLedger.Reason.EXPEDITION,
        )
        self.assertEqual(ledger.count(), 1)
        self.assertEqual(int(ledger.first().amount), result["coins_awarded"])

        # Inventory row created for the food item (the only seed item).
        inv = UserInventory.objects.filter(user=self.user, item=self.food).first()
        self.assertIsNotNone(inv)
        self.assertGreaterEqual(inv.quantity, 1)

    def test_claim_is_idempotent(self):
        expedition = self._start_and_fast_forward("short")
        first = ExpeditionService.claim(self.user, expedition.pk)
        second = ExpeditionService.claim(self.user, expedition.pk)
        # Second claim returns the same shape but no new awards.
        self.assertEqual(first["expedition_id"], second["expedition_id"])
        self.assertFalse(second["freshly_claimed"])
        self.assertEqual(second["coins_awarded"], 0)
        # Only one ledger row exists.
        self.assertEqual(
            CoinLedger.objects.filter(
                user=self.user, reason=CoinLedger.Reason.EXPEDITION,
            ).count(),
            1,
        )

    def test_lucky_coin_doubles_expedition_payout(self):
        # Set Lucky Coin boost to active.
        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        profile.save(update_fields=["coin_boost_expires_at"])

        expedition = self._start_and_fast_forward("short")
        planned_coins = expedition.loot["coins"]
        result = ExpeditionService.claim(self.user, expedition.pk)
        # CoinService.award_coins applies the 2.0x multiplier.
        self.assertEqual(result["coins_awarded"], planned_coins * 2)

    def test_claim_calls_game_loop_with_drops_disabled(self):
        expedition = self._start_and_fast_forward("short")
        with patch(
            "apps.rpg.services.GameLoopService.on_task_completed",
            return_value={"trigger_type": "expedition_returned", "drops": [], "streak": {}, "quest": None, "notifications": []},
        ) as game_loop:
            ExpeditionService.claim(self.user, expedition.pk)

        self.assertEqual(game_loop.call_count, 1)
        _user, trigger, ctx = game_loop.call_args[0]
        self.assertEqual(str(trigger), "expedition_returned")
        self.assertFalse(ctx.get("drops_allowed", True))

    def test_cosmetic_duplicate_salvages_to_coins(self):
        # Pre-load a cosmetic the user already owns.
        cosmetic = _make_item(
            "frame-test", item_type="cosmetic_frame",
            rarity="rare", coin_value=20,
        )
        UserInventory.objects.create(user=self.user, item=cosmetic, quantity=1)

        # Build an expedition row directly with a forced loot payload that
        # includes the dupe — bypasses the random roll.
        expedition = MountExpedition.objects.create(
            mount=self.mount,
            tier="short",
            status=MountExpedition.Status.ACTIVE,
            started_at=timezone.now() - timedelta(hours=2, minutes=10),
            returns_at=timezone.now() - timedelta(seconds=5),
            loot={
                "coins": 10,
                "items": [{
                    "item_id": cosmetic.pk, "quantity": 1,
                    "name": cosmetic.name, "icon": cosmetic.icon,
                    "rarity": cosmetic.rarity, "item_type": cosmetic.item_type,
                    "sprite_key": cosmetic.sprite_key,
                }],
            },
        )

        ExpeditionService.claim(self.user, expedition.pk)

        # Cosmetic quantity stays at 1 (no dupe) but a salvage coin row exists.
        self.assertEqual(
            UserInventory.objects.get(user=self.user, item=cosmetic).quantity,
            1,
        )
        salvage = CoinLedger.objects.filter(
            user=self.user,
            reason=CoinLedger.Reason.ADJUSTMENT,
            description__icontains="Salvaged duplicate from expedition",
        )
        self.assertEqual(salvage.count(), 1)
        self.assertEqual(int(salvage.first().amount), cosmetic.coin_value)


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ExpeditionAPITests(TestCase):
    """Smoke-tests the URL routing + permission shape."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.species = _make_species("wolf")
        self.potion = _make_potion("base")
        self.mount = UserMount.objects.create(
            user=self.user, species=self.species, potion=self.potion,
        )
        DropTable.objects.create(
            trigger_type="clock_out",
            item=_make_item("training-snack", item_type="food"),
            weight=10,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_start_endpoint_returns_201(self):
        url = reverse("mount-expedition-start", args=[self.mount.pk])
        response = self.client.post(url, {"tier": "short"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["tier"], "short")
        self.assertEqual(response.data["status"], "active")

    def test_start_endpoint_returns_404_for_other_user_mount(self):
        other = User.objects.create_user(
            username="rival", password="pw", role="child",
        )
        other_mount = UserMount.objects.create(
            user=other, species=self.species, potion=self.potion,
        )
        url = reverse("mount-expedition-start", args=[other_mount.pk])
        response = self.client.post(url, {"tier": "short"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_start_endpoint_validates_tier(self):
        url = reverse("mount-expedition-start", args=[self.mount.pk])
        response = self.client.post(url, {"tier": "marathon"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_list_endpoint_returns_user_expeditions_only(self):
        ExpeditionService.start(self.user, self.mount.pk, "short")
        url = reverse("expeditions-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["expeditions"]), 1)

    def test_list_ready_filter(self):
        # Active but not yet ready.
        ExpeditionService.start(self.user, self.mount.pk, "short")
        url = reverse("expeditions-list")
        response = self.client.get(url + "?ready=true")
        self.assertEqual(len(response.data["expeditions"]), 0)

        # Fast-forward and re-check.
        MountExpedition.objects.filter(mount=self.mount).update(
            returns_at=timezone.now() - timedelta(seconds=5),
        )
        response = self.client.get(url + "?ready=true")
        self.assertEqual(len(response.data["expeditions"]), 1)

    def test_claim_endpoint_returns_404_for_other_user(self):
        other = User.objects.create_user(
            username="rival", password="pw", role="child",
        )
        other_mount = UserMount.objects.create(
            user=other, species=self.species, potion=self.potion,
        )
        expedition = MountExpedition.objects.create(
            mount=other_mount, tier="short",
            status=MountExpedition.Status.ACTIVE,
            started_at=timezone.now() - timedelta(hours=3),
            returns_at=timezone.now() - timedelta(seconds=5),
            loot={"coins": 10, "items": []},
        )
        url = reverse("expedition-claim", args=[expedition.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
