"""Discovery retires prospective egg sources while honoring saved promises."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge, UserBadge
from apps.dev_tools.operations import OperationError, force_drop, grant_hatch_ingredients
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.schemas import ListRewardsIn, RequestRedemptionIn, UseConsumableIn
from apps.mcp_server.tools import inventory as inventory_tools, rewards as reward_tools
from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetIncubation, UserMount
from apps.pets.services import PetService
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService, RewardUnavailableError
from apps.rpg.catalog_support import item_is_available
from apps.rpg.inventory import grant_item
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import DropService
from config.tests.factories import make_family

from .factories import ASSET_POLICY, make_catalog


def first_choice(rows, **_kwargs):
    return [rows[0]]


@override_settings(
    EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={}, RPG_ASSET_SUPPORT_POLICY=ASSET_POLICY,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class LegacyEggSourceTransitionTests(TestCase):
    def setUp(self):
        family = make_family("Egg transition", parents=[{"username": "transition-parent"}],
                             children=[{"username": "transition-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.catalog = make_catalog()
        self.egg, self.food = self.catalog.ordinary.egg, self.catalog.food
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def shop_offer(self, *, kind="digital_item"):
        return Reward.objects.create(
            family=self.child.family, name=f"Egg reward {kind}", cost_coins=20, stock=2,
            fulfillment_kind=kind, item_definition=self.egg,
        )

    def box(self):
        item = ItemDefinition.objects.create(
            slug="transition-box", name="Saved Mystery Box", item_type="consumable",
            metadata={"effect": "mystery_box", "rarities": ["common"]},
        )
        return item, UserInventory.objects.create(user=self.child, item=item, quantity=2)

    def test_task_and_accomplishment_draws_exclude_eggs_and_keep_supplies(self):
        for trigger in ("clock_out", "badge_earned", "quest_complete"):
            with self.subTest(trigger=trigger):
                DropTable.objects.create(trigger_type=trigger, item=self.egg)
                with patch("apps.rpg.services.random.random", return_value=0):
                    self.assertEqual(DropService.process_drops(self.child, trigger), [])
                self.assertFalse(DropLog.objects.filter(trigger_type=trigger).exists())
                DropTable.objects.create(trigger_type=trigger, item=self.food)
                with patch("apps.rpg.services.random.random", return_value=0), patch(
                    "apps.rpg.services.random.choices", side_effect=first_choice,
                ):
                    result = (DropService.process_drops(self.child, trigger) if trigger == "clock_out"
                              else DropService.award_accomplishment(self.child, trigger))
                self.assertEqual(result[0]["item_id"], self.food.pk)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item__item_type="egg").exists())
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 3)

    @override_settings(EGG_DISCOVERY_ENABLED=False)
    def test_disabled_transition_keeps_the_original_random_egg_draw(self):
        DropTable.objects.create(trigger_type="clock_out", item=self.egg)
        with patch("apps.rpg.services.random.random", return_value=0):
            result = DropService.process_drops(self.child, "clock_out")
        self.assertEqual(result[0]["item_id"], self.egg.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.egg).quantity, 1)

    def test_perfect_day_keeps_noncommon_supplies_without_egg_substitution(self):
        for item in (self.egg, self.food):
            item.rarity = "uncommon"
            item.save(update_fields=["rarity"])
            DropTable.objects.create(trigger_type="perfect_day", item=item)
        with patch("apps.rpg.services.random.random", return_value=0), patch(
            "apps.rpg.services.random.choices", side_effect=first_choice,
        ):
            result = DropService.award_accomplishment(self.child, "perfect_day")
        self.assertEqual(result[0]["item_id"], self.food.pk)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.egg).exists())

    def test_saved_box_keeps_effect_rarity_and_quantity_while_using_non_egg_pool(self):
        box, stack = self.box()
        # Leave precisely a supported egg and food within the box's rarity.
        ItemDefinition.objects.filter(item_type="potion").update(rarity="uncommon")
        with patch("apps.rpg.services.random.choices", side_effect=first_choice):
            result = self.client.post(f"/api/inventory/{box.pk}/use/", {}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["effect"], "mystery_box")
        self.assertEqual(result.data["detail"]["granted_item_id"], self.food.pk)
        stack.refresh_from_db()
        box.refresh_from_db()
        self.assertEqual(stack.quantity, 1)
        self.assertEqual(box.metadata, {"effect": "mystery_box", "rarities": ["common"]})
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.egg).exists())

    def test_egg_only_box_fails_without_consuming_or_awarding_through_mcp(self):
        box, stack = self.box()
        ItemDefinition.objects.filter(item_type__in=["food", "potion"]).update(rarity="uncommon")
        with override_user(self.child), self.assertRaises(MCPValidationError):
            inventory_tools.use_consumable(UseConsumableIn(item_id=box.pk))
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 2)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.egg).exists())

    @override_settings(EGG_DISCOVERY_ENABLED=False)
    def test_disabled_transition_keeps_the_original_box_egg_pool(self):
        box, stack = self.box()
        with patch("apps.rpg.services.random.choices", side_effect=lambda rows, **_kwargs: [
            next(item for item in rows if item.pk == self.egg.pk),
        ]):
            result = self.client.post(f"/api/inventory/{box.pk}/use/", {}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["detail"]["granted_item_id"], self.egg.pk)
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 1)

    def test_inventory_badge_cascade_cannot_reintroduce_egg_drops(self):
        badge = Badge.objects.create(
            name="Full shelf transition", criteria_type="full_potion_shelf", criteria_value={},
            xp_bonus=0, award_coins=False,
        )
        for item in (self.egg, self.food):
            DropTable.objects.create(trigger_type="badge_earned", item=item)
        with patch("apps.rpg.services.random.random", return_value=0), patch(
            "apps.rpg.services.random.choices", side_effect=first_choice,
        ):
            grant_item(self.child, self.catalog.potion)
            grant_item(self.child, self.catalog.potion)
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assertEqual(DropLog.objects.get(user=self.child, trigger_type="badge_earned").item_id, self.food.pk)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.egg).exists())

    def test_new_expedition_start_filters_both_dedicated_and_fallback_pools(self):
        mount = UserMount.objects.create(user=self.child, species=self.catalog.ordinary.species, potion=self.catalog.base)
        for trigger in ("expedition_returned", "clock_out"):
            with self.subTest(trigger=trigger):
                DropTable.objects.all().delete()
                for item in (self.egg, self.food):
                    DropTable.objects.create(trigger_type=trigger, item=item)
                with patch("apps.pets.expeditions.random.choices", side_effect=first_choice):
                    loot = ExpeditionService._roll_loot(self.child, "long")
                self.assertEqual([slot["item_id"] for slot in loot["items"]], [self.food.pk] * 3)
        with patch("apps.pets.expeditions.random.choices", side_effect=first_choice):
            accepted = ExpeditionService.start(self.child, mount.pk, "short")
        self.assertEqual([slot["item_id"] for slot in accepted.loot["items"]], [self.food.pk])

    def test_prerolled_egg_expedition_claims_exact_saved_loot_once(self):
        mount = UserMount.objects.create(user=self.child, species=self.catalog.ordinary.species, potion=self.catalog.base)
        saved = MountExpedition.objects.create(
            mount=mount, tier="short", started_at=timezone.now() - timedelta(hours=3),
            returns_at=timezone.now() - timedelta(hours=1),
            loot={"coins": 7, "items": [{"item_id": self.egg.pk, "quantity": 2, "name": "Saved egg", "item_type": "egg"}]},
        )
        with patch("apps.rpg.services.GameLoopService.on_task_completed", return_value={}):
            first = ExpeditionService.claim(self.child, saved.pk)
            second = ExpeditionService.claim(self.child, saved.pk)
        self.assertEqual(first["items"], second["items"])
        self.assertEqual(first["coins_awarded"], 7)
        self.assertEqual(second["coins_awarded"], 0)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.egg).quantity, 2)
        self.assertEqual(CoinService.get_balance(self.child), 7)

    def test_shop_lists_and_direct_rest_mcp_requests_cannot_charge_for_new_eggs(self):
        offer = self.shop_offer()
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.ADJUSTMENT)
        self.assertNotIn(offer.pk, [row["id"] for row in self.client.get("/api/rewards/").data["results"]])
        self.assertEqual(self.client.post(f"/api/rewards/{offer.pk}/redeem/").status_code, 404)
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(self.child, offer)
        with override_user(self.child):
            self.assertNotIn(offer.pk, [row["id"] for row in reward_tools.list_rewards(ListRewardsIn())["rewards"]])
            with self.assertRaises(MCPValidationError):
                reward_tools.request_redemption(RequestRedemptionIn(reward_id=offer.pk, request_id=uuid4()))
        offer.refresh_from_db()
        self.assertEqual(offer.stock, 2)
        self.assertEqual(CoinService.get_balance(self.child), 100)
        self.assertFalse(RewardRedemption.objects.filter(user=self.child).exists())

    def test_new_parent_egg_offer_is_rejected_but_existing_offer_can_be_retired(self):
        offer = self.shop_offer()
        self.client.force_authenticate(self.parent)
        result = self.client.post("/api/rewards/", {
            "name": "Another new egg", "cost_coins": 5, "fulfillment_kind": "digital_item",
            "item_definition": self.egg.pk,
        }, format="json")
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Reward.objects.filter(name="Another new egg").exists())
        self.assertEqual(self.client.patch(f"/api/rewards/{offer.pk}/", {"is_active": False}, format="json").status_code, 200)

    def test_parent_personal_shop_hides_new_eggs_and_keeps_own_balance(self):
        offer = self.shop_offer()
        CoinService.award_coins(self.parent, 100, CoinLedger.Reason.ADJUSTMENT)
        self.client.force_authenticate(self.parent)
        result = self.client.get("/api/rewards/", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(offer.pk, [row["id"] for row in result.data["results"]])
        self.assertEqual(self.client.post(
            f"/api/rewards/{offer.pk}/redeem/", {}, format="json", HTTP_X_ABBY_SPACE="personal",
        ).status_code, 404)
        self.assertEqual(CoinService.get_balance(self.parent), 100)
        self.assertEqual(CoinService.get_balance(self.child), 0)

    def test_paid_digital_and_combined_promises_survive_cutover_and_offer_edits(self):
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.ADJUSTMENT)
        for kind in ("digital_item", "both"):
            offer = self.shop_offer(kind=kind)
            with override_settings(EGG_DISCOVERY_ENABLED=False):
                pending = RewardService.request_redemption(self.child, offer)
            offer.item_definition = self.food
            offer.is_active = False
            offer.save(update_fields=["item_definition", "is_active"])
            RewardService.approve(pending, self.parent)
            RewardService.approve(pending, self.parent)
            if kind == "both":
                RewardService.deliver(pending, self.parent)
                RewardService.deliver(pending, self.parent)
            pending.refresh_from_db()
            self.assertEqual(pending.status, "fulfilled")
            self.assertEqual(pending.item_definition_snapshot_id, self.egg.pk)
            offer.refresh_from_db()
            self.assertEqual(offer.stock, 1)
        self.assertEqual(CoinService.get_balance(self.child), 60)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.egg).quantity, 2)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.food).exists())

    def test_development_grants_cannot_bypass_discovery(self):
        with self.assertRaises(OperationError):
            force_drop(self.child, slug=self.egg.slug)
        with self.assertRaises(OperationError):
            force_drop(self.child, rarity="rare")
        with self.assertRaises(OperationError):
            grant_hatch_ingredients(self.child, species_slug=self.catalog.ordinary.species.slug, potion_slug="base")
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())

    @override_settings(EGG_DISCOVERY_ENABLED=False)
    def test_disabled_transition_keeps_dev_grants_and_shop_requests(self):
        force_drop(self.child, slug=self.egg.slug)
        grant_hatch_ingredients(self.child, species_slug=self.catalog.ordinary.species.slug, potion_slug="base")
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.ADJUSTMENT)
        pending = RewardService.request_redemption(self.child, self.shop_offer())
        self.assertEqual(pending.status, "pending")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.egg).quantity, 2)

    def test_owned_egg_still_incubates_and_hatches_once(self):
        for item in (self.egg, self.catalog.potion):
            UserInventory.objects.create(user=self.child, item=item, quantity=1)
        self.assertTrue(item_is_available(self.egg))
        accepted, _ = PetService.start_incubation(self.child, self.egg.pk, self.catalog.potion.pk, uuid4())
        accepted.ready_at = timezone.now() - timedelta(seconds=1)
        accepted.save(update_fields=["ready_at"])
        first, pet, fresh = PetService.hatch_incubation(self.child, accepted.pk)
        second, same, repeated = PetService.hatch_incubation(self.child, accepted.pk)
        self.assertTrue(fresh)
        self.assertFalse(repeated)
        self.assertEqual(pet.pk, same.pk)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PetIncubation.objects.filter(user=self.child).count(), 1)

    def test_codex_exposes_discovery_and_omits_unaccepted_old_challenge_without_writes(self):
        definition = QuestDefinition.objects.create(
            name="Old public egg trail", quest_type="collection", target_value=3,
            duration_days=7, is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        for item in (self.egg, self.catalog.potion):
            QuestRewardItem.objects.create(quest_definition=definition, item=item)
        with CaptureQueriesContext(connection) as queries:
            body = self.client.get("/api/pets/codex/").data
        self.assertTrue(body["egg_discovery_enabled"])
        species = next(row for row in body["species"] if row["id"] == self.catalog.ordinary.species.pk)
        potion = species["available_potions"][0]
        self.assertEqual(potion["acquisition_challenges"], [])
        self.assertEqual(potion["acquisition_discovery"], {
            "key": self.catalog.ordinary.key, "path": "/quests?tab=trials",
            "name": f"{self.egg.display_name} · Base", "eligible": True,
            "unavailable_reason": None, "tier": "ordinary",
        })
        self.assertFalse(any(row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for row in queries))
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            body = self.client.get("/api/pets/codex/").data
        species = next(row for row in body["species"] if row["id"] == self.catalog.ordinary.species.pk)
        self.assertFalse(body["egg_discovery_enabled"])
        self.assertIsNone(species["available_potions"][0]["acquisition_discovery"])
        self.assertEqual(species["available_potions"][0]["acquisition_challenges"][0]["definition_id"], definition.pk)

    def test_item_hint_keeps_current_saved_promise_but_omits_unsaved_later_egg_cycle(self):
        definition = QuestDefinition.objects.create(
            name="Accepted repeat egg trail", quest_type="collection", target_value=3,
            duration_days=7, is_system=True, is_repeatable=True,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestRewardItem.objects.create(quest_definition=definition, item=self.egg)
        self.shop_offer()
        now = timezone.now()
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=definition,
            is_catalog=True, name="Saved egg promise", metric="count", target=3,
            starts_at=now - timedelta(days=8), ends_at=now - timedelta(days=1), repeat_days=7,
            timezone_name="UTC", reward_items=[{"item_id": self.egg.pk, "quantity": 1}],
        )

        def hint():
            self.client.force_authenticate(self.parent)
            # Parent catalog resolves self, so use native serializer with the
            # actual child request to assert family-scoped hints.
            from rest_framework.request import Request
            from rest_framework.test import APIRequestFactory
            from apps.rpg.serializers import ItemDefinitionSerializer
            request = Request(APIRequestFactory().get("/api/items/catalog/"))
            request.user = self.child
            return ItemDefinitionSerializer(self.egg, context={"request": request}).data["acquisition_sources"]

        self.assertEqual(hint(), [{"kind": "discovery", "name": "Choose an egg discovery", "path": "/quests?tab=trials"}])
        ChallengeOccurrence.objects.create(
            goal=goal, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=6),
            snapshot={"items": [{"item_id": self.egg.pk, "quantity": 1}]},
        )
        self.assertIn({"kind": "challenge", "name": goal.name, "path": "/quests?tab=trials"}, hint())

    def test_codex_keeps_accepted_cycle_zero_and_saved_window_but_hides_unsaved_future_cycles(self):
        definition = QuestDefinition.objects.create(
            name="Accepted exact hatch pair", quest_type="collection", target_value=3,
            duration_days=7, is_system=True, is_repeatable=True,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        rewards = [{"item_id": item.pk, "quantity": 1} for item in (self.egg, self.catalog.potion)]
        for item in (self.egg, self.catalog.potion):
            QuestRewardItem.objects.create(quest_definition=definition, item=item)
        now = timezone.now()
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=definition,
            is_catalog=True, name="The saved enrollment", metric="count", target=3,
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=6), repeat_days=7,
            timezone_name="UTC", reward_items=rewards,
        )

        def paths():
            body = self.client.get("/api/pets/codex/").data
            species = next(row for row in body["species"] if row["id"] == self.catalog.ordinary.species.pk)
            return species["available_potions"][0]["acquisition_challenges"]

        pending = paths()
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0]["offer_available"])
        self.assertEqual(pending[0]["name"], goal.name)
        self.assertFalse(ChallengeOccurrence.objects.filter(goal=goal).exists())
        goal.starts_at = now - timedelta(days=8)
        goal.ends_at = now - timedelta(days=1)
        goal.save(update_fields=["starts_at", "ends_at"])
        self.assertEqual(paths(), [])
        saved = ChallengeOccurrence.objects.create(
            goal=goal, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=6),
            snapshot={"name": "The saved current window", "target": "3", "items": rewards},
        )
        retained = paths()
        self.assertEqual(len(retained), 1)
        self.assertFalse(retained[0]["offer_available"])
        self.assertEqual(retained[0]["attempt"]["id"], f"goal:{saved.pk}")
