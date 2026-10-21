"""New retries need available rewards; accepted attempts retain their promises."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies, PotionType
from apps.quests.controls import control_context, retry_state
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


def art_policy(*variants):
    return {"schema_version": 1, "potion_slugs": ["base", *variants], "pets": [
        {"species_slug": "saved-retry-chick", "sprite_key": "saved-retry-chick",
         "potion_slugs": ["base", *variants]},
    ]}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   RPG_ASSET_SUPPORT_POLICY=art_policy("fire"))
class AcceptedElementalRetryTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "saved-pair-child"}]).children[0]
        self.child.family.timezone = "UTC"
        self.child.family.save(update_fields=["timezone"])
        self.species = PetSpecies.objects.create(slug="saved-retry-chick", name="Saved retry chick",
                                                sprite_key="saved-retry-chick")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.fire = PotionType.objects.create(slug="fire", name="Fire")
        self.species.available_potions.add(self.base, self.fire)
        self.egg = ItemDefinition.objects.create(slug="saved-retry-chick-egg", name="Saved retry egg",
                                                item_type="egg", pet_species=self.species)
        self.potion = ItemDefinition.objects.create(slug="fire-potion", name="Fire potion", item_type="potion", potion_type=self.fire)
        self.accepted_at = datetime(2026, 10, 19, 12, tzinfo=datetime_timezone.utc)
        self.retry_at = self.accepted_at + timedelta(days=2)
        self.original = self.expired([(self.egg, 2), (self.potion, 3)])
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        drops = patch("apps.rpg.services.DropService.award_accomplishment", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def expired(self, rewards):
        with patch("django.utils.timezone.now", return_value=self.accepted_at):
            definition = QuestDefinition.objects.create(
                name=f"Accepted retry {QuestDefinition.objects.count()}", quest_type="collection", target_value=1,
                duration_days=1, is_system=True, coin_reward=0, xp_reward=0,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            for item, quantity in rewards:
                QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=quantity)
            list_goals(self.child)
            return ChallengeOccurrence.objects.get(goal__catalog_definition=definition, goal__user=self.child)

    def retry(self, occurrence=None):
        with patch("django.utils.timezone.now", return_value=self.retry_at):
            return self.client.post(f"/api/challenges/goal:{(occurrence or self.original).pk}/retry/", {}, format="json")

    def assert_blocked(self, occurrence=None):
        occurrence = occurrence or self.original
        saved = deepcopy(occurrence.snapshot)
        response = self.retry(occurrence)
        self.assertEqual((response.status_code, response.data), (409, {"error": "reward_unavailable"}))
        with patch("django.utils.timezone.now", return_value=self.retry_at):
            state = retry_state(occurrence, control_context(self.child))
        self.assertEqual((state["allowed"], state["reason"]), (False, "reward_unavailable"))
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=occurrence).exists())
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, saved)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_new_retry_is_blocked_after_reward_art_is_withdrawn(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy()):
            self.assert_blocked()

    def test_new_retry_requires_saved_exact_pair_art_and_authored_compatibility(self):
        policy = art_policy("fire")
        policy["pets"][0]["potion_slugs"] = ["base"]
        with override_settings(RPG_ASSET_SUPPORT_POLICY=policy):
            self.assert_blocked()
        self.species.available_potions.set([self.base])
        self.assert_blocked()

    def test_new_retry_checks_generic_saved_items_even_if_definition_links_changed(self):
        bee = PetSpecies.objects.create(slug="saved-bee", name="Saved bee", sprite_key="saved-bee")
        egg = ItemDefinition.objects.create(slug="saved-bee-egg", name="Saved Bee Egg", item_type="egg", pet_species=bee)
        policy = art_policy("fire")
        policy["pets"].append({"species_slug": bee.slug, "sprite_key": bee.sprite_key, "potion_slugs": ["base"]})
        with override_settings(RPG_ASSET_SUPPORT_POLICY=policy):
            original = self.expired([(egg, 1)])
        original.goal.catalog_definition.reward_items.all().delete()
        self.assert_blocked(original)

    def test_new_retry_rejects_a_deleted_saved_item_without_replacing_it(self):
        snack = ItemDefinition.objects.create(slug="deleted-retry-snack", name="Saved snack", item_type="food")
        original = self.expired([(snack, 1)])
        snack.delete()
        self.assert_blocked(original)

    def test_zero_item_promise_can_retry_despite_new_unavailable_definition_rewards(self):
        original = self.expired([])
        unavailable = ItemDefinition.objects.create(name="Unavailable accessory", item_type="cosmetic_pet_accessory")
        QuestRewardItem.objects.create(quest_definition=original.goal.catalog_definition, item=unavailable)
        with patch("apps.quests.controls.lock_retry_reward_catalog", side_effect=AssertionError("No item fence needed")):
            response = self.retry(original)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ChallengeOccurrence.objects.get(retry_of=original).snapshot["items"], [])

    def test_supported_saved_bundle_ignores_unavailable_replacement_definition_items(self):
        unavailable = ItemDefinition.objects.create(name="Later unavailable accessory", item_type="cosmetic_pet_accessory")
        self.original.goal.catalog_definition.reward_items.all().delete()
        QuestRewardItem.objects.create(quest_definition=self.original.goal.catalog_definition, item=unavailable)
        response = self.retry()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ChallengeOccurrence.objects.get(retry_of=self.original).snapshot["items"], self.original.snapshot["items"])

    def test_admission_rechecks_pair_compatibility_after_the_read_projection(self):
        def project_then_change(user):
            context = control_context(user)
            self.assertTrue(retry_state(self.original, context)["allowed"])
            self.species.available_potions.set([self.base])
            return context

        with patch("apps.quests.controls.control_context", side_effect=project_then_change):
            response = self.retry()
        self.assertEqual((response.status_code, response.data), (409, {"error": "reward_unavailable"}))
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=self.original).exists())

    def test_legacy_metadata_reward_projection_has_flat_query_growth(self):
        def add_legacy(index):
            egg = ItemDefinition.objects.create(name=f"Legacy egg {index}", item_type="egg",
                                                metadata={"species": self.species.name})
            self.expired([(egg, 1)])

        add_legacy(0)
        with CaptureQueriesContext(connection) as single:
            control_context(self.child)
        for index in range(1, 9):
            add_legacy(index)
        with CaptureQueriesContext(connection) as multiple:
            control_context(self.child)
        self.assertLessEqual(len(multiple), len(single) + 1,
                             "Legacy reference resolution must be shared across all saved rewards.")

    def test_accepted_retry_replay_and_one_payout_survive_later_art_withdrawal(self):
        saved = deepcopy(self.original.snapshot)
        response = self.retry()
        self.assertEqual(response.status_code, 201, response.data)
        retry = ChallengeOccurrence.objects.get(retry_of=self.original)
        self.assertEqual(retry.snapshot, {**saved, "_retry_after_activity_id": 0})
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy()), patch("django.utils.timezone.now", return_value=self.retry_at):
            self.assertEqual(self.retry().status_code, 200)
            ingest_activity(self.child, "chore_complete", "fresh-saved-pair-work", "chore_complete",
                            occurred_at=self.retry_at, occurred_on=self.retry_at.date())
            replay = self.retry()
            self.assertEqual((replay.status_code, replay.data["id"]), (200, f"goal:{retry.pk}"))
        retry.refresh_from_db()
        self.assertEqual({row["item_id"]: row["quantity"] for row in retry.reward_receipt["items"]},
                         {self.egg.pk: 2, self.potion.pk: 3})
        self.assertEqual(list(UserInventory.objects.filter(user=self.child).order_by("item_id").values_list("item_id", "quantity")),
                         [(self.egg.pk, 2), (self.potion.pk, 3)])
        self.original.refresh_from_db()
        self.assertEqual(self.original.snapshot, saved)
        self.assertEqual((self.original.status, self.original.closed_reason, self.original.reward_receipt),
                         ("closed", "reward_already_awarded", {}))

    def test_late_original_completion_still_fulfills_saved_items_after_withdrawal(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy()), patch("django.utils.timezone.now", return_value=self.retry_at):
            self.assert_blocked()
            ingest_activity(self.child, "chore_complete", "late-original-pair-work", "chore_complete",
                            occurred_at=self.accepted_at, occurred_on=self.accepted_at.date())
        self.original.refresh_from_db()
        self.assertEqual(self.original.status, "completed")
        self.assertEqual({row["item_id"] for row in self.original.reward_receipt["items"]}, {self.egg.pk, self.potion.pk})

    def test_reward_retry_projection_is_batched_and_pure(self):
        with CaptureQueriesContext(connection) as single:
            control_context(self.child)
        for _ in range(8):
            self.expired([(self.egg, 2), (self.potion, 3)])
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy()), patch("django.utils.timezone.now", return_value=self.retry_at):
            with CaptureQueriesContext(connection) as multiple:
                context = control_context(self.child)
            rows = list(ChallengeOccurrence.objects.select_related("goal__catalog_definition"))
            with CaptureQueriesContext(connection) as projected:
                states = [retry_state(row, context) for row in rows for _ in range(3)]
        self.assertLessEqual(len(multiple), len(single) + 1)
        self.assertEqual(len(projected), 0)
        self.assertEqual({state["reason"] for state in states}, {"reward_unavailable"})

    def test_malformed_saved_items_fail_closed_without_breaking_other_goals(self):
        valid = self.expired([])
        for items in (None, {}, "invalid", [None], [{}], [{"item_id": True, "quantity": 1}],
                      [{"item_id": 10**100, "quantity": 1}], [{"item_id": self.egg.pk, "quantity": False}]):
            with self.subTest(items=items):
                self.original.snapshot["items"] = items
                self.original.save(update_fields=["snapshot"])
                with patch("django.utils.timezone.now", return_value=self.retry_at):
                    context = control_context(self.child)
                self.assertEqual(retry_state(self.original, context)["reason"], "reward_unavailable")
                self.assertTrue(retry_state(valid, context)["allowed"])
