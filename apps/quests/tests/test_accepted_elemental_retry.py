"""Explicit retries preserve the one accepted elemental ingredient promise."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies, PotionType
from apps.quests.availability import definition_is_available
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


def art_policy(*variants):
    return {"schema_version": 1, "potion_slugs": ["base", *variants], "pets": [
        {"species_slug": "saved-retry-chick", "sprite_key": "saved-retry-chick",
         "potion_slugs": ["base", *variants]},
    ]}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AcceptedElementalRetryTests(TestCase):
    @patch("apps.rpg.services.DropService.award_accomplishment", return_value=[])
    def test_art_withdrawal_keeps_retry_snapshot_quantities_and_one_lifetime_payout(self, _drops):
        family = make_family(children=[{"username": "saved-pair-child"}, {"username": "new-pair-child"}])
        child, new_child = family.children
        family.family.timezone = "UTC"
        family.family.save(update_fields=["timezone"])
        species = PetSpecies.objects.create(slug="saved-retry-chick", name="Saved retry chick",
                                           sprite_key="saved-retry-chick")
        base = PotionType.objects.create(slug="base", name="Base")
        fire = PotionType.objects.create(slug="fire", name="Fire")
        species.available_potions.add(base, fire)
        egg = ItemDefinition.objects.create(slug="saved-retry-chick-egg", name="Saved retry egg",
                                            item_type="egg", pet_species=species)
        potion = ItemDefinition.objects.create(slug="fire-potion", name="Fire potion", item_type="potion", potion_type=fire)
        accepted_at = datetime(2026, 10, 19, 12, tzinfo=datetime_timezone.utc)
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy("fire")), patch("django.utils.timezone.now", return_value=accepted_at):
            definition = QuestDefinition.objects.create(
                name="Accepted elemental retry", quest_type="collection", target_value=1,
                duration_days=1, is_system=True, coin_reward=0, xp_reward=0,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            for item, quantity in ((egg, 2), (potion, 3)):
                QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=quantity)
            list_goals(child)
            original = ChallengeOccurrence.objects.get(goal__user=child)
        saved = deepcopy(original.snapshot)
        client = APIClient()
        client.force_authenticate(child)
        retry_at = accepted_at + timedelta(days=2)
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy()), patch("django.utils.timezone.now", return_value=retry_at):
            self.assertFalse(definition_is_available(definition))
            self.assertEqual(list_goals(new_child)["results"], [])
            self.assertFalse(ChallengeGoal.objects.filter(user=new_child).exists())
            response = client.post(f"/api/challenges/goal:{original.pk}/retry/", {}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            retry = ChallengeOccurrence.objects.get(retry_of=original)
            self.assertEqual(retry.snapshot, {**saved, "_retry_after_activity_id": 0})
            ingest_activity(child, "chore_complete", "fresh-saved-pair-work", "chore_complete",
                            occurred_at=retry_at, occurred_on=retry_at.date())
            retry.refresh_from_db()
            self.assertEqual((retry.reward_receipt["coins"], retry.reward_receipt["xp"]), (0, 0))
            self.assertEqual({row["item_id"]: row["quantity"] for row in retry.reward_receipt["items"]},
                             {egg.pk: 2, potion.pk: 3})
            receipt = deepcopy(retry.reward_receipt)
            replay = client.post(f"/api/challenges/goal:{original.pk}/retry/", {}, format="json")
            self.assertEqual((replay.status_code, replay.data["id"]), (200, f"goal:{retry.pk}"))
            self.assertEqual(list(UserInventory.objects.filter(user=child).order_by("item_id").values_list("item_id", "quantity")),
                             [(egg.pk, 2), (potion.pk, 3)])
            self.assertEqual(ChallengeOccurrence.objects.filter(goal=original.goal).count(), 2)
            self.assertFalse(CoinLedger.objects.filter(user=child).exists())
        original.refresh_from_db()
        retry.refresh_from_db()
        self.assertEqual(original.snapshot, saved)
        self.assertEqual((original.status, original.closed_reason, original.reward_receipt),
                         ("closed", "reward_already_awarded", {}))
        self.assertEqual(retry.reward_receipt, receipt)
