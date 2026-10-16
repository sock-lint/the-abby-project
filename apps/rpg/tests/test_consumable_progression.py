"""Consumable receipts must correspond to saved companion and skill progress."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory, SkillPrerequisite, SkillProgress, UserBadge
from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import PetService
from apps.projects.models import User
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CompanionConsumableProgressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        cls.child = User.objects.create_user(username="consumable-child", role="child")
        cls.chick = PetSpecies.objects.get(slug="chick")
        cls.base = PotionType.objects.get(slug="base")
        cls.food = ItemDefinition.objects.get(slug="food-birdseed")

    def pet(self, growth=0, **kwargs):
        return UserPet.objects.create(
            user=self.child, species=self.chick, potion=self.base,
            growth_points=growth, is_active=True, **kwargs,
        )

    def give(self, slug, quantity=1):
        item = ItemDefinition.objects.get(slug=slug)
        UserInventory.objects.create(user=self.child, item=item, quantity=quantity)
        return item

    def assert_boosted_feed(self, tonic_slug, initial_feeds):
        pet = self.pet()
        tonic = self.give(tonic_slug)
        self.give("food-birdseed", 2)
        ConsumableService.use(self.child, tonic.pk)
        for expected_remaining in (initial_feeds - 1, initial_feeds - 2):
            result = PetService.feed_pet(self.child, pet.pk, self.food.pk)
            self.assertEqual(result["growth_added"], 30)
            self.assertEqual(
                CharacterProfile.objects.get(user=self.child).pet_growth_boost_remaining,
                expected_remaining,
            )
        pet.refresh_from_db()
        self.assertEqual(pet.growth_points, 60)
        self.assertIsNotNone(pet.last_fed_at)
        self.assertEqual(pet.consumable_growth_today, 0)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=tonic).exists())

    def test_authored_growth_tonic_doubles_and_consumes_following_feeds(self):
        self.assert_boosted_feed("growth-tonic", 3)

    def test_authored_morale_tonic_doubles_and_consumes_following_feeds(self):
        self.assert_boosted_feed("pet-morale-tonic", 5)

    def test_last_boost_doubles_neutral_feed_then_expires(self):
        pet = self.pet()
        neutral = ItemDefinition.objects.create(name="Neutral food", item_type="food")
        UserInventory.objects.create(user=self.child, item=neutral, quantity=2)
        CharacterProfile.objects.filter(user=self.child).update(pet_growth_boost_remaining=1)
        first = PetService.feed_pet(self.child, pet.pk, neutral.pk)
        second = PetService.feed_pet(self.child, pet.pk, neutral.pk)
        self.assertEqual((first["growth_added"], second["growth_added"]), (10, 5))
        self.assertEqual(CharacterProfile.objects.get(user=self.child).pet_growth_boost_remaining, 0)

    def test_failed_feed_keeps_boost_and_food(self):
        pet = self.pet()
        self.give("food-birdseed")
        CharacterProfile.objects.filter(user=self.child).update(pet_growth_boost_remaining=1)
        with patch.object(UserPet, "save", side_effect=RuntimeError("storage failed")):
            with self.assertRaisesRegex(RuntimeError, "storage failed"):
                PetService.feed_pet(self.child, pet.pk, self.food.pk)
        pet.refresh_from_db()
        self.assertEqual(pet.growth_points, 0)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).pet_growth_boost_remaining, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 1)

    def test_authored_feast_evolves_at_threshold_and_creates_one_mount(self):
        pet = self.pet(90)
        feast = self.give("feast-platter")
        result = ConsumableService.use(self.child, feast.pk)
        pet.refresh_from_db()
        self.assertEqual((pet.growth_points, pet.evolved_to_mount), (100, True))
        self.assertEqual(UserMount.objects.filter(user=self.child, species=self.chick, potion=self.base).count(), 1)
        self.assertEqual(result["detail"]["growth_per_pet_applied"], [10])

    def test_feast_uses_evolution_chronicle_and_notification_hooks(self):
        self.pet(90)
        feast = self.give("feast-platter")
        with (
            patch("apps.chronicle.services.ChronicleService.record_first") as chronicle,
            patch("apps.notifications.services.notify") as child_notice,
            patch("apps.notifications.services.notify_parents") as parent_notice,
        ):
            ConsumableService.use(self.child, feast.pk)
        chronicle.assert_called_once()
        self.assertEqual(chronicle.call_args.kwargs["event_slug"], "first_mount_evolved")
        child_notice.assert_called_once()
        parent_notice.assert_called_once()

    def test_feast_mount_failure_rolls_back_growth_cap_and_inventory(self):
        pet = self.pet(90)
        feast = self.give("feast-platter")
        with patch.object(UserMount.objects, "get_or_create", side_effect=RuntimeError("mount failed")):
            with self.assertRaisesRegex(RuntimeError, "mount failed"):
                ConsumableService.use(self.child, feast.pk)
        pet.refresh_from_db()
        self.assertEqual((pet.growth_points, pet.evolved_to_mount, pet.consumable_growth_today), (90, False, 0))
        self.assertEqual(UserInventory.objects.get(user=self.child, item=feast).quantity, 1)

    def test_growth_surge_uses_same_evolution_hooks(self):
        self.pet(70)
        surge = self.give("pet-evolution-accelerator")
        with patch("apps.chronicle.services.ChronicleService.record_first") as chronicle:
            ConsumableService.use(self.child, surge.pk)
        chronicle.assert_called_once()
        self.assertEqual(chronicle.call_args.kwargs["event_slug"], "first_mount_evolved")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SkillTonicProgressionTests(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="skill-tonic-child", role="child")
        category = SkillCategory.objects.create(name="Tonic skills")
        self.leader = Skill.objects.create(category=category, name="Practice")
        self.dependent = Skill.objects.create(category=category, name="Advanced practice", is_locked_by_default=True)
        SkillPrerequisite.objects.create(skill=self.dependent, required_skill=self.leader, required_level=1)
        self.progress = SkillProgress.objects.create(user=self.child, skill=self.leader, xp_points=90)
        SkillProgress.objects.create(user=self.child, skill=self.dependent, unlocked=False)
        self.item = ItemDefinition.objects.create(
            name="Skill tonic", item_type="consumable", metadata={"effect": "skill_tonic", "xp": 50},
        )
        UserInventory.objects.create(user=self.child, item=self.item, quantity=1)
        self.badge = Badge.objects.create(
            name="First practice level", criteria_type="skill_level_reached", criteria_value={"level": 1},
            xp_bonus=0, award_coins=False,
        )

    def test_tonic_level_threshold_unlocks_dependent_skill_and_badge(self):
        result = ConsumableService.use(self.child, self.item.pk)
        self.progress.refresh_from_db()
        self.assertEqual((self.progress.xp_points, self.progress.level), (140, 1))
        self.assertTrue(SkillProgress.objects.get(user=self.child, skill=self.dependent).unlocked)
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=self.badge).exists())
        self.assertEqual(result["detail"]["xp_awarded"], 50)

    def test_tonic_uses_standard_xp_boost_and_logs_confirmed_award(self):
        from apps.activity.models import ActivityEvent

        CharacterProfile.objects.filter(user=self.child).update(xp_boost_expires_at=timezone.now() + timedelta(hours=1))
        result = ConsumableService.use(self.child, self.item.pk)
        self.progress.refresh_from_db()
        self.assertEqual((result["detail"]["xp_awarded"], self.progress.xp_points), (100, 190))
        event = ActivityEvent.objects.get(subject=self.child, event_type="award.xp")
        self.assertEqual((event.xp_delta, event.context["extras"]["xp_base"]), (100, 50))

    def test_tonic_badge_failure_rolls_back_xp_unlocks_and_item(self):
        with patch("apps.achievements.services.BadgeService.evaluate_badges", side_effect=RuntimeError("badge failed")):
            with self.assertRaisesRegex(RuntimeError, "badge failed"):
                ConsumableService.use(self.child, self.item.pk)
        self.progress.refresh_from_db()
        self.assertEqual((self.progress.xp_points, self.progress.level), (90, 0))
        self.assertFalse(SkillProgress.objects.filter(user=self.child, skill=self.dependent, unlocked=True).exists())
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)
