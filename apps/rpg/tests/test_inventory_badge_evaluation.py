"""Inventory mutations recognize their badges inside the source award transaction."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.availability import BadgeGoalAvailability
from apps.achievements.criteria import _cosmetic_set_owned
from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.quests.goals import ingest_activity
from apps.quests.models import ChallengeOccurrence, Quest, QuestDefinition, QuestRewardItem
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger, Reward
from apps.rewards.services import CoinService, RewardService
from apps.rpg.constants import TriggerType
from apps.rpg.content.validation import validate_content
from apps.rpg.inventory import grant_item
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, CosmeticService, DropService
from config.tests.factories import make_family


class InventoryBadgeEvaluationTests(TestCase):
    def setUp(self):
        family = make_family(
            "Inventory badge household", parents=[{"username": "inventory-parent"}],
            children=[{"username": "inventory-child"}, {"username": "inventory-sibling"}],
        )
        self.parent, self.child, self.sibling = family.parents[0], *family.children
        category = SkillCategory.objects.create(name="Inventory badge skills")
        self.skill = Skill.objects.create(name="Persistence", category=category)
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=100, level=1)
        self.bonus = ItemDefinition.objects.create(
            slug="inventory-badge-snack", name="Badge snack", item_type="food",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def give(self, item, quantity=1):
        return UserInventory.objects.create(user=self.child, item=item, quantity=quantity)

    def consumable(self, effect, **metadata):
        return ItemDefinition.objects.create(
            slug=f"inventory-{effect}", name=effect, item_type="consumable",
            metadata={"effect": effect, **metadata},
        )

    def badge(self, name, criterion, value, *, xp=0):
        return Badge.objects.create(
            name=name, criteria_type=criterion, criteria_value=value,
            xp_bonus=xp, award_coins=False,
        )

    def seed_badge_drop(self, item=None):
        DropTable.objects.create(trigger_type=TriggerType.BADGE_EARNED, item=item or self.bonus)

    def assert_badge_once(self, badge, *, bonus_drops=1):
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type=TriggerType.BADGE_EARNED).count(), bonus_drops)
        self.assertFalse(UserBadge.objects.filter(user=self.sibling).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.sibling).exists())

    def collection(self):
        pieces = [ItemDefinition.objects.create(
            slug=slug, name=slug, item_type=kind, rarity=rarity,
            metadata={"theme": "hyrule"} if kind == "cosmetic_theme" else {},
        ) for slug, kind, rarity in (
            ("inventory-set-frame", "cosmetic_frame", "common"),
            ("inventory-set-cover", "cosmetic_theme", "common"),
            ("inventory-set-title", "cosmetic_title", "uncommon"),
        )]
        for piece in pieces[:2]:
            self.give(piece)
        badge = self.badge("Finished collection", "cosmetic_set_owned", {"slugs": [piece.slug for piece in pieces]})
        self.seed_badge_drop()
        return pieces[-1], badge

    def quest(self, item, *, system=False):
        definition = QuestDefinition.objects.create(
            name="Inventory promise", description="Earn a collection piece",
            quest_type="collection", target_value=1, is_system=system,
            created_by=None if system else self.parent,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestRewardItem.objects.create(quest_definition=definition, item=item)
        return definition

    def authored_mixed_collection(self):
        box = self.consumable("mystery_box")
        definition = {
            "name": "Authored box and snack collection",
            "description": "Own the box and its snack together",
            "icon": "A", "criteria_type": "cosmetic_set_owned",
            "criteria_value": {"slugs": [box.slug, self.bonus.slug]},
            "xp_bonus": 0, "rarity": "common",
        }
        # Both supported authoring surfaces permit any item slug in this set.
        validate_content({"badges": {"badges": [definition]}}, strict=True)
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        author = APIClient()
        author.force_authenticate(self.parent)
        response = author.post("/api/badges/", definition, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        badge = Badge.objects.get(name=definition["name"])
        self.assertTrue(BadgeGoalAvailability(self.child).is_available(badge))
        self.give(box)
        return box, badge

    def test_first_streak_freeze_use_api_immediately_pays_frozen_in_time_once(self):
        freeze = self.consumable("streak_freeze", duration_days=1)
        self.give(freeze, 2)
        badge = self.badge("Frozen in Time", "streak_freeze_used", {"count": 1}, xp=20)
        self.seed_badge_drop()

        response = self.client.post(f"/api/inventory/{freeze.pk}/use/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_badge_once(badge)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 120)
        response = self.client.post(f"/api/inventory/{freeze.pk}/use/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_badge_once(badge)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 120)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).streak_freezes_used, 2)

    def test_fifth_distinct_consumable_effect_immediately_pays_alchemist_once(self):
        profile = self.child.character_profile
        profile.consumable_effects_used = ["streak_freeze", "xp_boost", "coin_boost", "drop_boost"]
        profile.save(update_fields=["consumable_effects_used"])
        tonic = self.consumable("growth_tonic", feeds=3)
        self.give(tonic, 2)
        badge = self.badge("Alchemist", "consumable_variety", {"count": 5}, xp=80)
        self.seed_badge_drop()

        ConsumableService.use(self.child, tonic.pk)
        self.assert_badge_once(badge)
        ConsumableService.use(self.child, tonic.pk)
        self.assert_badge_once(badge)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 180)
        profile.refresh_from_db()
        self.assertEqual(len(profile.consumable_effects_used), 5)

    def test_last_consumable_unit_keeps_same_item_replacement_from_inventory_badge(self):
        freeze = self.consumable("streak_freeze", duration_days=1)
        self.give(freeze)
        badge = self.badge("Frozen in Time", "streak_freeze_used", {"count": 1})
        self.seed_badge_drop(freeze)

        ConsumableService.use(self.child, freeze.pk)

        self.assert_badge_once(badge)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=freeze).quantity, 1)
        ConsumableService.use(self.child, freeze.pk)
        self.assert_badge_once(badge)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=freeze).exists())

    def test_mystery_box_api_does_not_award_collection_from_consumed_last_box(self):
        box, badge = self.authored_mixed_collection()

        with patch("apps.rpg.services.random.choices", return_value=[self.bonus]):
            response = self.client.post(f"/api/inventory/{box.pk}/use/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["detail"]["granted_item_id"], self.bonus.pk)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=box).exists())
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.bonus).quantity, 1)
        self.assertFalse(_cosmetic_set_owned(self.child, badge.criteria_value))
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS).exists())

    def test_non_consuming_grant_awards_supported_mixed_collection_once(self):
        box, badge = self.authored_mixed_collection()

        grant_item(self.child, self.bonus)

        self.assertEqual(UserInventory.objects.get(user=self.child, item=box).quantity, 1)
        self.assertTrue(_cosmetic_set_owned(self.child, badge.criteria_value))
        self.assert_badge_once(badge, bonus_drops=0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS).count(), 1)
        grant_item(self.child, self.bonus)
        self.assert_badge_once(badge, bonus_drops=0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS).count(), 1)

    def test_failed_mystery_box_use_and_retry_leave_inventory_evaluation_available(self):
        box, badge = self.authored_mixed_collection()
        apply_effect = ConsumableService._apply_effect

        def fail_after_grant(profile, effect, item):
            apply_effect(profile, effect, item)
            raise RuntimeError("after mystery box grant")

        with patch("apps.rpg.services.random.choices", return_value=[self.bonus]):
            with patch.object(ConsumableService, "_apply_effect", side_effect=fail_after_grant):
                with self.assertRaisesRegex(RuntimeError, "after mystery box grant"):
                    ConsumableService.use(self.child, box.pk)

            self.assertEqual(UserInventory.objects.get(user=self.child, item=box).quantity, 1)
            self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.bonus).exists())
            self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
            self.assertFalse(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS).exists())
            self.assertEqual(CharacterProfile.objects.get(user=self.child).consumable_effects_used, [])

            ConsumableService.use(self.child, box.pk)

        self.assertFalse(UserInventory.objects.filter(user=self.child, item=box).exists())
        self.assertFalse(_cosmetic_set_owned(self.child, badge.criteria_value))
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        # A later independent qualifying grant must still evaluate normally.
        grant_item(self.child, box)
        self.assertTrue(_cosmetic_set_owned(self.child, badge.criteria_value))
        self.assert_badge_once(badge, bonus_drops=0)

    def test_random_drop_recognizes_last_collection_piece_before_returning(self):
        piece, badge = self.collection()
        DropTable.objects.create(trigger_type=TriggerType.CLOCK_OUT, item=piece)

        with patch("apps.rpg.services.random.random", return_value=0):
            drops = DropService.process_drops(self.child, TriggerType.CLOCK_OUT)

        self.assertEqual(drops[0]["item_id"], piece.pk)
        self.assert_badge_once(badge)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=piece).quantity, 1)

    def test_lucky_dip_recognizes_its_last_collection_piece(self):
        piece, badge = self.collection()
        dip = self.consumable("lucky_dip")
        self.give(dip)

        result = ConsumableService.use(self.child, dip.pk)

        self.assertEqual(result["detail"]["granted_item_id"], piece.pk)
        self.assert_badge_once(badge)

    def test_legacy_quest_items_recognize_last_collection_piece_once(self):
        piece, badge = self.collection()
        definition = self.quest(piece)
        quest = QuestService.start_quest(self.child, definition.pk)

        result = QuestService.record_progress(self.child, "chore_complete")

        self.assertTrue(result["completed"])
        self.assert_badge_once(badge)
        QuestService._complete_quest(quest, self.child)
        self.assert_badge_once(badge)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=piece).quantity, 1)

    def test_automatic_quest_items_recognize_last_collection_piece_once(self):
        piece, badge = self.collection()
        definition = self.quest(piece, system=True)

        ingest_activity(self.child, "chore_complete", "saved-chore", "chore_complete")

        self.assert_badge_once(badge)
        self.assertEqual(ChallengeOccurrence.objects.get(goal__catalog_definition=definition).status, "completed")
        ingest_activity(self.child, "chore_complete", "saved-chore", "chore_complete")
        self.assert_badge_once(badge)

    def test_expedition_claim_recognizes_last_collection_piece_without_repeat_credit(self):
        piece, badge = self.collection()
        species = PetSpecies.objects.create(name="Saved creature", slug="inventory-saved-creature")
        potion = PotionType.objects.create(name="Base", slug="base", color_hex="#ffffff")
        mount = UserMount.objects.create(user=self.child, species=species, potion=potion)
        trip = MountExpedition.objects.create(
            mount=mount, tier="short", returns_at=timezone.now() - timedelta(seconds=1),
            loot={"coins": 10, "items": [{"item_id": piece.pk, "quantity": 1}]},
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = ExpeditionService.claim(self.child, trip.pk)

        self.assertTrue(result["freshly_claimed"])
        self.assert_badge_once(badge)
        self.assertFalse(ExpeditionService.claim(self.child, trip.pk)["freshly_claimed"])
        self.assert_badge_once(badge)

    def test_digital_shop_approval_recognizes_saved_last_piece_once(self):
        piece, badge = self.collection()
        CoinService.award_coins(self.child, 50, CoinLedger.Reason.ADJUSTMENT)
        offer = Reward.objects.create(
            family=self.child.family, name="Collection piece", cost_coins=5,
            requires_parent_approval=True, fulfillment_kind="digital_item", item_definition=piece,
        )
        redemption = RewardService.request_redemption(self.child, offer)
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())

        RewardService.approve(redemption, self.parent)

        self.assert_badge_once(badge)
        RewardService.approve(redemption, self.parent)
        self.assert_badge_once(badge)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=piece).quantity, 1)

    def test_new_starter_cover_recognizes_last_collection_piece_once(self):
        frame = ItemDefinition.objects.create(slug="starter-set-frame", name="Starter frame", item_type="cosmetic_frame")
        title = ItemDefinition.objects.create(slug="starter-set-title", name="Starter title", item_type="cosmetic_title")
        cover = ItemDefinition.objects.create(
            slug="starter-set-cover", name="Starter cover", item_type="cosmetic_theme", metadata={"theme": "hyrule"},
        )
        self.give(frame)
        self.give(title)
        badge = self.badge("Starter collection", "cosmetic_set_owned", {"slugs": [frame.slug, title.slug, cover.slug]})
        self.seed_badge_drop()

        CosmeticService.grant_starter_cover(self.child, slug=cover.slug)

        self.assert_badge_once(badge)
        CosmeticService.grant_starter_cover(self.child, slug=cover.slug)
        self.assert_badge_once(badge)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=cover).quantity, 1)

    def test_inventory_badge_drop_chain_drains_finitely_without_activity_replay(self):
        piece, collection_badge = self.collection()
        DropTable.objects.filter(trigger_type=TriggerType.BADGE_EARNED).delete()
        self.seed_badge_drop(piece)
        freeze = self.consumable("streak_freeze", duration_days=1)
        self.give(freeze)
        frozen = self.badge("Frozen in Time", "streak_freeze_used", {"count": 1})

        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game_loop:
            ConsumableService.use(self.child, freeze.pk)

        game_loop.assert_not_called()
        self.assert_badge_once(frozen, bonus_drops=2)
        self.assert_badge_once(collection_badge, bonus_drops=2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=piece).quantity, 1)
        self.assertIsNone(CharacterProfile.objects.get(user=self.child).last_active_date)

    def test_failed_inventory_badge_drop_rolls_back_consumable_and_retries_once(self):
        freeze = self.consumable("streak_freeze", duration_days=1)
        self.give(freeze)
        badge = self.badge("Frozen in Time", "streak_freeze_used", {"count": 1}, xp=20)
        self.seed_badge_drop()

        with patch.object(DropLog.objects, "create", side_effect=RuntimeError("inventory badge drop failed")):
            with self.assertRaisesRegex(RuntimeError, "inventory badge drop failed"):
                ConsumableService.use(self.child, freeze.pk)

        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertEqual(CharacterProfile.objects.get(user=self.child).streak_freezes_used, 0)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=freeze).quantity, 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 100)
        self.assertFalse(DropLog.objects.exists())
        ConsumableService.use(self.child, freeze.pk)
        self.assert_badge_once(badge)

    def test_failed_collection_badge_drop_rolls_back_quest_items_and_completion(self):
        piece, badge = self.collection()
        definition = self.quest(piece)
        quest = QuestService.start_quest(self.child, definition.pk)

        with patch.object(DropLog.objects, "create", side_effect=RuntimeError("inventory badge drop failed")):
            with self.assertRaisesRegex(RuntimeError, "inventory badge drop failed"):
                QuestService.record_progress(self.child, "chore_complete")

        quest.refresh_from_db()
        self.assertEqual((quest.status, quest.current_progress), (Quest.Status.ACTIVE, 0))
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=piece).exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        QuestService.record_progress(self.child, "chore_complete")
        self.assert_badge_once(badge)
