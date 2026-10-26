"""Hatchery discovery reads exact offers and accepted promises without writes."""
from copy import deepcopy
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant, QuestRewardItem
from apps.quests.reward_items import snapshot_reward_items
from apps.rpg.models import ItemDefinition
from config.tests.factories import make_family


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HatcheryDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.potions = {slug: PotionType.objects.create(slug=slug, name=slug.title())
                       for slug in ("base", "fire", "ice")}
        cls.ingredients = {slug: ItemDefinition.objects.create(
            slug=f"{slug}-potion", name=f"{slug.title()} Potion", item_type="potion",
            potion_type=potion, metadata={"variant": slug},
        ) for slug, potion in cls.potions.items()}
        cls.species, cls.eggs = {}, {}
        content = yaml.safe_load((Path(settings.BASE_DIR) / "content/rpg/initial/pet_species.yaml").read_text())
        for row in content["species"]:
            species = PetSpecies.objects.create(slug=row["slug"], name=row["name"],
                                                sprite_key=row["sprite_key"])
            species.available_potions.add(*(cls.potions[slug] for slug in row["available_potions"]))
            cls.species[species.slug] = species
            cls.eggs[species.slug] = ItemDefinition.objects.create(
                slug=f"{species.slug}-egg", name=f"{species.name} Egg", item_type="egg",
                pet_species=species, metadata={"species": species.slug},
            )

    def setUp(self):
        family = make_family("Hatchery discovery", parents=[{"username": "discovery-parent"}],
                             children=[{"username": "discovery-child"}, {"username": "discovery-sibling"}])
        self.child, self.sibling = family.children
        self.parent = family.parents[0]
        self.foreign = make_family("Other discovery", children=[{"username": "foreign-discovery"}]).children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        self.now = timezone.now()

    def definition(self, *, name="A renamed public discovery", species="chick", potion="fire", **kwargs):
        definition = QuestDefinition.objects.create(
            name=name, quest_type="collection", target_value=10, duration_days=180,
            trigger_filter={"allowed_triggers": ["chore_complete"]}, is_system=True,
            **kwargs,
        )
        for item in (self.eggs[species], self.ingredients[potion]):
            QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=1)
        return definition

    def accepted(self, definition, *, user=None, progress=3, status="active", expired=False, **kwargs):
        user = user or self.child
        starts = self.now - timedelta(days=181 if expired else 1)
        ends = self.now - timedelta(days=1) if expired else self.now + timedelta(days=179)
        goal = ChallengeGoal.objects.create(
            user=user, family=user.family, is_catalog=True, catalog_definition=definition,
            name="The accepted promise", description="Saved description", metric="count", target=8,
            unit="actions", trigger_filter=definition.trigger_filter, starts_at=starts, ends_at=ends,
            reward_items=[{"item_id": row.item_id, "quantity": row.quantity}
                          for row in definition.reward_items.all()],
        )
        snapshot = {"name": goal.name, "description": goal.description, "metric": "count", "target": "8",
                    "unit": "actions", "filter": deepcopy(goal.trigger_filter), "items": snapshot_reward_items(definition),
                    "skill_tags": [], "coins": 0, "xp": 0}
        occurrence = ChallengeOccurrence.objects.create(
            goal=goal, starts_at=starts, ends_at=ends, snapshot=snapshot, progress=progress,
            status=status, **kwargs,
        )
        return occurrence

    def catalog(self, **params):
        response = self.client.get("/api/pets/codex/", params)
        self.assertEqual(response.status_code, 200)
        return response.data

    def paths(self, *, species="chick", potion="fire", **params):
        row = next(row for row in self.catalog(**params)["species"] if row["slug"] == species)
        variant = next(row for row in row["available_potions"] if row["slug"] == potion)
        self.assertIn("acquisition_challenges", variant)
        return variant["acquisition_challenges"]

    def test_empty_inventory_browses_all_exact_pairs_without_materialization_or_rewards(self):
        definition = self.definition()
        with CaptureQueriesContext(connection) as queries:
            body = self.catalog()
        self.assertEqual(len(body["species"]), 15)
        self.assertEqual(sum(len(row["available_potions"]) for row in body["species"]), 31)
        for species in body["species"]:
            expected = {"base", "fire", "ice"} if species["slug"] in {
                "chick", "meshtint-wolf", "meshtint-mushroom", "meshtint-dragon", "meshtint-bee", "meshtint-bat",
                "meshtint-snake", "meshtint-hermit-crab",
            } else {"base"}
            self.assertEqual({row["slug"] for row in species["available_potions"]}, expected)
            for potion in species["available_potions"]:
                self.assertIn("acquisition_challenges", potion)
        self.assertEqual(self.paths(), [{
            "definition_id": definition.pk, "name": definition.name, "offer_available": True,
            "target": "10", "duration_days": 180, "attempt": None, "path": "/quests?tab=trials",
        }])
        writes = [query["sql"] for query in queries if query["sql"].lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE"),
        )]
        self.assertEqual(writes, [])
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(ChallengeOccurrence.objects.exists())

    def test_saved_active_promise_keeps_frozen_identity_target_and_progress_after_offer_edit(self):
        definition = self.definition()
        occurrence = self.accepted(definition)
        definition.name = "New catalog name"
        definition.target_value = 25
        definition.save()
        definition.reward_items.all().delete()
        for item in (self.eggs["meshtint-bee"], self.ingredients["base"]):
            QuestRewardItem.objects.create(quest_definition=definition, item=item)
        saved = self.paths()[0]
        self.assertFalse(saved["offer_available"])
        self.assertEqual(saved["name"], "New catalog name")
        self.assertEqual(saved["target"], "25")
        self.assertEqual(saved["attempt"], {
            "id": f"goal:{occurrence.pk}", "name": "The accepted promise", "status": "active",
            "progress": "3", "target": "8", "ends_at": occurrence.ends_at.isoformat(), "retry_available": False,
        })
        self.assertEqual(saved["path"], f"/quests?tab=trials&goal=goal%3A{occurrence.pk}")
        # The accepted goal keeps its enrollment-time reward and retries copy
        # that promise, so the edited pair is not a guaranteed reward for them.
        current = self.paths(species="meshtint-bee", potion="base")[0]
        self.assertFalse(current["offer_available"])
        self.assertIsNone(current["attempt"])
        self.client.force_authenticate(self.sibling)
        fresh = self.paths(species="meshtint-bee", potion="base")[0]
        self.assertTrue(fresh["offer_available"], "A child who never accepted it still sees today's offer.")

    def test_edited_offer_stays_guaranteed_when_a_new_window_can_still_pay_it(self):
        repeatable = self.definition(name="Repeatable discovery", is_repeatable=True)
        quest = Quest.objects.create(
            definition=repeatable, current_progress=10, status="completed",
            end_date=self.now - timedelta(days=1), reward_items_snapshot=snapshot_reward_items(repeatable),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        repeatable.reward_items.filter(item=self.ingredients["fire"]).update(item=self.ingredients["ice"])
        # A completed legacy run of a repeatable offer does not block a new
        # automatic window, which would freeze today's edited reward.
        current = self.paths(potion="ice")[0]
        self.assertTrue(current["offer_available"])
        self.assertIsNone(current["attempt"])

    def test_edited_offer_is_not_guaranteed_after_any_attempt_at_a_saved_one_time_reward(self):
        definition = self.definition()
        self.accepted(definition, expired=True, progress=1)
        definition.reward_items.filter(item=self.ingredients["fire"]).update(item=self.ingredients["ice"])
        saved = self.paths()[0]
        self.assertFalse(saved["offer_available"])
        self.assertTrue(saved["attempt"]["retry_available"])
        current = self.paths(potion="ice")[0]
        self.assertFalse(current["offer_available"], "A retry copies the saved Fire promise, never today's Ice pair.")

    def test_expired_legacy_pair_cannot_override_a_later_automatic_promise(self):
        from apps.quests.goals import list_goals
        from apps.quests.services import QuestService

        definition = self.definition()
        old = Quest.objects.create(
            definition=definition, status="expired", start_date=self.now - timedelta(days=190),
            end_date=self.now - timedelta(days=10), reward_items_snapshot=snapshot_reward_items(definition),
        )
        QuestParticipant.objects.create(quest=old, user=self.child)
        definition.reward_items.filter(item=self.ingredients["fire"]).update(item=self.ingredients["ice"])
        list_goals(self.child)
        goal = ChallengeGoal.objects.get(user=self.child, catalog_definition=definition)
        self.assertEqual({row["item_id"] for row in goal.occurrences.get().snapshot["items"]},
                         {self.eggs["chick"].pk, self.ingredients["ice"].pk})
        definition.reward_items.filter(item=self.ingredients["ice"]).update(item=self.ingredients["fire"])
        row = self.paths()[0]
        # Native enrollment and legacy starts both refuse a second promise.
        goals = list(ChallengeGoal.objects.filter(user=self.child).values_list("pk", flat=True))
        list_goals(self.child)
        self.assertEqual(list(ChallengeGoal.objects.filter(user=self.child).values_list("pk", flat=True)), goals)
        with self.assertRaisesMessage(ValueError, "This challenge progresses automatically"):
            QuestService.start_quest(self.child, definition.pk)
        self.assertEqual((row["attempt"]["id"], row["attempt"]["retry_available"]), (f"legacy:{old.pk}", False))
        self.assertFalse(row["offer_available"],
                         "An expired legacy Fire attempt cannot pay while the accepted goal retains Ice.")
        ice = self.paths(potion="ice")[0]
        self.assertTrue(ice["attempt"]["id"].startswith("goal:"))

    def test_accepted_goal_waiting_for_its_first_window_keeps_its_own_reward_reachable(self):
        definition = self.definition()
        # Enrollment can save the goal before its first window: a non-matching
        # fact sets starts_at after that fact, so no occurrence exists yet.
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, is_catalog=True, catalog_definition=definition,
            name=definition.name, description="", metric="count", target=definition.target_value,
            unit="actions", trigger_filter=definition.trigger_filter, starts_at=self.now,
            ends_at=self.now + timedelta(days=180),
            reward_items=[{"item_id": row.item_id, "quantity": row.quantity} for row in definition.reward_items.all()],
        )
        self.assertFalse(goal.occurrences.exists())
        waiting = self.paths()[0]
        self.assertTrue(waiting["offer_available"], "Its first window will open with this saved reward.")
        self.assertIsNone(waiting["attempt"])
        definition.reward_items.filter(item=self.ingredients["fire"]).update(item=self.ingredients["ice"])
        self.assertFalse(self.paths(potion="ice")[0]["offer_available"])

    def test_superseded_alias_goal_cannot_pay_through_windows_it_will_never_open(self):
        canonical = self.definition(name="Canonical discovery", potion="ice")
        self.accepted(canonical)  # Freezes Chick + Ice on the canonical goal.
        canonical.reward_items.filter(item=self.ingredients["ice"]).update(item=self.ingredients["fire"])
        alias = self.definition(name="Retained alias discovery", is_repeatable=True)
        ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, is_catalog=True, catalog_definition=alias,
            name=alias.name, description="", metric="count", target=alias.target_value, unit="actions",
            trigger_filter=alias.trigger_filter, starts_at=self.now, ends_at=self.now + timedelta(days=180),
            reward_items=[{"item_id": row.item_id, "quantity": row.quantity} for row in alias.reward_items.all()],
        )
        QuestDefinition.objects.filter(pk=alias.pk).update(superseded_by=canonical)
        fire = next(row for row in self.paths() if row["definition_id"] == canonical.pk)
        self.assertFalse(fire["offer_available"],
                         "An alias goal opens no new windows, and the canonical goal froze Ice.")

    def test_definition_made_repeatable_does_not_reopen_a_paid_one_time_goal(self):
        definition = self.definition()
        self.accepted(definition, status="completed", progress=10, awarded_at=self.now)
        QuestDefinition.objects.filter(pk=definition.pk).update(is_repeatable=True)
        # The goal saved repeat_days=0 at enrollment, so no new window opens.
        self.assertFalse(self.paths()[0]["offer_available"])

    def test_definition_made_one_time_keeps_a_repeating_goal_reachable(self):
        definition = self.definition(is_repeatable=True)
        occurrence = self.accepted(definition, status="completed", progress=10, awarded_at=self.now,
                                   expired=True)
        ChallengeGoal.objects.filter(pk=occurrence.goal_id).update(repeat_days=180)
        QuestDefinition.objects.filter(pk=definition.pk).update(is_repeatable=False)
        # The goal keeps its saved 180-day cycle and pays its reward again.
        self.assertTrue(self.paths()[0]["offer_available"])

    def test_expired_saved_attempt_and_latest_retry_use_native_status_without_writes(self):
        definition = self.definition()
        previous = self.accepted(definition, expired=True, progress=4)
        with CaptureQueriesContext(connection) as queries:
            expired = self.paths()[0]
        self.assertEqual(expired["attempt"]["status"], "expired")
        self.assertTrue(expired["attempt"]["retry_available"])
        self.assertEqual(expired["path"], f"/quests?tab=trials&goal=goal%3A{previous.pk}")
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        previous.refresh_from_db()
        self.assertEqual(previous.status, "active")
        retry = ChallengeOccurrence.objects.create(
            goal=previous.goal, retry_of=previous, starts_at=self.now, ends_at=self.now + timedelta(days=180),
            snapshot={**previous.snapshot, "name": "Accepted retry", "target": "7"}, progress=1,
        )
        latest = self.paths()[0]
        self.assertEqual(latest["attempt"]["id"], f"goal:{retry.pk}")
        self.assertEqual(latest["attempt"]["name"], "Accepted retry")
        self.assertEqual(latest["attempt"]["target"], "7")
        self.assertEqual(latest["attempt"]["progress"], "1")
        self.assertFalse(latest["attempt"]["retry_available"])

    def test_withdrawn_definition_keeps_accepted_promise_separate_from_a_new_offer(self):
        definition = self.definition()
        occurrence = self.accepted(definition)
        QuestDefinition.objects.filter(pk=definition.pk).update(is_system=False)
        row = self.paths()[0]
        self.assertFalse(row["offer_available"])
        self.assertEqual(row["attempt"]["id"], f"goal:{occurrence.pk}")
        self.client.force_authenticate(self.sibling)
        self.assertEqual(self.paths(), [])

    def test_completed_history_beyond_trials_window_never_reoffers_or_invents_a_deep_link(self):
        definition = self.definition()
        completed = self.accepted(definition, expired=True, progress=8, status="completed",
                                  completed_at=self.now - timedelta(days=100), awarded_at=self.now - timedelta(days=100))
        for index in range(22):
            other = self.definition(name=f"Other history {index}", species="meshtint-dragon", potion="ice")
            self.accepted(other, expired=True, progress=8, status="completed",
                          completed_at=self.now - timedelta(hours=index), awarded_at=self.now - timedelta(hours=index))
        row = self.paths()[0]
        self.assertFalse(row["offer_available"])
        self.assertEqual(row["attempt"]["id"], f"goal:{completed.pk}")
        self.assertEqual(row["attempt"]["status"], "completed")
        self.assertFalse(row["attempt"]["retry_available"])
        self.assertEqual(row["path"], "/quests?tab=trials")

    def test_only_canonical_whole_system_bundles_advertise_guaranteed_pairs(self):
        good = self.definition(name="Renamed but exact")
        private = self.definition(name="Private same egg")
        QuestDefinition.objects.filter(pk=private.pk).update(is_system=False, created_by=self.parent)
        duplicate = self.definition(name="Ambiguous")
        self.definition(name=duplicate.name)
        alias = self.definition(name="Retired alias")
        QuestDefinition.objects.filter(pk=alias.pk).update(superseded_by=good)
        empty = self.definition(name="Zero reward")
        empty.reward_items.filter(item=self.ingredients["fire"]).update(quantity=0)
        spoofed = self.definition(name="Spoofed typed ingredient")
        spoof = ItemDefinition.objects.create(slug="fake-fire-potion", name="Fire Potion", item_type="potion",
                                             potion_type=self.potions["fire"], metadata={"variant": "fire"})
        spoofed.reward_items.filter(item=self.ingredients["fire"]).update(item=spoof)
        wrong_pair = self.definition(name="Unsupported Bee Fire", species="meshtint-bee")
        self.assertTrue(wrong_pair.reward_items.exists())
        self.assertEqual([row["definition_id"] for row in self.paths()], [good.pk])
        self.assertEqual(self.paths(species="meshtint-bee", potion="base"), [])

    def test_progress_and_names_are_self_scoped_even_with_targeting_query_parameters(self):
        definition = self.definition()
        mine = self.accepted(definition, progress=2)
        self.accepted(definition, user=self.sibling, progress=6)
        self.accepted(definition, user=self.foreign, progress=7)
        for target in [self.sibling.pk, self.foreign.pk]:
            row = self.paths(user_id=target)[0]
            self.assertEqual(row["attempt"]["id"], f"goal:{mine.pk}")
            self.assertEqual(row["attempt"]["progress"], "2")
        self.client.force_authenticate(self.parent)
        self.assertIsNone(self.paths()[0]["attempt"])
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/pets/codex/").status_code, 401)

    def test_projection_queries_do_not_grow_once_per_extra_guaranteed_path(self):
        self.definition()
        with CaptureQueriesContext(connection) as first:
            self.paths()
        for index in range(12):
            self.definition(name=f"Additional exact path {index}")
        with CaptureQueriesContext(connection) as expanded:
            rows = self.paths()
        self.assertEqual(len(rows), 13)
        self.assertLessEqual(len(expanded), len(first) + 2)

    def test_existing_parent_catalog_shape_is_unchanged(self):
        self.definition()
        self.client.force_authenticate(self.parent)
        response = self.client.get("/api/pets/species/catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all("acquisition_challenges" not in potion
                            for species in response.data for potion in species["available_potions"]))

    def test_a_repeated_codex_read_does_not_call_enrollment_or_payout_paths(self):
        self.definition()
        with patch("apps.quests.goals.list_goals", side_effect=AssertionError("materializing list")), \
                patch("apps.quests.goals._catalog_goals", side_effect=AssertionError("enrollment")), \
                patch("apps.quests.goals._occurrence", side_effect=AssertionError("new occurrence")):
            first = self.paths()
            self.assertEqual(self.paths(), first)

    def test_saved_pair_survives_nonidentity_ingredient_metadata_changes(self):
        definition = self.definition()
        occurrence = self.accepted(definition)
        for item in (self.eggs["chick"], self.ingredients["fire"]):
            ItemDefinition.objects.filter(pk=item.pk).update(metadata={**item.metadata, "display_note": "Updated copy"})
        row = self.paths()[0]
        self.assertIsNotNone(row["attempt"])
        self.assertEqual(row["attempt"]["id"], f"goal:{occurrence.pk}")
        # Rebinding frozen identity metadata must not advertise another pair.
        ItemDefinition.objects.filter(pk=self.eggs["chick"].pk).update(metadata={"species": "meshtint-wolf"})
        self.assertEqual(self.paths(), [])

    def test_retired_alias_uses_canonical_outer_metadata_and_frozen_attempt_name(self):
        canonical = self.definition(name="Canonical withdrawn offer")
        self.accepted(canonical)
        alias = self.definition(name="Historical alias")
        occurrence = self.accepted(alias)
        QuestDefinition.objects.filter(pk=alias.pk).update(superseded_by=canonical)
        QuestDefinition.objects.filter(pk=canonical.pk).update(is_system=False, target_value=42)
        self.assertEqual(self.paths(), [{
            "definition_id": canonical.pk, "name": canonical.name, "offer_available": False,
            "target": "42", "duration_days": 180,
            "attempt": {"id": f"goal:{occurrence.pk}", "name": "The accepted promise", "status": "active",
                        "progress": "3", "target": "8", "ends_at": occurrence.ends_at.isoformat(),
                        "retry_available": False},
            "path": f"/quests?tab=trials&goal=goal%3A{occurrence.pk}",
        }])

    def test_alias_cannot_reveal_a_foreign_private_canonical_definition(self):
        foreign_parent = make_family("Private definition family", parents=[{"username": "foreign-definition-parent"}]).parents[0]
        canonical = self.definition(name="Foreign household private title")
        QuestDefinition.objects.filter(pk=canonical.pk).update(is_system=False, created_by=foreign_parent)
        alias = self.definition(name="Old global public alias")
        self.accepted(alias)
        QuestDefinition.objects.filter(pk=alias.pk).update(superseded_by=canonical)
        self.assertEqual(self.paths(), [])

    def test_alias_cannot_reveal_an_orphan_private_canonical_definition(self):
        canonical = self.definition(name="Orphan household private title")
        QuestDefinition.objects.filter(pk=canonical.pk).update(is_system=False, created_by=None)
        alias = self.definition(name="Public alias does not grant private access")
        self.accepted(alias)
        QuestDefinition.objects.filter(pk=alias.pk).update(superseded_by=canonical)
        self.assertEqual(self.paths(), [])

    def test_accepted_alias_keeps_same_family_canonical_visibility(self):
        canonical = self.definition(name="Our household canonical title")
        QuestDefinition.objects.filter(pk=canonical.pk).update(is_system=False, created_by=self.parent)
        alias = self.definition(name="Accepted public alias")
        occurrence = self.accepted(alias)
        QuestDefinition.objects.filter(pk=alias.pk).update(superseded_by=canonical)
        row = self.paths()[0]
        self.assertEqual(row["definition_id"], canonical.pk)
        self.assertEqual(row["name"], canonical.name)
        self.assertFalse(row["offer_available"])
        self.assertEqual(row["attempt"]["id"], f"goal:{occurrence.pk}")
        self.client.force_authenticate(self.sibling)
        self.assertEqual(self.paths(), [])

    def test_each_frozen_pair_keeps_its_own_attempt_when_newer_snapshot_differs(self):
        definition = self.definition()
        old = self.accepted(definition, expired=True, progress=4)
        definition.reward_items.filter(item=self.ingredients["fire"]).update(item=self.ingredients["ice"])
        latest = ChallengeOccurrence.objects.create(
            goal=old.goal, retry_of=old, starts_at=self.now, ends_at=self.now + timedelta(days=180),
            snapshot={**old.snapshot, "name": "Different accepted appearance",
                      "items": snapshot_reward_items(definition)}, progress=1,
        )
        fire = self.paths()[0]
        self.assertFalse(fire["offer_available"])
        self.assertEqual(fire["attempt"]["id"], f"goal:{old.pk}")
        self.assertEqual(fire["attempt"]["progress"], "4")
        self.assertFalse(fire["attempt"]["retry_available"])
        ice = self.paths(potion="ice")[0]
        self.assertTrue(ice["offer_available"])
        self.assertEqual(ice["attempt"]["id"], f"goal:{latest.pk}")
        self.assertEqual(ice["attempt"]["progress"], "1")

    def test_malformed_saved_snapshots_do_not_break_discovery_or_invent_an_attempt(self):
        definition = self.definition()
        occurrence = self.accepted(definition)
        original = occurrence.snapshot
        self.client.raise_request_exception = False
        for snapshot in [[], {**original, "items": 9}, {**original, "name": None},
                         {key: value for key, value in original.items() if key != "target"},
                         {**original, "target": "NaN"}]:
            with self.subTest(snapshot=snapshot):
                ChallengeOccurrence.objects.filter(pk=occurrence.pk).update(snapshot=snapshot)
                row = self.paths()[0]
                self.assertTrue(row["offer_available"])
                self.assertIsNone(row["attempt"])

    def test_prerequisite_completion_uses_native_completed_status_without_requiring_payment(self):
        from apps.quests.milestone_eligibility import prerequisite_completion

        prior = self.definition(name="Completed prerequisite", potion="ice")
        self.accepted(prior, status="completed", progress=8, completed_at=self.now, awarded_at=None)
        gated = self.definition(name="Reading unlocked by completion", prerequisite_quest=prior)
        QuestDefinition.objects.filter(pk=gated.pk).update(trigger_filter={"allowed_triggers": ["reading_logged"]})
        self.assertTrue(prerequisite_completion(self.child, prior.pk)[0])
        self.assertTrue(self.paths()[0]["offer_available"])

    def test_saved_progress_queries_are_batched_across_extra_goals(self):
        self.accepted(self.definition())
        with CaptureQueriesContext(connection) as first:
            self.paths()
        for index in range(12):
            self.accepted(self.definition(name=f"Another accepted path {index}"))
        with CaptureQueriesContext(connection) as expanded:
            rows = self.paths()
        self.assertEqual(len(rows), 13)
        self.assertTrue(all(row["attempt"] is not None for row in rows))
        self.assertLessEqual(len(expanded), len(first) + 2)

    def test_legacy_saved_items_keep_their_pair_when_current_rewards_change(self):
        definition = self.definition()
        quest = Quest.objects.create(
            definition=definition, current_progress=4, end_date=self.now + timedelta(days=10),
            reward_items_snapshot=snapshot_reward_items(definition),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        definition.reward_items.filter(item=self.ingredients["fire"]).update(item=self.ingredients["ice"])
        row = self.paths()[0]
        self.assertFalse(row["offer_available"])
        self.assertEqual(row["attempt"]["id"], f"legacy:{quest.pk}")
        self.assertEqual(row["attempt"]["progress"], "4")
        self.assertEqual(row["path"], f"/quests?tab=trials&goal=legacy%3A{quest.pk}")
        # An active one-time legacy window blocks a new automatic enrollment.
        current = self.paths(potion="ice")[0]
        self.assertFalse(current["offer_available"])
        self.assertIsNone(current["attempt"])
        QuestDefinition.objects.filter(pk=definition.pk).update(is_system=False, created_by=self.parent)
        self.assertEqual(self.paths(), [])

    def test_legacy_null_snapshot_uses_retained_links_but_malformed_snapshot_fails_closed(self):
        definition = self.definition()
        quest = Quest.objects.create(definition=definition, end_date=self.now + timedelta(days=10))
        QuestParticipant.objects.create(quest=quest, user=self.child)
        self.assertEqual(self.paths()[0]["attempt"]["id"], f"legacy:{quest.pk}")
        for snapshot in [[], {"items": "not a list"}, [None], [{"item_id": 2 ** 100, "quantity": 1}]]:
            with self.subTest(snapshot=snapshot):
                Quest.objects.filter(pk=quest.pk).update(reward_items_snapshot=snapshot)
                self.assertIsNone(self.paths()[0]["attempt"])

    def test_completed_legacy_link_respects_the_existing_twenty_row_history_window(self):
        definition = self.definition()
        quest = Quest.objects.create(
            definition=definition, status="completed", start_date=self.now - timedelta(days=30),
            end_date=self.now - timedelta(days=1), current_progress=10,
            reward_items_snapshot=snapshot_reward_items(definition),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        self.assertEqual(self.paths()[0]["path"], f"/quests?tab=trials&goal=legacy%3A{quest.pk}")
        private = self.definition(name="Other saved family history")
        QuestDefinition.objects.filter(pk=private.pk).update(is_system=False, created_by=self.parent)
        for index in range(22):
            other = Quest.objects.create(
                definition=private, status="completed", start_date=self.now - timedelta(hours=index),
                end_date=self.now - timedelta(minutes=1),
            )
            QuestParticipant.objects.create(quest=other, user=self.child)
        row = self.paths()[0]
        self.assertEqual(row["attempt"]["id"], f"legacy:{quest.pk}")
        self.assertFalse(row["offer_available"])
        self.assertEqual(row["path"], "/quests?tab=trials")

    def test_current_badge_skill_and_taxonomy_gates_do_not_revoke_saved_progress(self):
        from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge

        category = SkillCategory.objects.create(name="Discovery reading")
        skill = Skill.objects.create(name="Discovery skill", category=category)
        badge = Badge.objects.create(name="Discovery badge", criteria_type="first_project")
        definition = self.definition(required_skill=skill, required_skill_level=1, required_badge=badge)
        QuestDefinition.objects.filter(pk=definition.pk).update(trigger_filter={"allowed_triggers": ["reading_logged"]})
        self.assertFalse(self.paths()[0]["offer_available"])
        SkillProgress.objects.create(user=self.sibling, skill=skill, level=6)
        UserBadge.objects.create(user=self.sibling, badge=badge)
        self.assertFalse(self.paths()[0]["offer_available"])
        SkillProgress.objects.create(user=self.child, skill=skill, level=1)
        UserBadge.objects.create(user=self.child, badge=badge)
        self.assertTrue(self.paths()[0]["offer_available"])
        occurrence = self.accepted(definition)
        Skill.objects.filter(pk=skill.pk).update(is_retired=True)
        row = self.paths()[0]
        self.assertFalse(row["offer_available"])
        self.assertEqual(row["attempt"]["id"], f"goal:{occurrence.pk}")
        self.assertEqual(row["attempt"]["progress"], "3")

    def test_future_saved_attempt_is_upcoming_and_uses_generic_navigation(self):
        occurrence = self.accepted(self.definition())
        ChallengeOccurrence.objects.filter(pk=occurrence.pk).update(starts_at=self.now + timedelta(days=1))
        row = self.paths()[0]
        self.assertEqual(row["attempt"]["status"], "upcoming")
        self.assertEqual(row["path"], "/quests?tab=trials")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HatcheryDiscoveryProductionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        cls.child = make_family("Actual discovery catalog", children=[{"username": "actual-discovery"}]).children[0]

    def test_all_sixteen_shipped_elemental_challenges_join_the_exact_supported_pairs(self):
        from apps.rpg.catalog_icons import challenge_catalog_icon

        client = APIClient()
        client.force_authenticate(self.child)
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/api/pets/codex/")
        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(len(body["species"]), 15)
        self.assertEqual(sum(len(row["available_potions"]) for row in body["species"]), 31)
        expected = {"chick": ("Nest", 5, 180), "meshtint-wolf": ("Trail", 20, 180),
                    "meshtint-mushroom": ("Grove", 10, 180), "meshtint-dragon": ("Summit", 50, 365),
                    "meshtint-bee": ("Hive", 5, 180), "meshtint-bat": ("Cave", 10, 180),
                    "meshtint-snake": ("Coil", 10, 180), "meshtint-hermit-crab": ("Shore", 10, 180)}
        checked = set()
        for species in body["species"]:
            for potion in species["available_potions"]:
                if potion["slug"] == "base":
                    continue
                with self.subTest(species=species["slug"], potion=potion["slug"]):
                    prefix = "Ember" if potion["slug"] == "fire" else "Frost"
                    suffix, target, days = expected[species["slug"]]
                    self.assertEqual([row["name"] for row in potion["acquisition_challenges"]],
                                     [f"{prefix} {suffix}"])
                    path = potion["acquisition_challenges"][0]
                    self.assertTrue(path["offer_available"])
                    self.assertIsNone(path["attempt"])
                    self.assertEqual((path["target"], path["duration_days"]), (str(target), days))
                    icon = (f"review-{species['slug'].removeprefix('meshtint-')}-{potion['slug']}-acquisition-icon"
                            if suffix in {"Hive", "Cave", "Coil", "Shore"} else f"challenge-{prefix.lower()}-{suffix.lower()}")
                    self.assertEqual(challenge_catalog_icon(QuestDefinition.objects.get(pk=path["definition_id"])), icon)
                    checked.add((species["slug"], potion["slug"]))
        self.assertEqual(len(checked), 16)
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        self.assertFalse(ChallengeGoal.objects.exists())
