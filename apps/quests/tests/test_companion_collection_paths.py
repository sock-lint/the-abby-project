"""Authored companion trails provide supported, deterministic collection goals."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.achievements.models import Skill
from apps.creations.models import CreationDailyCounter
from apps.creations.services import CreationService
from apps.quests.activity import record_activity
from apps.quests.goals import ingest_activity, list_goals, set_pin
from apps.quests.models import ChallengeActivity, ChallengeOccurrence, QuestDefinition
from apps.quests.serializers import QuestDefinitionSerializer
from apps.rpg.catalog_support import item_is_available, species_is_available
from apps.rpg.models import ItemDefinition, UserInventory
from apps.pets.models import PetSpecies
from config.tests.factories import make_family


TRAILS = {
    "Ghost Trail": ("meshtint-ghost-egg", "rare", 10, 180),
    "Wolf Trail": ("meshtint-wolf-egg", "rare", 20, 180),
    "Bomb Trail": ("meshtint-bomb-egg", "rare", 30, 180),
    "Shadow Trail": ("meshtint-shadow-egg", "epic", 25, 180),
    "Dragon Trail": ("meshtint-dragon-egg", "legendary", 50, 365),
}
ALLOWED_TRIGGERS = {
    "chore_complete", "homework_complete", "milestone_complete", "project_complete", "creation_logged",
}


class CompanionCollectionPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())

    def setUp(self):
        family = make_family("Companion trails", children=[
            {"username": "trail-child"}, {"username": "trail-sibling"},
        ])
        self.child, self.sibling = family.children
        self.other = make_family("Other trails", children=[{"username": "trail-outsider"}]).children[0]

    def enroll_trails(self, child=None):
        # Other authored challenges are independent of these deterministic paths.
        QuestDefinition.objects.exclude(name__in=TRAILS).update(is_system=False)
        rows = list_goals(child or self.child)["results"]
        self.assertEqual({row["name"] for row in rows}, set(TRAILS))
        return rows

    def test_authored_paths_cover_every_supported_rare_or_higher_family(self):
        definitions = {row.name: row for row in QuestDefinition.objects.filter(name__in=TRAILS)}
        self.assertEqual(set(definitions), set(TRAILS))
        promised_eggs = set()
        for name, (slug, rarity, target, days) in TRAILS.items():
            definition = definitions[name]
            with self.subTest(trail=name):
                self.assertTrue(definition.is_system)
                self.assertFalse(definition.is_repeatable)
                self.assertIsNone(definition.required_badge_id)
                self.assertEqual((definition.quest_type, definition.target_value, definition.duration_days),
                                 ("collection", target, days))
                self.assertEqual(set(definition.trigger_filter["allowed_triggers"]), ALLOWED_TRIGGERS)
                self.assertEqual((definition.coin_reward, definition.xp_reward), (0, 0))
                rewards = list(definition.reward_items.select_related("item__pet_species", "item__potion_type"))
                self.assertEqual({row.item.slug: row.quantity for row in rewards}, {slug: 1, "base-potion": 1})
                self.assertTrue(all(item_is_available(row.item) for row in rewards))
                egg = next(row.item for row in rewards if row.item.slug == slug)
                self.assertEqual(egg.rarity, rarity)
                promised_eggs.add(egg.pet_species_id)
                wire_items = QuestDefinitionSerializer(definition).data["reward_items"]
                self.assertEqual({row["item"] for row in wire_items}, {row.item_id for row in rewards})
        supported = {species.pk for species in PetSpecies.objects.filter(rarity__in=["rare", "epic", "legendary"])
                     if species_is_available(species)}
        self.assertEqual(promised_eggs, supported)

    @patch("apps.rpg.services.DropService.process_drops", return_value=[])
    def test_meaningful_facts_award_each_exact_egg_and_potion_once(self, _drops):
        self.enroll_trails()
        triggers = ["chore_complete", "homework_complete", "milestone_complete", "project_complete"]
        for index in range(50):
            trigger = triggers[index % len(triggers)]
            ingest_activity(self.child, trigger, f"trail-source-{index}", trigger)
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=self.child))
        self.assertEqual(len(occurrences), len(TRAILS))
        for occurrence in occurrences:
            with self.subTest(trail=occurrence.snapshot["name"]):
                self.assertEqual(occurrence.status, "completed")
                self.assertIsNotNone(occurrence.awarded_at)
                self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
                expected_egg = ItemDefinition.objects.get(slug=TRAILS[occurrence.snapshot["name"]][0])
                self.assertEqual({row["item_id"]: row["quantity"] for row in occurrence.reward_receipt["items"]},
                                 {expected_egg.pk: 1, ItemDefinition.objects.get(slug="base-potion").pk: 1})
        before = {row.pk: row.reward_receipt for row in occurrences}
        # The same source and fresh activity after completion cannot rearm a trail.
        ingest_activity(self.child, "chore_complete", "trail-source-0", "chore_complete")
        ingest_activity(self.child, "chore_complete", "extra-after-completion", "chore_complete")
        list_goals(self.child)
        self.assertEqual({row.pk: row.reward_receipt for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}, before)
        for slug, _rarity, _target, _days in TRAILS.values():
            self.assertEqual(UserInventory.objects.get(user=self.child, item__slug=slug).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="base-potion").quantity, 5)

    def test_creation_daily_limit_and_replay_cannot_fast_forward_a_trail(self):
        self.enroll_trails()
        skill = Skill.objects.filter(category__name="Art & Crafts").first()
        self.assertIsNotNone(skill)
        with patch("apps.rpg.services.safe_game_loop_call"):
            creations = [CreationService.log_creation(self.child, image="synthetic-trail.jpg", primary_skill_id=skill.pk)
                         for _ in range(3)]
        self.assertEqual(CreationDailyCounter.objects.get(user=self.child).count, 3)
        facts = ChallengeActivity.objects.filter(user=self.child, trigger_type="creation_logged").order_by("pk")
        self.assertEqual([fact.context["catalog_eligible"] for fact in facts], [True, True, False])
        record_activity(self.child, "creation_logged", {"creation_id": creations[-1].pk, "catalog_eligible": True})
        ingest_activity(self.child, "habit_log", "micro-tap", "habit_log")
        ingest_activity(self.child, "clock_out", "split-clock", "clock_out", context={"duration_minutes": 1})
        for occurrence in ChallengeOccurrence.objects.filter(goal__user=self.child):
            self.assertEqual((occurrence.progress, occurrence.status), (2, "active"))
            self.assertIsNone(occurrence.awarded_at)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item__slug__in=[row[0] for row in TRAILS.values()]).exists())

    def test_sibling_and_other_family_cannot_receive_or_pin_another_childs_progress(self):
        child_rows = self.enroll_trails()
        self.enroll_trails(self.sibling)
        self.enroll_trails(self.other)
        ingest_activity(self.child, "chore_complete", "owned-fact", "chore_complete")
        for user in (self.sibling, self.other):
            with self.subTest(user=user.username):
                self.assertEqual({row["progress"] for row in list_goals(user)["results"]}, {"0"})
                self.assertFalse(UserInventory.objects.filter(user=user).exists())
                with self.assertRaisesRegex(ValueError, "Challenge not found"):
                    set_pin(user, child_rows[0]["id"])
