"""Pet milestones pay their existing badges in the successful care transaction."""
from unittest.mock import patch

from django.db import transaction
from django.db.models import Sum
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.notifications.models import Notification, NotificationType
from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import PetService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    COINS_PER_BADGE_RARITY={"common": 7, "uncommon": 11},
    RPG_ASSET_SUPPORT_POLICY=None,
)
class PetBadgeMilestoneTests(TestCase):
    def setUp(self):
        household = make_family("Pet milestones", children=[
            {"username": "pet-milestone-child"}, {"username": "pet-milestone-sibling"},
        ])
        self.child, self.sibling = household.children
        self.other = make_family("Other pet milestones", children=[{"username": "other-pet-child"}]).children[0]
        self.species = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick", icon="C")
        self.potion = PotionType.objects.create(slug="base", name="Base")
        self.species.available_potions.add(self.potion)
        self.egg = ItemDefinition.objects.create(
            slug="chick-egg", name="Chick Egg", item_type="egg",
            pet_species=self.species, metadata={"species": "chick"},
        )
        self.potion_item = ItemDefinition.objects.create(
            slug="base-potion", name="Base Potion", item_type="potion",
            potion_type=self.potion, metadata={"variant": "base"},
        )
        self.food = ItemDefinition.objects.create(name="Birdseed", item_type="food", food_species=self.species)
        category = SkillCategory.objects.create(name="Synthetic pet care")
        skill = Skill.objects.create(category=category, name="Synthetic care skill")
        self.progress = SkillProgress.objects.create(user=self.child, skill=skill, xp_points=100, level=1, unlocked=True)

    def badge(self, kind, name="Pet milestone", xp=50):
        return Badge.objects.create(
            name=name, description="Synthetic existing milestone", criteria_type=kind,
            criteria_value={"count": 1}, xp_bonus=xp,
            rarity="common" if kind == "pets_hatched" else "uncommon",
        )

    def give(self, item, quantity=1):
        return UserInventory.objects.create(user=self.child, item=item, quantity=quantity)

    def ready_pet(self, growth=90, species=None):
        return UserPet.objects.create(
            user=self.child, species=species or self.species, potion=self.potion,
            growth_points=growth, is_active=True,
        )

    def assert_award(self, badge, xp, coins):
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100 + xp)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).aggregate(total=Sum("amount"))["total"], coins)
        self.assertFalse(UserBadge.objects.filter(user__in=[self.sibling, self.other]).exists())

    def assert_badge_notification(self, badge):
        notes = Notification.objects.filter(user=self.child, notification_type=NotificationType.BADGE_EARNED,
                                            title=f"Badge earned: {badge.name}")
        self.assertEqual(notes.count(), 1)
        self.assertEqual(notes.get().link, "/atlas?tab=badges")
        self.assertFalse(Notification.objects.filter(user__in=[self.sibling, self.other],
                                                     notification_type=NotificationType.BADGE_EARNED).exists())

    def test_hatching_awards_first_pet_and_meta_badges_immediately_once_for_its_owner(self):
        hatch = self.badge("pets_hatched", "A first hatch", xp=25)
        meta = Badge.objects.create(
            name="Z first badge", description="Synthetic collector", criteria_type="badges_earned_count",
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False,
        )
        # Eligible saved pets in both families must not be awarded by this request.
        for owner in (self.sibling, self.other):
            UserPet.objects.create(user=owner, species=self.species, potion=self.potion)
        egg, potion = self.give(self.egg, 2), self.give(self.potion_item, 2)

        pet = PetService.hatch_pet(self.child, self.egg.pk, self.potion_item.pk)

        self.assertEqual(pet.growth_points, 0)
        self.assert_award(hatch, xp=25, coins=7)
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=meta).exists())
        self.assert_badge_notification(hatch)
        self.assert_badge_notification(meta)
        with self.assertRaisesRegex(ValueError, "already have"):
            PetService.hatch_pet(self.child, self.egg.pk, self.potion_item.pk)
        BadgeService.evaluate_badges(self.child, scopes={"pet", "badges"})
        self.assert_award(hatch, xp=25, coins=7)
        self.assert_badge_notification(hatch)
        for inventory in (egg, potion):
            inventory.refresh_from_db()
            self.assertEqual(inventory.quantity, 1)

    def test_food_evolution_awards_existing_mount_badge_without_another_activity(self):
        badge = self.badge("mounts_evolved")
        pet = self.ready_pet()
        food = self.give(self.food, 2)

        result = PetService.feed_pet(self.child, pet.pk, self.food.pk)

        self.assertTrue(result["evolved"])
        self.assert_award(badge, xp=50, coins=11)
        self.assert_badge_notification(badge)
        with self.assertRaisesRegex(ValueError, "already evolved"):
            PetService.feed_pet(self.child, pet.pk, self.food.pk)
        self.assert_award(badge, xp=50, coins=11)
        self.assert_badge_notification(badge)
        food.refresh_from_db()
        self.assertEqual(food.quantity, 1)

    def assert_consumable_evolution(self, effect):
        badge = self.badge("mounts_evolved")
        self.ready_pet()
        item = ItemDefinition.objects.create(
            name=f"Synthetic {effect}", item_type="consumable", metadata={"effect": effect, "growth": 10},
        )
        self.give(item)

        ConsumableService.use(self.child, item.pk)

        self.assertEqual(UserMount.objects.filter(user=self.child).count(), 1)
        self.assert_award(badge, xp=50, coins=11)
        self.assert_badge_notification(badge)

    def test_growth_surge_evolution_awards_mount_badge(self):
        self.assert_consumable_evolution("growth_surge")

    def test_feast_evolution_awards_mount_badge(self):
        self.assert_consumable_evolution("feast_platter")

    def test_passive_evolution_awards_mount_badge_once(self):
        badge = self.badge("mounts_evolved")
        companion = PetSpecies.objects.create(slug="companion", name="Saved Companion", icon="P")
        self.ready_pet(growth=98, species=companion)

        result = PetService.auto_grow_companions(self.child)

        self.assertEqual(result["evolved"], 1)
        self.assert_award(badge, xp=50, coins=11)
        self.assert_badge_notification(badge)
        self.assertEqual(PetService.auto_grow_companions(self.child)["evolved"], 0)
        self.assert_award(badge, xp=50, coins=11)
        self.assert_badge_notification(badge)

    def test_foreign_pet_care_cannot_grant_growth_or_badges_to_either_account(self):
        badge = self.badge("mounts_evolved")
        pet = UserPet.objects.create(user=self.other, species=self.species, potion=self.potion, growth_points=90)
        food = self.give(self.food)
        client = APIClient()
        client.force_authenticate(self.child)

        response = client.post(f"/api/pets/{pet.pk}/feed/", {"food_item_id": self.food.pk}, format="json")

        self.assertEqual(response.status_code, 400)
        pet.refresh_from_db()
        food.refresh_from_db()
        self.assertEqual((pet.growth_points, food.quantity), (90, 1))
        self.assertFalse(UserBadge.objects.filter(badge=badge).exists())
        self.assertFalse(UserMount.objects.exists())

    def test_hatch_badge_payout_failure_rolls_back_ingredients_pet_xp_and_badge_then_retries(self):
        badge = self.badge("pets_hatched", xp=25)
        self.give(self.egg)
        self.give(self.potion_item)
        with patch.object(BadgeService, "_award_badge_coins", side_effect=RuntimeError("payout unavailable")):
            with self.assertRaisesRegex(RuntimeError, "payout unavailable"):
                PetService.hatch_pet(self.child, self.egg.pk, self.potion_item.pk)
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())
        self.assertEqual(UserInventory.objects.filter(user=self.child).count(), 2)
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(Notification.objects.filter(user=self.child, notification_type=NotificationType.BADGE_EARNED).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)

        PetService.hatch_pet(self.child, self.egg.pk, self.potion_item.pk)

        self.assert_award(badge, xp=25, coins=7)
        self.assert_badge_notification(badge)

    def test_badge_notification_failure_keeps_the_successful_hatch_and_payout(self):
        badge = self.badge("pets_hatched", xp=25)
        self.give(self.egg)
        self.give(self.potion_item)
        with self.assertLogs("apps.pets.services", level="ERROR"), patch(
            "apps.notifications.services.notify", side_effect=RuntimeError("notification unavailable"),
        ):
            pet = PetService.hatch_pet(self.child, self.egg.pk, self.potion_item.pk)

        self.assertTrue(UserPet.objects.filter(pk=pet.pk, user=self.child).exists())
        self.assert_award(badge, xp=25, coins=7)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_badge_notification_push_waits_for_the_ownership_commit(self):
        badge = self.badge("pets_hatched", xp=25)
        self.give(self.egg)
        self.give(self.potion_item)
        with patch("apps.notifications.services._push_now") as push:
            with self.captureOnCommitCallbacks(execute=True):
                PetService.hatch_pet(self.child, self.egg.pk, self.potion_item.pk)
                self.assert_badge_notification(badge)
                push.assert_not_called()
            push.assert_called_once()
            self.assertEqual(push.call_args.args[0].notification_type, NotificationType.BADGE_EARNED)

    def test_later_transaction_rollback_discards_pet_badge_notification_and_push(self):
        self.badge("pets_hatched", xp=25)
        self.give(self.egg)
        self.give(self.potion_item)
        with patch("apps.notifications.services._push_now") as push:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaisesRegex(RuntimeError, "outer transaction failed"):
                    with transaction.atomic():
                        PetService.hatch_pet(self.child, self.egg.pk, self.potion_item.pk)
                        raise RuntimeError("outer transaction failed")
            push.assert_not_called()
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(Notification.objects.filter(user=self.child, notification_type=NotificationType.BADGE_EARNED).exists())
        self.assertEqual(UserInventory.objects.filter(user=self.child).count(), 2)

    def test_growth_badge_payout_failure_rolls_back_mount_food_and_xp_then_retries(self):
        badge = self.badge("mounts_evolved")
        pet = self.ready_pet()
        self.give(self.food)
        with patch.object(BadgeService, "_award_badge_coins", side_effect=RuntimeError("payout unavailable")):
            with self.assertRaisesRegex(RuntimeError, "payout unavailable"):
                PetService.feed_pet(self.child, pet.pk, self.food.pk)
        pet.refresh_from_db()
        self.assertEqual(pet.growth_points, 90)
        self.assertFalse(pet.evolved_to_mount)
        self.assertFalse(UserMount.objects.filter(user=self.child).exists())
        self.assertTrue(UserInventory.objects.filter(user=self.child, item=self.food, quantity=1).exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)

        PetService.feed_pet(self.child, pet.pk, self.food.pk)

        self.assert_award(badge, xp=50, coins=11)
