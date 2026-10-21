"""Tests for Tier-1.3 reward shop CRUD + coin adjustments via MCP."""
from __future__ import annotations

from uuid import uuid4

from django.test import TestCase, override_settings

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    AdjustCoinsIn,
    CreateRewardIn,
    DecideRedemptionIn,
    DeleteRewardIn,
    RequestRedemptionIn,
    UpdateRewardIn,
)
from apps.mcp_server.tools import rewards as reward_tools
from apps.accounts.models import User
from apps.rewards.models import CoinLedger, Reward
from apps.rewards.services import CoinService, RewardService
from apps.pets.models import PetSpecies
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )


class CreateRewardTests(_Base):
    def test_basic_create(self) -> None:
        with override_user(self.parent):
            result = reward_tools.create_reward(CreateRewardIn(
                name="Ice Cream",
                cost_coins=50,
                rarity="common",
            ))
        self.assertEqual(result["name"], "Ice Cream")
        self.assertEqual(
            Reward.objects.filter(name="Ice Cream").count(), 1,
        )

    def test_duplicate_name_rejected(self) -> None:
        Reward.objects.create(name="Exists", cost_coins=10)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.create_reward(CreateRewardIn(
                name="Exists", cost_coins=20,
            ))

    def test_child_cannot_create(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            reward_tools.create_reward(CreateRewardIn(
                name="Sneaky", cost_coins=1,
            ))

    def test_digital_item_requires_slug(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.create_reward(CreateRewardIn(
                name="Bare Digital",
                cost_coins=50,
                fulfillment_kind="digital_item",
                # no item_definition_slug
            ))

    def test_digital_item_with_slug_links(self) -> None:
        item = ItemDefinition.objects.create(
            slug="gold-frame",
            name="Gold Frame",
            icon="🖼️",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
        )
        with override_user(self.parent):
            result = reward_tools.create_reward(CreateRewardIn(
                name="Gold Frame Shop",
                cost_coins=500,
                fulfillment_kind="digital_item",
                item_definition_slug="gold-frame",
            ))
        reward = Reward.objects.get(pk=result["id"])
        self.assertEqual(reward.item_definition_id, item.id)

    def test_unknown_item_slug_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.create_reward(CreateRewardIn(
                name="Bad Link",
                cost_coins=1,
                fulfillment_kind="digital_item",
                item_definition_slug="does-not-exist",
            ))


class UpdateRewardTests(_Base):
    def test_partial_update(self) -> None:
        reward = Reward.objects.create(name="R", cost_coins=10)
        with override_user(self.parent):
            reward_tools.update_reward(UpdateRewardIn(
                reward_id=reward.id,
                description="now with sprinkles",
                cost_coins=25,
            ))
        reward.refresh_from_db()
        self.assertEqual(reward.cost_coins, 25)
        self.assertIn("sprinkles", reward.description)

    def test_clear_stock_sets_unlimited(self) -> None:
        reward = Reward.objects.create(name="R", cost_coins=10, stock=3)
        with override_user(self.parent):
            reward_tools.update_reward(UpdateRewardIn(
                reward_id=reward.id, clear_stock=True,
            ))
        reward.refresh_from_db()
        self.assertIsNone(reward.stock)

    def test_rename_conflict_rejected(self) -> None:
        a = Reward.objects.create(name="A", cost_coins=10)
        Reward.objects.create(name="B", cost_coins=10)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.update_reward(UpdateRewardIn(
                reward_id=a.id, name="B",
            ))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class SupportedRewardPublicationTests(TestCase):
    def setUp(self) -> None:
        household = make_family(
            "MCP catalog household", parents=[{"username": "catalog-parent"}],
            children=[{"username": "catalog-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        fox = PetSpecies.objects.create(slug="fox", name="Fox", icon="F", sprite_key="fox")
        self.egg = ItemDefinition.objects.create(
            slug="fox-egg", name="Fox egg", icon="E", item_type="egg", pet_species=fox,
        )
        self.accessory = ItemDefinition.objects.create(
            slug="pet-crown", name="Pet crown", icon="C", item_type="cosmetic_pet_accessory",
        )
        self.frame = ItemDefinition.objects.create(
            slug="frame-gold", name="Gold frame", icon="F", item_type="cosmetic_frame",
        )

    def test_unavailable_digital_and_both_offers_cannot_be_created_active(self) -> None:
        for item in (self.egg, self.accessory):
            for kind in ("digital_item", "both"):
                with self.subTest(item=item.slug, kind=kind), override_user(self.parent), self.assertRaises(MCPValidationError):
                    reward_tools.create_reward(CreateRewardIn(
                        name=f"{item.slug}-{kind}", cost_coins=5,
                        fulfillment_kind=kind, item_definition_slug=item.slug,
                    ))
        self.assertFalse(Reward.objects.filter(family=self.parent.family).exists())

    def test_inactive_unavailable_draft_is_retained_but_cannot_be_published(self) -> None:
        with override_user(self.parent):
            draft = reward_tools.create_reward(CreateRewardIn(
                name="Saved crown draft", cost_coins=5, is_active=False,
                fulfillment_kind="digital_item", item_definition_slug=self.accessory.slug,
            ))
            self.assertFalse(draft["catalog_available"])
            reward_tools.update_reward(UpdateRewardIn(reward_id=draft["id"], description="Saved keepsake"))
            with self.assertRaises(MCPValidationError):
                reward_tools.update_reward(UpdateRewardIn(reward_id=draft["id"], is_active=True, stock=10))
        saved = Reward.objects.get(pk=draft["id"])
        self.assertFalse(saved.is_active)
        self.assertIsNone(saved.stock)
        self.assertEqual(saved.description, "Saved keepsake")

    def test_replacing_an_active_supported_item_with_unavailable_item_saves_nothing(self) -> None:
        reward = Reward.objects.create(
            family=self.parent.family, name="Supported frame", cost_coins=5,
            fulfillment_kind="digital_item", item_definition=self.frame, stock=2,
        )
        before = Reward.objects.values().get(pk=reward.pk)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.update_reward(UpdateRewardIn(
                reward_id=reward.pk, item_definition_slug=self.egg.slug,
                name="Unsupported egg", cost_coins=50, stock=10,
            ))
        self.assertEqual(Reward.objects.values().get(pk=reward.pk), before)

    def test_clearing_a_digital_item_link_does_not_publish_an_unfulfillable_reward(self) -> None:
        reward = Reward.objects.create(
            family=self.parent.family, name="Linked frame", cost_coins=5,
            fulfillment_kind="digital_item", item_definition=self.frame,
        )
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.update_reward(UpdateRewardIn(reward_id=reward.pk, clear_item_definition=True))
        reward.refresh_from_db()
        self.assertEqual(reward.item_definition_id, self.frame.pk)

    def test_real_world_offers_remain_authorable_with_an_unused_legacy_item_link(self) -> None:
        with override_user(self.parent):
            created = reward_tools.create_reward(CreateRewardIn(
                name="Family outing", cost_coins=10, item_definition_slug=self.accessory.slug,
            ))
            changed = reward_tools.update_reward(UpdateRewardIn(
                reward_id=created["id"], description="Choose a park", cost_coins=15,
            ))
        self.assertTrue(changed["catalog_available"])
        self.assertEqual(changed["fulfillment_kind"], "real_world")
        self.assertEqual(changed["cost_coins"], 15)

    def test_retiring_unavailable_offer_preserves_pending_approval_and_credits_once(self) -> None:
        reward = Reward.objects.create(
            family=self.parent.family, name="Previously offered crown", cost_coins=20,
            fulfillment_kind="digital_item", item_definition=self.accessory, stock=2,
        )
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.ADJUSTMENT)
        # Issue the real pending receipt under the previous synthetic catalog.
        # The production policy applies again before retirement and approval.
        previous_policy = {"schema_version": 1, "pets": [], "potion_slugs": [], "disabled_item_types": []}
        with override_settings(RPG_ASSET_SUPPORT_POLICY=previous_policy), override_user(self.child):
            receipt = reward_tools.request_redemption(RequestRedemptionIn(request_id=uuid4(), reward_id=reward.pk))
        with override_user(self.parent):
            retired = reward_tools.update_reward(UpdateRewardIn(reward_id=reward.pk, is_active=False))
            self.assertFalse(retired["is_active"])
            for _attempt in range(2):
                approved = reward_tools.approve_redemption(DecideRedemptionIn(redemption_id=receipt["id"]))
                self.assertEqual(approved["status"], "fulfilled")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.accessory).quantity, 1)
        self.assertEqual(CoinService.get_balance(self.child), 80)
        reward.refresh_from_db()
        self.assertFalse(reward.is_active)
        self.assertEqual(reward.stock, 1)


class DeleteRewardTests(_Base):
    def test_delete_unused_reward(self) -> None:
        reward = Reward.objects.create(name="Disposable", cost_coins=1)
        with override_user(self.parent):
            result = reward_tools.delete_reward(
                DeleteRewardIn(reward_id=reward.id),
            )
        self.assertTrue(result["deleted"])

    def test_cannot_delete_with_redemption_history(self) -> None:
        reward = Reward.objects.create(name="Used", cost_coins=10)
        CoinService.award_coins(
            self.child, 100, CoinLedger.Reason.ADJUSTMENT, description="seed",
        )
        RewardService.request_redemption(self.child, reward)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.delete_reward(DeleteRewardIn(reward_id=reward.id))


class AdjustCoinsTests(_Base):
    def test_grant_coins_updates_balance(self) -> None:
        with override_user(self.parent):
            result = reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=50,
                description="weekly bonus",
            ))
        self.assertEqual(result["new_balance"], 50)

    def test_revoke_goes_through_spend(self) -> None:
        CoinService.award_coins(
            self.child, 100, CoinLedger.Reason.ADJUSTMENT, description="seed",
        )
        with override_user(self.parent):
            result = reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=-30, description="late chore",
            ))
        self.assertEqual(result["new_balance"], 70)

    def test_zero_amount_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=0, description="noop",
            ))

    def test_child_cannot_adjust(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=100, description="self-grant",
            ))
