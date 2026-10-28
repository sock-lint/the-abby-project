"""Focus Master describes its actual damage rule without rewriting acceptance."""
from copy import deepcopy
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import SkillProgress
from apps.quests.goals import _amount, ingest_activity
from apps.quests.models import ChallengeContribution, ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.rewards.models import CoinLedger
from apps.rpg.models import UserInventory
from config.tests.factories import make_family


OLD_DESCRIPTION = "Clock 20 hours of focused project work to defeat the distraction monster!"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FocusMasterDescriptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        household = make_family(
            "Focus description household",
            parents=[{"username": "focus-description-parent"}],
            children=[{"username": "focus-description-accepted"}, {"username": "focus-description-new"}],
        )
        cls.parent = household.parents[0]
        cls.accepted_child, cls.new_child = household.children
        # Establish the loader's ordinary starter-cover gifts before taking
        # reward baselines; the subsequent reload must be idempotent.
        call_command("loadrpgcontent", stdout=StringIO())
        cls.definition = QuestDefinition.objects.get(
            name="Focus Master", is_system=True, created_by=None, superseded_by=None,
        )

    def catalog_row(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.get("/api/quests/catalog/")
        self.assertEqual(response.status_code, 200)
        return next(row for row in response.data if row["id"] == self.definition.pk)

    def challenge_row(self, child):
        client = APIClient()
        client.force_authenticate(child)
        response = client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        return next(row for row in response.data["results"] if row["name"] == "Focus Master")

    def assert_damage_description(self, description):
        self.assertIn("200 damage", description)
        self.assertIn("tracked project work", description)
        self.assertIn("rounded down for each completed session", description)
        self.assertNotIn("20 hours", description)

    def test_loaded_catalog_and_new_challenge_describe_actual_split_session_damage(self):
        row = self.catalog_row()
        self.assert_damage_description(row["description"])
        self.assertEqual(
            (row["quest_type"], row["target_value"], row["duration_days"],
             row["trigger_filter"], row["coin_reward"], row["xp_reward"], row["reward_items"]),
            ("boss", 200, 14, {"allowed_triggers": ["clock_out"]}, 100, 150, []),
        )
        self.assertEqual(
            list(self.definition.skill_tags.order_by("skill__name").values_list(
                "skill__category__name", "skill__name", "xp_weight",
            )),
            [("Life Skills", "Persistence", 2), ("Life Skills", "Time Management", 2)],
        )

        # The old hours claim fails for split sessions even though total work
        # time is identical. Exercise the actual automatic damage calculation.
        snapshot = {"metric": "damage", "filter": row["trigger_filter"]}
        for minutes, sessions, damage in ((10, 120, 120), (30, 40, 200), (60, 20, 200)):
            with self.subTest(minutes=minutes, sessions=sessions):
                activity = SimpleNamespace(trigger_type="clock_out", context={"duration_minutes": minutes})
                self.assertEqual(_amount(snapshot, activity) * sessions, Decimal(damage))

        projected = self.challenge_row(self.new_child)
        self.assertEqual(projected["description"], row["description"])
        self.assertEqual((projected["metric"], projected["target"], projected["unit"]),
                         ("damage", "200", "damage"))
        self.assertEqual((projected["rewards"]["coins"], projected["rewards"]["xp"]), (100, 150))

    def test_default_reload_keeps_accepted_description_progress_and_reward_promises(self):
        # Model the definition served before this wording correction, then let
        # normal factual ingestion create the child's accepted modern window.
        self.definition.description = OLD_DESCRIPTION
        self.definition.save(update_fields=["description"])
        ingest_activity(
            self.accepted_child, "focus-description-test", "completed-session", "clock_out",
            context={"duration_minutes": 10},
        )
        goal = ChallengeGoal.objects.get(user=self.accepted_child, catalog_definition=self.definition)
        occurrence = ChallengeOccurrence.objects.get(goal=goal)
        self.assertEqual((occurrence.progress, occurrence.snapshot["description"]), (1, OLD_DESCRIPTION))
        self.assertEqual((occurrence.snapshot["coins"], occurrence.snapshot["xp"]), (100, 150))
        accepted_goal = ChallengeGoal.objects.filter(pk=goal.pk).values().get()
        accepted_window = deepcopy(ChallengeOccurrence.objects.filter(pk=occurrence.pk).values().get())
        contributions = list(ChallengeContribution.objects.filter(occurrence=occurrence).order_by("pk").values())
        balances = self.saved_rewards()

        call_command("loadrpgcontent", stdout=StringIO())

        catalog = self.catalog_row()
        self.assert_damage_description(catalog["description"])
        retained = self.challenge_row(self.accepted_child)
        self.assertEqual((retained["description"], retained["progress"]), (OLD_DESCRIPTION, "1"))
        self.assertEqual((retained["rewards"]["coins"], retained["rewards"]["xp"]), (100, 150))
        self.assertEqual(ChallengeGoal.objects.filter(pk=goal.pk).values().get(), accepted_goal)
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=occurrence.pk).values().get(), accepted_window)
        self.assertEqual(list(ChallengeContribution.objects.filter(occurrence=occurrence).order_by("pk").values()),
                         contributions)
        self.assertEqual(self.saved_rewards(), balances)
        self.assertEqual(self.challenge_row(self.new_child)["description"], catalog["description"])

    def saved_rewards(self):
        return {
            "coins": list(CoinLedger.objects.filter(user=self.accepted_child).order_by("pk").values()),
            "xp": list(SkillProgress.objects.filter(user=self.accepted_child).order_by("pk").values()),
            "inventory": list(UserInventory.objects.filter(user=self.accepted_child).order_by("pk").values()),
        }
