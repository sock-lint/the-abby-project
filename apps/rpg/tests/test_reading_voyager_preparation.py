"""The selected policy can be prepared privately without activating its rules."""
from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory
from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.publication import _snapshot
from apps.rpg.content.reading_voyager import prepare_reading_voyager
from apps.rpg.models import ContentPackEntry, ContentPackPublication, ItemDefinition, RPGContentDraft, RPGContentOverride, UserInventory
from config.tests.factories import make_family


CURRENT_COPY = (
    "Complete 20 daily Reading Adventures within 45 days. Ten newly logged reading or listening minutes "
    "counts once each family-local day. Celebrate your reading rhythm with the Bookworm title."
)
PROPOSED_COPY = (
    "Unlock by completing Reading Companion and reaching Reading Comprehension level 1. "
    "Complete 20 daily Reading Adventures within 56 days after this challenge opens. "
    "Each Adventure needs ten newly logged reading or listening minutes and counts once each family-local day. "
    "Earn the Bookworm title."
)


class ReadingVoyagerPreparationTests(TestCase):
    def setUp(self):
        household = make_family("Designers", parents=[{"username": "designer", "is_staff": True}],
                                children=[{"username": "reader"}])
        self.family, self.actor, self.child = household.family, household.parents[0], household.children[0]
        category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(category=category, name="Reading Comprehension")
        self.title = ItemDefinition.objects.create(slug="title-bookworm", name="Bookworm", item_type="cosmetic_title",
                                                   rarity="uncommon", coin_value=15, metadata={"text": "Bookworm"})
        self.companion = QuestDefinition.objects.create(name="Reading Companion", description=("Complete 3 daily Reading Adventures within 14 days. Each Adventure needs ten newly logged reading or listening minutes "
                "in your family's day. Meet a Chick with an egg, a Base potion and two Birdseed."), is_system=True,
            quest_type="collection", target_value=3, duration_days=14, coin_reward=0, xp_reward=20,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        self.voyager = QuestDefinition.objects.create(name="Reading Voyager", description=CURRENT_COPY, is_system=True,
            quest_type="collection", target_value=20, duration_days=45, coin_reward=0, xp_reward=50,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        QuestSkillTag.objects.create(quest_definition=self.voyager, skill=self.skill, xp_weight=1)
        QuestSkillTag.objects.create(quest_definition=self.companion, skill=self.skill, xp_weight=1)
        chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        base = PotionType.objects.create(slug="base", name="Base")
        for item, quantity in (
            (ItemDefinition.objects.create(slug="base-potion", name="Base Potion", item_type="potion", potion_type=base,
                metadata={"variant": "base"}), 1),
            (ItemDefinition.objects.create(slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=chick,
                metadata={"species": "chick"}), 1),
            (ItemDefinition.objects.create(slug="food-birdseed", name="Birdseed", item_type="food", food_species=chick,
                metadata={"growth": 5, "food_type": "birdseed"}), 2),
        ):
            QuestRewardItem.objects.create(quest_definition=self.companion, item=item, quantity=quantity)
        QuestRewardItem.objects.create(quest_definition=self.voyager, item=self.title, quantity=1)

    def assert_no_prepared_rows(self):
        self.assertEqual(RPGContentDraft.objects.count(), 0)
        self.assertEqual(ContentPackPublication.objects.count(), 0)
        self.assertEqual(RPGContentOverride.objects.count(), 0)

    def test_prepares_untimed_companion_and_gated_voyager_together(self):
        result = prepare_reading_voyager(self.actor)
        edits = {row["object_id"]: row["values"] for row in result["changes"]}
        self.assertEqual(set(edits), {self.companion.pk, self.voyager.pk})
        self.assertIsNone(edits[self.companion.pk]["duration_days"])
        self.assertIn("no deadline", edits[self.companion.pk]["description"].lower())
        self.assertEqual(edits[self.voyager.pk]["duration_days"], 56)
        self.companion.refresh_from_db()
        self.assertEqual(self.companion.duration_days, 14)
        self.assertIsNone(result["published_at"])

    def test_reward_value_drift_requires_a_new_review(self):
        self.title.coin_value = 100
        self.title.save(update_fields=["coin_value"])
        with self.assertRaisesMessage(ContentPackError, "Bookworm reward differs"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_prepares_exact_private_preview_and_preserves_catalog_and_accepted_work(self):
        start = timezone.now()
        goal = ChallengeGoal.objects.create(user=self.child, family=self.family, catalog_definition=self.voyager,
            is_catalog=True, name="Reading Voyager", description=CURRENT_COPY, metric="count", target=20,
            unit="actions", trigger_filter={"allowed_triggers": ["reading_logged"]}, timezone_name="America/Phoenix",
            starts_at=start, ends_at=start + timedelta(days=45), coin_reward=0, xp_reward=50,
            skill_tags=[{"skill_id": self.skill.pk, "xp_weight": 1}], reward_items=[{"item_id": self.title.pk, "quantity": 1}])
        ChallengeOccurrence.objects.create(goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
            snapshot={"name": "Reading Voyager", "target": "20", "items": [{"item_id": self.title.pk, "quantity": 1}]}, progress=7)
        UserInventory.objects.create(user=self.child, item=self.title, quantity=1)
        before_catalog = _snapshot(self.family)
        before_goals = list(ChallengeGoal.objects.values())
        before_occurrences = list(ChallengeOccurrence.objects.values())
        ledger_count = CoinLedger.objects.count()

        result = prepare_reading_voyager(self.actor)

        self.assertEqual(result["resolved_ids"], {"voyager": self.voyager.pk, "companion": self.companion.pk,
                                                 "reading_skill": self.skill.pk, "bookworm_title": self.title.pk})
        self.assertEqual(result["changes"][1:], [{"section": "quests", "object_id": self.voyager.pk,
            "key": "reading-voyager", "values": {"duration_days": 56, "description": PROPOSED_COPY,
                "prerequisite_quest": self.companion.pk, "required_skill": self.skill.pk, "required_skill_level": 1}}])
        self.assertTrue(result["preparation_only"])
        self.assertIsNone(result["published_at"])
        self.assertIsNone(result["preview"]["published_at"])
        self.assertIsNone(result["simulation"])
        self.assertEqual(result["revision"], 2)
        self.assertTrue(result["preview"]["preview_id"])
        self.assertEqual(len(result["preview"]["content_digest"]), 64)
        self.assertEqual(_snapshot(self.family), before_catalog)
        self.assertEqual(list(ChallengeGoal.objects.values()), before_goals)
        self.assertEqual(list(ChallengeOccurrence.objects.values()), before_occurrences)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.title).quantity, 1)
        self.assertEqual(CoinLedger.objects.count(), ledger_count)
        self.assertEqual(RPGContentOverride.objects.count(), 0)
        self.assertEqual(RPGContentDraft.objects.count(), 1)
        self.assertEqual(ContentPackPublication.objects.count(), 1)

    def test_refuses_expected_old_scalar_drift_before_creating_a_draft(self):
        for field, value in (("duration_days", 49), ("target_value", 19), ("coin_reward", 1),
                             ("xp_reward", 51), ("description", "Different promise"), ("is_repeatable", True),
                             ("trigger_filter", {"allowed_triggers": ["chore_complete"]})):
            old = getattr(self.voyager, field)
            QuestDefinition.objects.filter(pk=self.voyager.pk).update(**{field: value})
            with self.subTest(field=field), self.assertRaisesMessage(ContentPackError, "differs"):
                prepare_reading_voyager(self.actor)
            self.assert_no_prepared_rows()
            QuestDefinition.objects.filter(pk=self.voyager.pk).update(**{field: old})

    def test_refuses_existing_authored_gate_drift(self):
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(prerequisite_quest=self.companion)
        with self.assertRaisesMessage(ContentPackError, "differs"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_refuses_reward_quantity_or_skill_weight_drift(self):
        reward = self.voyager.reward_items.get()
        reward.quantity = 2
        reward.save()
        with self.assertRaisesMessage(ContentPackError, "reward"):
            prepare_reading_voyager(self.actor)
        reward.quantity = 1
        reward.save()
        self.voyager.skill_tags.update(xp_weight=2)
        with self.assertRaisesMessage(ContentPackError, "skill"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_companion_reward_drift_refuses_before_private_draft_creation(self):
        link = self.companion.reward_items.get(item__slug="food-birdseed")
        link.quantity = 1
        link.save()
        with self.assertRaisesMessage(ContentPackError, "Companion item rewards"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()
        link.quantity = 2
        link.save()
        self.companion.skill_tags.update(xp_weight=2)
        with self.assertRaisesMessage(ContentPackError, "Companion skill rewards"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_starter_types_and_acquisition_bindings_refuse_drift_before_draft_creation(self):
        changes = [
            ("chick-egg", {"item_type": "food"}),
            ("base-potion", {"item_type": "food"}),
            ("food-birdseed", {"item_type": "consumable"}),
            ("chick-egg", {"pet_species_id": None}),
            ("chick-egg", {"metadata": {"species": "other"}}),
            ("base-potion", {"potion_type_id": None}),
            ("base-potion", {"metadata": {"variant": "fire"}}),
            ("food-birdseed", {"food_species_id": None}),
            ("food-birdseed", {"metadata": {"food_type": "birdseed", "growth": 30}}),
            ("food-birdseed", {"metadata": {"food_type": "fish", "growth": 5}}),
        ]
        for slug, values in changes:
            with self.subTest(slug=slug, values=values), transaction.atomic():
                ItemDefinition.objects.filter(slug=slug).update(**values)
                with self.assertRaises(ContentPackError):
                    prepare_reading_voyager(self.actor)
                self.assert_no_prepared_rows()
                transaction.set_rollback(True)

    def test_starter_pair_must_still_hatch_with_the_promised_base_potion(self):
        chick = PetSpecies.objects.get(slug="chick")
        fire = PotionType.objects.create(slug="fire", name="Fire")
        chick.available_potions.set([fire])
        with self.assertRaisesMessage(ContentPackError, "starter"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_refuses_ambiguous_global_target_or_predecessor(self):
        for original in (self.voyager, self.companion):
            duplicate = QuestDefinition.objects.create(name=original.name, description="Duplicate", is_system=True,
                quest_type="collection", target_value=3)
            with self.subTest(name=original.name), self.assertRaisesMessage(ContentPackError, "unique"):
                prepare_reading_voyager(self.actor)
            self.assert_no_prepared_rows()
            duplicate.delete()

    def test_private_names_are_not_adopted_as_global_references(self):
        self.voyager.is_system = False
        self.voyager.created_by = self.actor
        self.voyager.save()
        with self.assertRaisesMessage(ContentPackError, "unique"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_refuses_missing_named_skill_or_title(self):
        self.skill.name = "Another skill"
        self.skill.save()
        with self.assertRaisesMessage(ContentPackError, "unique"):
            prepare_reading_voyager(self.actor)
        self.skill.name = "Reading Comprehension"
        self.skill.save()
        self.title.slug = "another-title"
        self.title.save()
        with self.assertRaisesMessage(ContentPackError, "unique"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_requires_active_staff_parent_with_family(self):
        for field, value in (("is_staff", False), ("is_active", False), ("role", "child"), ("family", None)):
            old = getattr(self.actor, field)
            setattr(self.actor, field, value)
            with self.subTest(field=field), self.assertRaises(ContentPackError):
                prepare_reading_voyager(self.actor)
            self.assert_no_prepared_rows()
            setattr(self.actor, field, old)

    def test_foreign_catalog_ownership_rolls_back_draft(self):
        other = make_family("Other designers").family
        ContentPackEntry.objects.create(pack="other-owner", family=other, kind="questdefinition", key="voyager",
                                       model_label="quests.questdefinition", object_id=self.voyager.pk)
        with self.assertRaisesMessage(ContentPackError, "another family"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()

    def test_active_legacy_guard_rolls_back_draft_and_preserves_accepted_items(self):
        legacy = Quest.objects.create(definition=self.voyager, end_date=timezone.now() + timedelta(days=45))
        with self.assertRaisesMessage(ContentPackError, "active legacy"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()
        legacy.refresh_from_db()
        self.assertIsNone(legacy.reward_items_snapshot)

    def test_active_companion_legacy_conflict_rolls_back_both_edits(self):
        Quest.objects.create(definition=self.companion, end_date=timezone.now() + timedelta(days=14))
        with self.assertRaisesMessage(ContentPackError, "active legacy"):
            prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()
        self.companion.refresh_from_db()
        self.assertEqual(self.companion.duration_days, 14)

    def test_preview_failure_rolls_back_private_draft_and_never_publishes(self):
        with patch("apps.rpg.content.reading_voyager.preview_draft", side_effect=ContentPackError("preview rejected")):
            with self.assertRaisesMessage(ContentPackError, "preview rejected"):
                prepare_reading_voyager(self.actor)
        self.assert_no_prepared_rows()
        self.voyager.refresh_from_db()
        self.assertEqual(self.voyager.duration_days, 45)

    def test_command_requires_an_explicit_actor_and_outputs_review_identifiers(self):
        with self.assertRaises(CommandError):
            call_command("prepare_reading_voyager", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("prepare_reading_voyager", actor_id=999999, stdout=StringIO())
        self.actor.is_staff = False
        self.actor.save(update_fields=["is_staff"])
        with self.assertRaisesMessage(CommandError, "staff parent"):
            call_command("prepare_reading_voyager", actor_id=self.actor.pk, stdout=StringIO())
        self.assert_no_prepared_rows()
        self.actor.is_staff = True
        self.actor.save(update_fields=["is_staff"])
        output = StringIO()
        call_command("prepare_reading_voyager", actor_id=self.actor.pk, stdout=output)
        result = json.loads(output.getvalue())
        self.assertTrue(result["preparation_only"])
        self.assertTrue(result["id"])
        self.assertTrue(result["preview"]["preview_id"])
        self.assertEqual(result["resolved_ids"]["voyager"], self.voyager.pk)
        self.voyager.refresh_from_db()
        self.assertEqual(self.voyager.duration_days, 45)
