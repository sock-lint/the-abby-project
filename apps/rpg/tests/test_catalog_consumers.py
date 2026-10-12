from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, UserBadge
from apps.dev_tools.operations import OperationError, force_drop, grant_hatch_ingredients
from apps.notifications.models import Notification, NotificationType
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.quests.models import QuestDefinition, QuestRewardItem
from apps.quests.serializers import QuestDefinitionSerializer
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger, Reward, RewardRedemption, RewardWishlist
from apps.rewards.views import RewardViewSet
from apps.rewards.services import CoinService, RewardService, RewardUnavailableError
from apps.rpg.models import DropLog, ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class CatalogConsumerTests(APITestCase):
    def setUp(self):
        family = make_family("Catalog household", parents=[{"username": "catalog-parent"}], children=[{"username": "catalog-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.chick = PetSpecies.objects.create(slug="chick", name="Chick", icon="C", sprite_key="cute-chick")
        self.fox = PetSpecies.objects.create(slug="fox", name="Fox", icon="F", sprite_key="fox")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.chick.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(slug="fox-egg", name="Fox egg", icon="E", item_type="egg", pet_species=self.fox)
        self.accessory = ItemDefinition.objects.create(slug="accessory-crown", name="Crown", icon="C", item_type="cosmetic_pet_accessory")
        self.frame = ItemDefinition.objects.create(slug="frame-gold", name="Gold frame", icon="G", item_type="cosmetic_frame", metadata={"border_color": "#abcdef"})

    def reward(self):
        return Reward.objects.create(family=self.child.family, name="Crown reward", cost_coins=20, stock=2, fulfillment_kind="digital_item", item_definition=self.accessory)

    def test_new_digital_request_cannot_charge_or_consume_stock_for_unavailable_item(self):
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.ADJUSTMENT)
        reward = self.reward()
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(self.child, reward)
        reward.refresh_from_db()
        self.assertEqual(reward.stock, 2)
        self.assertEqual(CoinService.get_balance(self.child), 100)
        self.assertFalse(RewardRedemption.objects.filter(user=self.child).exists())
        self.client.force_authenticate(self.child)
        self.assertNotIn(reward.pk, [entry["id"] for entry in self.client.get("/api/rewards/").json()["results"]])
        self.assertEqual(self.client.post(f"/api/rewards/{reward.pk}/redeem/").status_code, 404)

    def test_pending_redemption_keeps_its_promised_item_and_can_be_approved_once(self):
        reward = self.reward()
        pending = RewardRedemption.objects.create(user=self.child, reward=reward, coin_cost_snapshot=20)
        RewardService.approve(pending, self.parent)
        RewardService.approve(pending, self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.accessory).quantity, 1)

    def test_parent_cannot_publish_new_unavailable_digital_reward_but_can_retire_old_one(self):
        self.client.force_authenticate(self.parent)
        body = {"name": "New crown", "cost_coins": 5, "fulfillment_kind": "digital_item", "item_definition": self.accessory.pk}
        self.assertEqual(self.client.post("/api/rewards/", body, format="json").status_code, 400)
        self.assertFalse(Reward.objects.filter(name="New crown").exists())
        reward = self.reward()
        self.assertEqual(self.client.patch(f"/api/rewards/{reward.pk}/", {"is_active": False}, format="json").status_code, 200)

    def test_wishlist_offers_hide_unavailable_items_without_removing_saved_rows(self):
        retired = self.reward()
        available = Reward.objects.create(
            family=self.child.family, name="Frame reward", cost_coins=5,
            fulfillment_kind="digital_item", item_definition=self.frame,
        )
        inactive = Reward.objects.create(
            family=self.child.family, name="Inactive reward", cost_coins=5,
            is_active=False,
        )
        for reward in (retired, available, inactive):
            RewardWishlist.objects.create(user=self.child, reward=reward)
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/rewards/my-wishlist/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()], [available.pk])
        self.assertEqual(RewardWishlist.objects.filter(user=self.child).count(), 3)

    def test_child_and_parent_cannot_add_unavailable_reward_to_wishlist(self):
        retired = self.reward()
        for actor, expected_status in ((self.child, 404), (self.parent, 400)):
            with self.subTest(actor=actor.role):
                self.client.force_authenticate(actor)
                response = self.client.post(f"/api/rewards/{retired.pk}/wishlist/")
                self.assertEqual(response.status_code, expected_status)
                self.assertFalse(RewardWishlist.objects.filter(user=actor, reward=retired).exists())

    def test_saved_unavailable_inactive_wishlist_entry_can_be_removed_idempotently(self):
        retired = self.reward()
        retired.is_active = False
        retired.save(update_fields=["is_active"])
        RewardWishlist.objects.create(user=self.child, reward=retired)
        RewardWishlist.objects.create(user=self.parent, reward=retired)
        self.client.force_authenticate(self.child)
        for _attempt in range(2):
            response = self.client.delete(f"/api/rewards/{retired.pk}/wishlist/")
            self.assertEqual(response.status_code, 204)
        self.assertFalse(RewardWishlist.objects.filter(user=self.child, reward=retired).exists())
        self.assertTrue(RewardWishlist.objects.filter(user=self.parent, reward=retired).exists())
        self.assertTrue(Reward.objects.filter(pk=retired.pk).exists())

    def test_wishlist_delete_does_not_resolve_another_familys_retained_reward(self):
        other = make_family("Other household", children=[{"username": "catalog-other-child"}])
        foreign_reward = Reward.objects.create(
            family=other.family, name="Foreign retired crown", cost_coins=5,
            fulfillment_kind="digital_item", item_definition=self.accessory, is_active=False,
        )
        entry = RewardWishlist.objects.create(user=other.children[0], reward=foreign_reward)
        for actor in (self.child, self.parent):
            with self.subTest(actor=actor.role):
                self.client.force_authenticate(actor)
                response = self.client.delete(f"/api/rewards/{foreign_reward.pk}/wishlist/")
                self.assertEqual(response.status_code, 404)
                self.assertTrue(RewardWishlist.objects.filter(pk=entry.pk).exists())

    def test_unavailable_or_inactive_restock_keeps_bookmarks_without_promising_items(self):
        retired = self.reward()
        retired.stock = 0
        retired.save(update_fields=["stock"])
        RewardWishlist.objects.create(user=self.child, reward=retired)
        with patch("apps.notifications.services.notify") as notify, patch("django.core.mail.send_mail") as email:
            # An authored unavailable active offer must not produce a restock
            # promise even if another parent integration invokes the helper.
            RewardViewSet._notify_wishlist_on_restock(retired)
            self.client.force_authenticate(self.parent)
            response = self.client.patch(
                f"/api/rewards/{retired.pk}/", {"is_active": False, "stock": 1}, format="json",
            )
            self.assertEqual(response.status_code, 200)
            notify.assert_not_called()
            email.assert_not_called()
        self.assertTrue(RewardWishlist.objects.filter(user=self.child, reward=retired).exists())
        self.assertFalse(Notification.objects.filter(
            user=self.child, notification_type=NotificationType.REWARD_RESTOCKED,
        ).exists())

    def test_stale_quest_rewards_do_not_mint_unavailable_items_or_replacement_coins(self):
        definition = QuestDefinition.objects.create(name="Catalog quest", quest_type="collection", target_value=1, coin_reward=5, xp_reward=0)
        for item in (self.egg, self.accessory, self.frame):
            QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=1)
        visible = QuestDefinitionSerializer(definition).data["reward_items"]
        self.assertEqual([entry["item"] for entry in visible], [self.frame.pk])
        QuestService.start_quest(self.child, definition.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertTrue(result["completed"])
        self.assertEqual(CoinService.get_balance(self.child), 5)
        self.assertEqual(list(UserInventory.objects.filter(user=self.child).values_list("item_id", flat=True)), [self.frame.pk])

    def test_dev_grants_cannot_bypass_catalog_boundary(self):
        with self.assertRaises(OperationError):
            force_drop(self.child, slug=self.egg.slug)
        with self.assertRaises(OperationError):
            grant_hatch_ingredients(self.child, species_slug="fox", potion_slug="base")
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())

    def test_unreachable_badge_goal_is_not_advertised_but_earned_badge_is_preserved(self):
        badge = Badge.objects.create(name="Three species", icon="B", criteria_type="pet_species_owned", criteria_value={"count": 3})
        self.client.force_authenticate(self.child)
        self.assertNotIn(badge.pk, [entry["id"] for entry in self.client.get("/api/badges/").json()["results"]])
        UserBadge.objects.create(user=self.child, badge=badge)
        saved = self.client.get("/api/badges/").json()["results"]
        row = next(entry for entry in saved if entry["id"] == badge.pk)
        self.assertFalse(row["catalog_available"])
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())

    def test_earned_summary_and_catalog_keep_reachable_saved_pet_goals_consistent(self):
        for species in (self.chick, self.fox):
            UserPet.objects.create(user=self.child, species=species, potion=self.base)
        badge = Badge.objects.create(name="Two saved species", icon="B", criteria_type="pet_species_owned", criteria_value={"count": 2})
        UserBadge.objects.create(user=self.child, badge=badge)
        self.client.force_authenticate(self.child)
        catalog = self.client.get("/api/badges/").json()["results"]
        summary = self.client.get("/api/achievements/summary/").json()["badges_earned"]
        self.assertTrue(next(entry for entry in catalog if entry["id"] == badge.pk)["catalog_available"])
        self.assertTrue(next(entry["badge"] for entry in summary if entry["badge"]["id"] == badge.pk)["catalog_available"])
