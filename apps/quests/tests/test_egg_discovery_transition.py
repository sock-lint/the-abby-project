"""Prospective discovery admission never rewrites accepted challenge promises."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import PetService
from apps.quests.availability import definition_is_available
from apps.quests.controls import control_context, retry_challenge, retry_state
from apps.quests.milestone_eligibility import milestone_eligibility, prerequisite_completion
from apps.quests.goals import _catalog_goals, _occurrence, ingest_activity, list_goals, set_pin
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, ChallengePin, QuestDefinition, QuestRewardItem
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


@override_settings(
    EGG_DISCOVERY_ENABLED=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY={"schema_version": 1, "potion_slugs": ["base", "fire"], "pets": [
        {"species_slug": "transition-bird", "sprite_key": "transition-bird", "potion_slugs": ["base", "fire"]},
    ]},
)
class EggDiscoveryChallengeTransitionTests(TestCase):
    def setUp(self):
        family = make_family("Challenge transition", parents=[{"username": "transition-parent"}],
                             children=[{"username": "transition-child"}, {"username": "transition-sibling"}])
        self.parent, self.child, self.sibling = family.parents[0], *family.children
        self.now = timezone.now()
        self.species = PetSpecies.objects.create(slug="transition-bird", name="Transition bird", sprite_key="transition-bird")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.fire = PotionType.objects.create(slug="fire", name="Fire")
        self.species.available_potions.add(self.base, self.fire)
        self.egg = ItemDefinition.objects.create(slug="transition-bird-egg", name="Transition egg", item_type="egg",
                                                 pet_species=self.species)
        self.potion = ItemDefinition.objects.create(slug="fire-potion", name="Fire potion", item_type="potion",
                                                    potion_type=self.fire)
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        drops = patch("apps.rpg.services.DropService.award_accomplishment", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def definition(self, name="Earlier egg path", *, egg=True, elemental=False, **overrides):
        values = {
            "name": name, "quest_type": "collection", "target_value": 2, "duration_days": 7, "is_system": True,
            "coin_reward": 5, "xp_reward": 0, "trigger_filter": {"allowed_triggers": ["chore_complete"]}, **overrides,
        }
        with patch("django.utils.timezone.now", return_value=self.now):
            definition = QuestDefinition.objects.create(**values)
        if egg:
            QuestRewardItem.objects.create(quest_definition=definition, item=self.egg, quantity=2)
        if elemental:
            QuestRewardItem.objects.create(quest_definition=definition, item=self.potion, quantity=3)
        return definition

    def fact(self, identity, at=None):
        with patch("django.utils.timezone.now", return_value=at or self.now):
            return ingest_activity(self.child, "transition-test", identity, "chore_complete", occurred_at=at or self.now)

    def accepted(self, definition):
        with patch("django.utils.timezone.now", return_value=self.now):
            list_goals(self.child)
        return ChallengeOccurrence.objects.get(goal__catalog_definition=definition, goal__user=self.child)

    def inventory(self):
        return dict(UserInventory.objects.filter(user=self.child).values_list("item_id", "quantity"))

    def milestone(self, prior):
        return self.definition("Future reading title", egg=False, prerequisite_quest=prior,
                               trigger_filter={"allowed_triggers": ["reading_logged"]})

    def test_disabled_mode_keeps_new_system_egg_offers_and_ordinary_catalog_enrollment(self):
        definition = self.definition()
        self.assertTrue(definition_is_available(definition))
        self.assertIn(definition.pk, [row["id"] for row in self.client.get("/api/quests/available/").data])
        occurrence = self.accepted(definition)
        self.assertNotIn("legacy_egg_promise", list_goals(self.child)["results"][0])
        self.assertEqual(occurrence.snapshot["items"][0]["item_id"], self.egg.pk)

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_enabled_mode_hides_new_egg_enrollment_and_catalog_but_keeps_other_bonuses(self):
        egg = self.definition()
        other = self.definition("Ordinary chore bonus", egg=False)
        self.assertFalse(definition_is_available(egg))
        self.assertTrue(definition_is_available(other))
        for path in ("/api/quests/available/", "/api/quests/catalog/"):
            self.client.force_authenticate(self.parent if path.endswith("catalog/") else self.child)
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual([row["id"] for row in response.data], [other.pk])
        self.fact("new-fact")
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=egg).exists())
        self.assertEqual(ChallengeOccurrence.objects.get(goal__catalog_definition=other).progress, 1)

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_locked_milestone_egg_offer_is_not_exposed_or_enrolled(self):
        predecessor = self.definition("Earlier prerequisite", egg=False)
        milestone = self.definition("Locked egg milestone", prerequisite_quest=predecessor,
                                    trigger_filter={"allowed_triggers": ["reading_logged"]})
        payload = list_goals(self.child)
        self.assertNotIn(milestone.pk, [row["id"] for row in payload["locked_catalog"]])
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=milestone).exists())

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_solo_coop_and_scroll_starts_explain_discovery_without_consuming_inventory(self):
        definition = self.definition()
        scroll = ItemDefinition.objects.create(slug="transition-scroll", name="Saved scroll", item_type="quest_scroll")
        UserInventory.objects.create(user=self.child, item=scroll, quantity=1)
        with self.assertRaisesMessage(ValueError, "Choose an egg in Discoveries"):
            QuestService.start_quest(self.child, definition.pk, scroll.pk)
        with self.assertRaisesMessage(ValueError, "Choose an egg in Discoveries"):
            QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=scroll).quantity, 1)
        self.assertEqual(self.client.post("/api/quests/start/", {"definition_id": definition.pk}).status_code, 400)

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_reroll_does_not_choose_egg_campaign_or_consume_its_item(self):
        self.definition()
        reroll = ItemDefinition.objects.create(slug="transition-reroll", name="Quest reroll", item_type="consumable",
                                               metadata={"effect": "quest_reroll"})
        UserInventory.objects.create(user=self.child, item=reroll, quantity=1)
        with self.assertRaisesMessage(ValueError, "No eligible quests"):
            ConsumableService.use(self.child, reroll.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=reroll).quantity, 1)

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_automatic_admission_rechecks_new_egg_links_after_catalog_lock(self):
        from apps.quests.reference_locks import admit_definition_identity
        definition = self.definition(egg=False)

        def add_egg_after_wait(candidate):
            admit_definition_identity(candidate)
            QuestRewardItem.objects.create(quest_definition=candidate, item=self.egg)

        with patch("apps.quests.reference_locks.admit_definition_identity", side_effect=add_egg_after_wait):
            list_goals(self.child)
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=definition).exists())

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_legacy_admission_rechecks_new_egg_links_after_catalog_lock(self):
        from apps.quests.reference_locks import admit_definition_identity
        definition = self.definition(egg=False)

        def add_egg_after_wait(candidate):
            admit_definition_identity(candidate)
            QuestRewardItem.objects.create(quest_definition=candidate, item=self.egg)

        with patch("apps.quests.reference_locks.admit_definition_identity", side_effect=add_egg_after_wait):
            with self.assertRaisesMessage(ValueError, "Choose an egg in Discoveries"):
                QuestService.start_quest(self.child, definition.pk)
            with self.assertRaisesMessage(ValueError, "Choose an egg in Discoveries"):
                QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])

    def test_accepted_automatic_elemental_bundle_completes_exactly_once_after_enablement(self):
        occurrence = self.accepted(self.definition(elemental=True))
        saved = deepcopy(occurrence.snapshot)
        self.fact("before")
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            self.fact("after")
            self.fact("after")
            payload = list_goals(self.child)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, saved)
        self.assertEqual((occurrence.progress, occurrence.status, occurrence.reward_receipt["coins"]), (2, "completed", 5))
        self.assertEqual(self.inventory(), {self.egg.pk: 2, self.potion.pk: 3})
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=5).count(), 1)
        self.assertTrue(next(row for row in payload["results"] if row["id"] == f"goal:{occurrence.pk}")["legacy_egg_promise"])

    def test_accepted_legacy_campaign_retains_exact_item_promise_after_enablement(self):
        definition = self.definition(elemental=True)
        quest = QuestService.start_quest(self.child, definition.pk)
        saved = deepcopy(quest.reward_items_snapshot)
        definition.reward_items.all().delete()
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            payload = list_goals(self.child)
            self.assertTrue(next(row for row in payload["results"] if row["id"] == f"legacy:{quest.pk}")["legacy_egg_promise"])
            QuestService.record_progress(self.child, "chore_complete")
            QuestService.record_progress(self.child, "chore_complete")
            self.assertIsNone(QuestService.record_progress(self.child, "chore_complete"))
        quest.refresh_from_db()
        self.assertEqual(quest.reward_items_snapshot, saved)
        self.assertEqual(quest.status, "completed")
        self.assertEqual(self.inventory(), {self.egg.pk: 2, self.potion.pk: 3})
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=5).count(), 1)

    def test_saved_coop_campaign_still_pays_each_accepted_participant(self):
        quest = QuestService.start_co_op_quest(self.definition(elemental=True).pk, [self.child, self.sibling])
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            QuestService.record_progress(self.child, "chore_complete")
            QuestService.record_progress(self.child, "chore_complete")
        quest.refresh_from_db()
        self.assertEqual(quest.status, "completed")
        for child in (self.child, self.sibling):
            self.assertEqual(dict(UserInventory.objects.filter(user=child).values_list("item_id", "quantity")),
                             {self.egg.pk: 2, self.potion.pk: 3})

    def test_initial_accepted_goal_can_materialize_its_window_after_enablement(self):
        definition = self.definition(is_repeatable=True)
        with patch("django.utils.timezone.now", return_value=self.now):
            _catalog_goals(self.child)
        goal = ChallengeGoal.objects.get(catalog_definition=definition, user=self.child)
        self.assertFalse(goal.occurrences.exists())
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            initial = _occurrence(goal, goal.starts_at)
            self.assertIsNotNone(initial)
            self.assertIsNone(_occurrence(goal, initial.ends_at))
        self.assertEqual(goal.occurrences.count(), 1)

    def test_disabled_mode_keeps_later_recurring_egg_windows(self):
        initial = self.accepted(self.definition(is_repeatable=True))
        later = _occurrence(initial.goal, initial.ends_at)
        self.assertIsNotNone(later)
        self.assertEqual(later.snapshot["items"], initial.snapshot["items"])

    def test_saved_future_window_completes_but_another_unsaved_cycle_does_not_open(self):
        initial = self.accepted(self.definition(is_repeatable=True))
        second = _occurrence(initial.goal, initial.ends_at)
        saved = deepcopy(second.snapshot)
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            self.fact("second-one", second.starts_at)
            self.fact("second-two", second.starts_at)
            self.fact("third-blocked", second.ends_at)
        second.refresh_from_db()
        self.assertEqual((second.status, second.snapshot), ("completed", saved))
        self.assertEqual(self.inventory(), {self.egg.pk: 2})
        self.assertEqual(initial.goal.occurrences.count(), 2)

    def test_old_recurring_egg_promise_cannot_reopen_after_current_links_remove_egg(self):
        definition = self.definition(is_repeatable=True)
        initial = self.accepted(definition)
        definition.reward_items.all().delete()
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            self.assertIsNone(_occurrence(initial.goal, initial.ends_at))
        self.assertEqual(initial.goal.occurrences.count(), 1)

    def test_newly_added_egg_reward_also_stops_future_cycles_without_changing_saved_window(self):
        definition = self.definition(egg=False, is_repeatable=True)
        initial = self.accepted(definition)
        QuestRewardItem.objects.create(quest_definition=definition, item=self.egg)
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            self.assertIsNone(_occurrence(initial.goal, initial.ends_at))
        initial.refresh_from_db()
        self.assertEqual(initial.snapshot["items"], [])

    def test_accepted_one_time_retry_is_preserved_and_keeps_original_bundle(self):
        original = self.accepted(self.definition(elemental=True))
        retry_at = original.ends_at + timedelta(hours=1)
        with override_settings(EGG_DISCOVERY_ENABLED=True), patch("django.utils.timezone.now", return_value=retry_at):
            self.assertTrue(retry_state(original, control_context(self.child))["allowed"])
            successor, created = retry_challenge(self.child, original.pk)
            self.assertTrue(created)
            self.assertEqual(successor.snapshot["items"], original.snapshot["items"])
            replay, created = retry_challenge(self.child, original.pk)
            self.assertEqual((replay.pk, created), (successor.pk, False))
            self.fact("retry-one", retry_at)
            self.fact("retry-two", retry_at)
        self.assertEqual(self.inventory(), {self.egg.pk: 2, self.potion.pk: 3})
        original.refresh_from_db()
        self.assertIsNone(original.awarded_at)

    def test_private_parent_campaigns_and_recurring_goals_remain_available_and_unmarked(self):
        definition = self.definition()
        definition.is_system, definition.created_by = False, self.parent
        definition.save(update_fields=["is_system", "created_by"])
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            self.assertTrue(definition_is_available(definition))
            quest = QuestService.start_quest(self.child, definition.pk)
            row = next(row for row in list_goals(self.child)["results"] if row["id"] == f"legacy:{quest.pk}")
            self.assertNotIn("legacy_egg_promise", row)
            goal = ChallengeGoal.objects.create(
                user=self.child, family=self.child.family, created_by=self.parent, is_catalog=False,
                name="Parent's continuing goal", metric="count", target=2, unit="actions", timezone_name="UTC",
                trigger_filter={"allowed_triggers": ["chore_complete"]}, starts_at=self.now,
                ends_at=self.now + timedelta(days=7), repeat_weekly=True,
                reward_items=[{"item_id": self.egg.pk, "quantity": 1}],
            )
            occurrence = _occurrence(goal, self.now + timedelta(days=14))
            self.assertIsNotNone(occurrence)
            row = next(row for row in list_goals(self.child)["results"] if row["id"] == f"goal:{_occurrence(goal, self.now).pk}")
            self.assertNotIn("legacy_egg_promise", row)

    def test_enabled_reads_preserve_saved_progress_rewards_pins_and_inventory(self):
        original = self.accepted(self.definition())
        set_pin(self.child, f"goal:{original.pk}")
        saved_pin = ChallengePin.objects.values("occurrence_id", "legacy_quest_id", "updated_at").get(user=self.child)
        saved = deepcopy(original.__dict__)
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            for _ in range(2):
                response = self.client.get("/api/challenges/")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data["results"][0]["legacy_egg_promise"])
        original.refresh_from_db()
        for field in ("snapshot", "progress", "status", "completed_at", "awarded_at", "reward_receipt", "updated_at"):
            self.assertEqual(getattr(original, field), saved[field])
        self.assertEqual(self.inventory(), {})
        self.assertEqual(ChallengePin.objects.values("occurrence_id", "legacy_quest_id", "updated_at").get(user=self.child), saved_pin)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_native_hatch_unlocks_future_non_egg_milestone_then_fresh_reading_opens_it(self):
        from apps.reading.models import ReadingBook

        prior = self.definition(elemental=True)
        target = self.milestone(prior)
        UserInventory.objects.create(user=self.child, item=self.egg, quantity=1)
        UserInventory.objects.create(user=self.child, item=self.potion, quantity=1)
        self.assertFalse(milestone_eligibility(self.child, target)["unlocked"])
        incubation, _ = PetService.start_incubation(self.child, self.egg.pk, self.potion.pk, uuid4())
        self.assertFalse(milestone_eligibility(self.child, target)["unlocked"])
        at = incubation.ready_at + timedelta(seconds=1)
        with patch("django.utils.timezone.now", return_value=at):
            PetService.hatch_incubation(self.child, incubation.pk)
            self.assertTrue(milestone_eligibility(self.child, target)["unlocked"])
            list_goals(self.child)
            self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=target, user=self.child).exists())
            book = ReadingBook.objects.create(user=self.child, title="Synthetic bridge reading", client_request_id=uuid4(),
                                              create_payload={})
            response = self.client.post("/api/reading-sessions/", {
                "book": book.pk, "duration_minutes": 10, "client_request_id": str(uuid4()),
            }, format="json")
            self.assertEqual(response.status_code, 201, response.data)
        accepted = ChallengeGoal.objects.get(user=self.child, catalog_definition=target)
        self.assertEqual(accepted.catalog_gate_snapshot["version"], 2)
        self.assertEqual(accepted.catalog_gate_snapshot["prerequisite_hatch_pairs"][0]["species_id"], self.species.pk)
        self.assertEqual(accepted.occurrences.get().progress, 1)
        self.assertEqual(prerequisite_completion(self.child, prior.pk), (False, None))
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=prior).exists())
        UserPet.objects.filter(user=self.child).delete()
        with patch("django.utils.timezone.now", return_value=at):
            self.assertTrue(milestone_eligibility(self.child, target, new_enrollment=False,
                                                accepted_gate=accepted.catalog_gate_snapshot)["unlocked"])

    def test_new_bridge_retry_keeps_frozen_pairs_after_mode_and_bundle_change(self):
        prior = self.definition(elemental=True)
        target = self.milestone(prior)
        UserPet.objects.create(user=self.child, species=self.species, potion=self.fire)
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            ingest_activity(self.child, "bridge-reading", "opening", "reading_logged", fresh_milestone=True)
        original = ChallengeOccurrence.objects.get(goal__catalog_definition=target)
        saved = deepcopy(original.snapshot["catalog_gate"])
        prior.reward_items.all().delete()
        QuestRewardItem.objects.create(quest_definition=prior, item=ItemDefinition.objects.create(
            name="Unrelated replacement egg", item_type="egg", pet_species=self.species,
        ))
        with patch("django.utils.timezone.now", return_value=original.ends_at + timedelta(hours=1)):
            self.assertTrue(retry_state(original, control_context(self.child))["allowed"])
            successor, created = retry_challenge(self.child, original.pk)
            self.assertTrue(created)
            self.assertEqual(successor.snapshot["catalog_gate"], saved)

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_exact_pair_gate_accepts_owned_pet_or_mount_but_not_wrong_variant_or_sibling(self):
        prior = self.definition(elemental=True)
        target = self.milestone(prior)
        UserPet.objects.create(user=self.sibling, species=self.species, potion=self.fire)
        wrong = UserPet.objects.create(user=self.child, species=self.species, potion=self.base)
        self.assertFalse(milestone_eligibility(self.child, target)["unlocked"])
        wrong.potion = self.fire
        wrong.save(update_fields=["potion"])
        self.assertTrue(milestone_eligibility(self.child, target)["unlocked"])
        wrong.delete()
        UserMount.objects.create(user=self.child, species=self.species, potion=self.fire)
        self.assertTrue(milestone_eligibility(self.child, target)["unlocked"])

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_every_typed_pair_remains_required_and_skill_gate_is_not_relaxed(self):
        from apps.achievements.models import Skill, SkillCategory, SkillProgress

        prior = self.definition(elemental=True)
        base_item = ItemDefinition.objects.create(slug="bridge-base-potion", name="Base potion", item_type="potion",
                                                  potion_type=self.base)
        QuestRewardItem.objects.create(quest_definition=prior, item=base_item)
        target = self.milestone(prior)
        target.required_skill = Skill.objects.create(name="Bridge reading", category=SkillCategory.objects.create(name="Bridge skills"))
        target.required_skill_level = 1
        target.save(update_fields=["required_skill", "required_skill_level"])
        UserPet.objects.create(user=self.child, species=self.species, potion=self.fire)
        self.assertFalse(milestone_eligibility(self.child, target)["unlocked"])
        UserPet.objects.create(user=self.child, species=self.species, potion=self.base)
        self.assertFalse(milestone_eligibility(self.child, target)["unlocked"])
        SkillProgress.objects.create(user=self.child, skill=target.required_skill, level=1, xp_points=100)
        self.assertTrue(milestone_eligibility(self.child, target)["unlocked"])

    def test_disabled_mode_and_saved_retry_gates_keep_original_challenge_requirement(self):
        prior = self.definition(elemental=True)
        target = self.milestone(prior)
        UserPet.objects.create(user=self.child, species=self.species, potion=self.fire)
        self.assertFalse(milestone_eligibility(self.child, target)["unlocked"])
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            self.assertTrue(milestone_eligibility(self.child, target)["unlocked"])
            strict = milestone_eligibility(self.child, target, new_enrollment=False)
            self.assertFalse(strict["unlocked"])
            self.assertNotIn("prerequisite_hatch_pairs", strict)

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_untyped_egg_prerequisite_does_not_invent_a_hatch_substitute(self):
        prior = self.definition(elemental=True)
        ItemDefinition.objects.filter(pk=self.egg.pk).update(pet_species=None)
        target = self.milestone(prior)
        UserPet.objects.create(user=self.child, species=self.species, potion=self.fire)
        eligibility = milestone_eligibility(self.child, target)
        self.assertFalse(eligibility["unlocked"])
        self.assertNotIn("prerequisite_hatch_pairs", eligibility)

    def test_existing_milestone_gate_snapshot_and_window_stay_unchanged_after_enablement(self):
        prior = self.definition(elemental=True)
        target = self.milestone(prior)
        self.fact("old-prior-one")
        self.fact("old-prior-two")
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(seconds=1)):
            ingest_activity(self.child, "old-milestone", "opening", "reading_logged", fresh_milestone=True)
        goal = ChallengeGoal.objects.get(user=self.child, catalog_definition=target)
        occurrence = goal.occurrences.get()
        saved = (deepcopy(goal.catalog_gate_snapshot), deepcopy(occurrence.snapshot), goal.starts_at, goal.ends_at)
        self.assertEqual(goal.catalog_gate_snapshot["version"], 1)
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            list_goals(self.child)
        goal.refresh_from_db()
        occurrence.refresh_from_db()
        self.assertEqual((goal.catalog_gate_snapshot, occurrence.snapshot, goal.starts_at, goal.ends_at), saved)

    @override_settings(EGG_DISCOVERY_ENABLED=True)
    def test_bridge_admission_rereads_prerequisite_pairs_after_target_lock(self):
        from apps.quests.reference_locks import admit_definition_identity

        prior = self.definition(elemental=True)
        target = self.milestone(prior)
        UserPet.objects.create(user=self.child, species=self.species, potion=self.fire)
        base_item = ItemDefinition.objects.create(slug="changed-bridge-base", name="Changed Base potion",
                                                  item_type="potion", potion_type=self.base)

        def change_pairs_during_target_wait(candidate):
            admit_definition_identity(candidate)
            if candidate.pk == target.pk:
                prior.reward_items.filter(item=self.potion).delete()
                QuestRewardItem.objects.create(quest_definition=prior, item=base_item)

        with patch("apps.quests.reference_locks.admit_definition_identity", side_effect=change_pairs_during_target_wait):
            ingest_activity(self.child, "bridge-reading", "changed-at-admission", "reading_logged", fresh_milestone=True)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child, catalog_definition=target).exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL NOWAIT prerequisite admission")
@override_settings(EGG_DISCOVERY_ENABLED=True,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DiscoveryPrerequisiteAdmissionConcurrencyTests(TransactionTestCase):
    def test_busy_prerequisite_keeps_source_and_releases_partial_catalog_locks(self):
        self.assert_busy_bridge_writer_preserves_source(reward_link=False)

    def test_busy_reward_link_keeps_source_and_releases_partial_catalog_locks(self):
        self.assert_busy_bridge_writer_preserves_source(reward_link=True)

    def assert_busy_bridge_writer_preserves_source(self, *, reward_link):
        from apps.quests.models import ChallengeActivity

        child = make_family("Bridge contention", children=[{"username": "bridge-pg-child"}]).children[0]
        species = PetSpecies.objects.create(slug="bridge-pg-bird", name="Bridge PG bird")
        potion = PotionType.objects.create(slug="base", name="Base")
        egg = ItemDefinition.objects.create(name="Bridge PG egg", item_type="egg", pet_species=species)
        ingredient = ItemDefinition.objects.create(name="Bridge PG potion", item_type="potion", potion_type=potion)
        prior = QuestDefinition.objects.create(name="Bridge PG prior", quest_type="collection", target_value=2,
                                               duration_days=7, is_system=True)
        QuestRewardItem.objects.create(quest_definition=prior, item=egg)
        QuestRewardItem.objects.create(quest_definition=prior, item=ingredient)
        target = QuestDefinition.objects.create(name="Bridge PG title", quest_type="collection", target_value=2,
                                                duration_days=7, is_system=True, prerequisite_quest=prior,
                                                trigger_filter={"allowed_triggers": ["reading_logged"]})
        UserPet.objects.create(user=child, species=species, potion=potion)
        locked, update_requested, updated, release = Event(), Event(), Event(), Event()

        def edit_prerequisite():
            close_old_connections()
            try:
                with transaction.atomic():
                    if reward_link:
                        QuestRewardItem.objects.filter(quest_definition=prior, item=egg).update(quantity=2)
                    else:
                        QuestDefinition.objects.select_for_update().get(pk=prior.pk)
                    locked.set()
                    if not update_requested.wait(10):
                        raise AssertionError("Source did not finish its NOWAIT admission")
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '2s'")
                    ItemDefinition.objects.filter(pk=egg.pk).update(description="Current catalog description")
                    updated.set()
                    if not release.wait(10):
                        raise AssertionError("Test did not release the prerequisite writer")
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            writer = executor.submit(edit_prerequisite)
            try:
                self.assertTrue(locked.wait(5))
                with transaction.atomic():
                    ingest_activity(child, "bridge-pg-reading", "busy", "reading_logged", fresh_milestone=True)
                    self.assertFalse(ChallengeGoal.objects.filter(user=child, catalog_definition=target).exists())
                    self.assertTrue(ChallengeActivity.objects.filter(user=child, source_id="busy").exists())
                    update_requested.set()
                    self.assertTrue(updated.wait(5), "Failed admission retained a partial ingredient catalog lock")
            finally:
                update_requested.set()
                release.set()
                writer.result(timeout=15)
        ingest_activity(child, "bridge-pg-reading", "after-writer", "reading_logged", fresh_milestone=True)
        accepted = ChallengeGoal.objects.get(user=child, catalog_definition=target)
        self.assertEqual(accepted.catalog_gate_snapshot["version"], 2)
