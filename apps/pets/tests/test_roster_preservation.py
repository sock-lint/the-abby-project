"""Generic pack loading preserves explicitly supplied synthetic saved data.

This disposable test database stands in for an existing household. It contains
all 17 earlier families and frozen promises; it reads no live database. The
default startup command separately resets the owner's retired catalog; these
tests exercise the non-destructive generic loader and acquisition reconciler.
"""
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillProgress, UserBadge
from apps.activity.models import ActivityEvent
from apps.chronicle.models import ChronicleEntry
from apps.payments.models import PaymentLedger
from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount, UserPet
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.quests.serializers import QuestDefinitionSerializer
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


LEGACY_SLUGS = (
    "wolf", "dragon", "fox", "owl", "cat", "bear", "phoenix", "unicorn",
    "clownling", "pondshell", "seafang", "ripplecoil", "drift-jelly",
    "deepkraken", "stallion", "archdragon", "companion",
)
FIXED_NOW = datetime(2026, 10, 16, 19, tzinfo=timezone.utc)
INITIAL_PACK = Path(settings.BASE_DIR) / "content/rpg/initial"


@override_settings(
    ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class RosterPreservationTests(APITestCase):
    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        # The current pack does not author earlier species. Supply the legacy
        # baseline explicitly, then exercise generic reloads independently of
        # the owner's separate default-command retirement/reset.
        ContentPack(INITIAL_PACK).load()
        household = make_family(
            "Synthetic retained roster", parents=[{"username": "roster-parent"}],
            children=[{"username": "roster-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.client.force_authenticate(self.child)
        self.base = PotionType.objects.get(slug="base")
        self.fire = PotionType.objects.get(slug="fire")
        self.eggs, self.foods, self.mounts = [], [], []
        self.saved_rewards = []
        quest = QuestDefinition.objects.create(
            name="Saved roster promise", quest_type="collection", target_value=1,
            description="Synthetic earlier promise", coin_reward=7,
        )
        self.quest = quest
        for index, slug in enumerate(LEGACY_SLUGS):
            species = PetSpecies.objects.create(
                slug=slug, name=slug.replace("-", " ").title(),
                sprite_key={"seafang": "tropical-fish", "ripplecoil": "eel", "drift-jelly": "jellyfish",
                            "deepkraken": "octopus", "stallion": "horse"}.get(slug, slug),
            )
            species.available_potions.add(self.base, self.fire)
            growth = (0, 49, 50, 99, 100)[index % 5]
            UserPet.objects.create(
                user=self.child, species=species, potion=self.base,
                name=f"Saved {slug}", growth_points=growth,
                evolved_to_mount=growth == 100, is_active=index == 0,
                last_fed_at=FIXED_NOW - timedelta(days=index + 1),
                consumable_growth_today=index, consumable_growth_date=FIXED_NOW.date(),
            )
            self.mounts.append(UserMount.objects.create(
                user=self.child, species=species, potion=self.fire,
                is_active=index == 0, last_bred_at=FIXED_NOW - timedelta(days=index + 2),
            ))
            egg = ItemDefinition.objects.create(
                slug=f"{slug}-egg", name=f"{species.name} Egg", icon="🥚",
                sprite_key="big-egg", item_type="egg", pet_species=species,
                metadata={"species": slug},
            )
            self.eggs.append(egg)
            UserInventory.objects.create(user=self.child, item=egg, quantity=index + 2)
            DropLog.objects.create(
                user=self.child, item=egg, trigger_type="chore_complete",
                quantity=index + 1, was_salvaged=index % 2 == 0,
            )
            DropTable.objects.create(item=egg, trigger_type="clock_out", weight=index + 2)
            food = ItemDefinition.objects.create(
                slug=f"saved-roster-food-{slug}", name=f"Saved {slug} food",
                item_type="food", food_species=species,
            )
            self.foods.append(food)
            reward = Reward.objects.create(
                family=household.family, name=f"Saved {slug} offer", cost_coins=21,
                fulfillment_kind="digital_item" if index % 2 == 0 else "both",
                item_definition=egg, stock=3,
            )
            self.saved_rewards.append(reward)
            QuestRewardItem.objects.create(quest_definition=quest, item=egg, quantity=index + 1)
        self.fire_item = ItemDefinition.objects.get(slug="fire-potion")
        UserInventory.objects.create(user=self.child, item=self.fire_item, quantity=11)
        DropTable.objects.create(item=self.fire_item, trigger_type="clock_out", weight=9)
        self.real_world = Reward.objects.create(
            family=household.family, name="Saved real-world outing", cost_coins=5,
            fulfillment_kind="real_world", item_definition=self.eggs[0],
        )
        self.pending = RewardRedemption.objects.create(
            user=self.child, reward=self.saved_rewards[0], coin_cost_snapshot=21,
        )
        CoinLedger.objects.create(user=self.child, amount=200, reason="adjustment")
        CoinLedger.objects.create(
            user=self.child, amount=-21, reason="redemption", redemption=self.pending,
        )
        CoinLedger.objects.create(
            user=self.child, amount=7, reason="daily_challenge",
            description="Synthetic already-paid saved goal",
        )
        PaymentLedger.objects.create(
            user=self.child, amount="12.50", entry_type="hourly",
            description="Synthetic previously earned project payment",
        )
        ActivityEvent.objects.create(
            actor=self.child, subject=self.child, category="award", event_type="saved.award",
            summary="Synthetic retained award", xp_delta=347, coins_delta=200,
        )
        ChronicleEntry.objects.create(
            user=self.child, kind="milestone", occurred_on=FIXED_NOW.date(),
            chapter_year=2026, title="Synthetic saved companion milestone",
            metadata={"species_slug": "wolf", "growth": 50},
        )
        skill = Skill.objects.order_by("pk").first()
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=347, level=2)
        badge = Badge.objects.create(
            name="Saved roster award", criteria_type="pet_species_owned", criteria_value={"count": 17},
        )
        UserBadge.objects.create(user=self.child, badge=badge)
        profile = CharacterProfile.objects.get(user=self.child)
        profile.level = 2
        profile.login_streak = 8
        saved_companion = UserPet.objects.get(user=self.child, species__slug="companion")
        profile.pending_companion_growth = [{
            "pet_id": saved_companion.pk, "new_growth": saved_companion.growth_points, "evolved": False,
        }]
        profile.save(update_fields=["level", "login_streak", "pending_companion_growth"])
        goal = ChallengeGoal.objects.create(
            user=self.child, family=household.family, created_by=self.parent,
            name="Saved egg goal", metric="count", target=1,
            timezone_name="America/Phoenix", starts_at=FIXED_NOW - timedelta(days=1),
            ends_at=FIXED_NOW + timedelta(days=6),
            reward_items=[{"item_id": self.eggs[0].pk, "quantity": 2}],
        )
        self.occurrence = ChallengeOccurrence.objects.create(
            goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
            snapshot={"name": goal.name, "items": [{"item_id": self.eggs[0].pk, "quantity": 2}]},
            progress=1, status="completed", completed_at=FIXED_NOW,
            awarded_at=FIXED_NOW, reward_receipt={"coins": 7, "items": []},
        )
        self.locked = MountExpedition.objects.create(
            mount=self.mounts[1], tier="short", started_at=FIXED_NOW - timedelta(hours=3),
            returns_at=FIXED_NOW - timedelta(hours=1),
            loot={"coins": 15, "items": [{
                "item_id": self.eggs[2].pk, "quantity": 2, "name": "Saved Fox Egg",
                "icon": "🥚", "rarity": "common", "item_type": "egg", "sprite_key": "egg",
            }]},
        )

    def saved_state(self):
        """Snapshot actual stored rows rather than recomputing catalog views."""
        models = (
            UserPet, UserMount, UserInventory, DropLog, RewardRedemption,
            QuestRewardItem, ChallengeGoal, ChallengeOccurrence, MountExpedition,
            CoinLedger, SkillProgress, UserBadge, CharacterProfile,
            PaymentLedger, ActivityEvent, ChronicleEntry,
        )
        return {
            model._meta.label: list(model.objects.order_by("pk").values()) for model in models
        } | {
            "legacy_species": list(PetSpecies.objects.filter(slug__in=LEGACY_SLUGS)
                                   .order_by("pk").values("pk", "slug")),
            "legacy_egg_links": list(ItemDefinition.objects.filter(pk__in=[egg.pk for egg in self.eggs])
                                     .order_by("pk").values("pk", "slug", "pet_species_id")),
            "food_links": list(ItemDefinition.objects.filter(item_type="food")
                               .order_by("pk").values("pk", "food_species_id")),
        }

    def reconcile(self, *, dry_run=False):
        output = StringIO()
        call_command("reconcile_companion_catalog", dry_run=dry_run, json=True, stdout=output)
        return json.loads(output.getvalue())

    def test_dry_run_changes_no_catalog_or_saved_rows_then_apply_and_reload_preserve_baseline(self):
        before = self.saved_state()
        all_offers = list(Reward.objects.order_by("pk").values())
        all_drops = list(DropTable.objects.order_by("pk").values())
        catalog = {model._meta.label: list(model.objects.order_by("pk").values())
                   for model in (PetSpecies, PotionType, ItemDefinition)}
        report = self.reconcile(dry_run=True)
        self.assertGreaterEqual(report["drops_removed"], 17)
        self.assertEqual(report["rewards_deactivated"], 17)
        self.assertGreaterEqual(report["retained_quest_reward_links"], 17)
        self.assertEqual(self.saved_state(), before)
        self.assertEqual(list(Reward.objects.order_by("pk").values()), all_offers)
        self.assertEqual(list(DropTable.objects.order_by("pk").values()), all_drops)
        self.assertEqual({model._meta.label: list(model.objects.order_by("pk").values())
                          for model in (PetSpecies, PotionType, ItemDefinition)}, catalog)

        self.reconcile()
        self.assertEqual(self.saved_state(), before)
        self.assertFalse(Reward.objects.filter(pk__in=[reward.pk for reward in self.saved_rewards], is_active=True).exists())
        self.real_world.refresh_from_db()
        self.assertTrue(self.real_world.is_active)
        # Fire is now supported art. It remains ineligible for random selection
        # independently of whether an old authored DropTable row is retained.
        retired = [egg.pk for egg in self.eggs]
        self.assertFalse(DropTable.objects.filter(item_id__in=retired).exists())
        self.assertEqual(self.reconcile()["drops_removed"], 0)
        self.assertEqual(self.reconcile()["rewards_deactivated"], 0)
        for _reload in range(2):
            ContentPack(INITIAL_PACK).load()
            self.assertEqual(self.saved_state(), before)
            self.assertFalse(DropTable.objects.filter(item_id__in=retired).exists())
            self.assertFalse(Reward.objects.filter(pk__in=[reward.pk for reward in self.saved_rewards], is_active=True).exists())
        stable = self.client.get("/api/pets/stable/").json()
        self.assertEqual((stable["total_pets"], stable["total_mounts"], stable["total_possible"]), (17, 17, 27))
        self.assertTrue(all(not pet["catalog_available"] for pet in stable["pets"]))
        self.assertEqual({pet["name"] for pet in stable["pets"]}, {f"Saved {slug}" for slug in LEGACY_SLUGS})

    def test_saved_redemption_and_prerolled_expedition_pay_original_promises_once_after_retirement(self):
        before = self.saved_state()
        self.reconcile()
        ContentPack(INITIAL_PACK).load()
        self.assertEqual(self.saved_state(), before)
        held_balance = CoinService.get_balance(self.child)
        egg_quantity = UserInventory.objects.get(user=self.child, item=self.eggs[0]).quantity
        RewardService.approve(self.pending, self.parent)
        RewardService.approve(self.pending, self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.eggs[0]).quantity, egg_quantity + 1)
        self.assertEqual(CoinService.get_balance(self.child), held_balance)
        self.pending.refresh_from_db()
        self.assertEqual((self.pending.status, self.pending.item_definition_snapshot_id), ("fulfilled", self.eggs[0].pk))
        self.assertEqual(self.pending.coin_cost_snapshot, 21)
        fox_quantity = UserInventory.objects.get(user=self.child, item=self.eggs[2]).quantity
        first = ExpeditionService.claim(self.child, self.locked.pk)
        repeat = ExpeditionService.claim(self.child, self.locked.pk)
        self.assertTrue(first["freshly_claimed"])
        self.assertFalse(repeat["freshly_claimed"])
        self.assertEqual(first["coins_awarded"], 15)
        self.assertEqual(repeat["coins_awarded"], 0)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.eggs[2]).quantity, fox_quantity + 2)
        self.assertEqual(CoinService.get_balance(self.child), held_balance + 15)
        self.assertEqual(list(QuestRewardItem.objects.filter(quest_definition=self.quest).order_by("pk").values()),
                         [row for row in before["quests.QuestRewardItem"] if row["quest_definition_id"] == self.quest.pk])
        self.assertEqual(QuestDefinitionSerializer(self.quest).data["reward_items"], [])
        self.occurrence.refresh_from_db()
        self.assertEqual(self.occurrence.snapshot, before["quests.ChallengeOccurrence"][0]["snapshot"])
