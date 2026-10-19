"""Daily reading receipts unlock companions without extra log opportunities."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.services import PetService
from apps.quests.activity import record_activity, resolve_activity
from apps.quests.goals import create_goal, list_goals
from apps.quests.models import ChallengeActivity, ChallengeOccurrence, DailyBonus, QuestDefinition
from apps.reading.models import ReadingBook, ReadingDailyReward
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


NOW = datetime(2026, 10, 18, 1, tzinfo=datetime_timezone.utc)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingChallengeReceiptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with patch("django.utils.timezone.now", return_value=NOW):
            ContentPack("content/rpg/initial").load()
            family = make_family("Reading path", parents=[{"username": "reading-path-parent"}],
                                 children=[{"username": "reading-path-child"}, {"username": "reading-path-sibling"}])
            cls.parent = family.parents[0]
            cls.child, cls.sibling = family.children
            family.family.timezone = "America/Los_Angeles"
            family.family.save(update_fields=["timezone"])
            cls.book = ReadingBook.objects.create(user=cls.child, title="Private title", client_request_id=uuid4(), create_payload={})
            cls.definition = QuestDefinition.objects.create(
                name="Daily reading receipt", quest_type="collection", target_value=3, duration_days=14,
                trigger_filter={"allowed_triggers": ["reading_logged"]}, is_system=True,
            )
            cls.old_definition = QuestDefinition.objects.create(
                name="Existing unfiltered promise", quest_type="collection", target_value=3, duration_days=14,
                is_system=True,
            )

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def session(self, minutes=10, request_id=None, **extra):
        return self.client.post("/api/reading-sessions/", {
            "book": self.book.pk, "duration_minutes": minutes,
            "client_request_id": str(request_id or uuid4()), **extra,
        }, format="json")

    def test_only_awarded_receipt_is_a_source_and_private_context_cannot_change_it(self):
        partial = self.session(4)
        self.assertEqual(partial.status_code, 201, partial.data)
        daily = ReadingDailyReward.objects.get(user=self.child)
        self.assertIsNone(resolve_activity(self.child, "reading_logged", {"reading_reward_id": daily.pk}))
        self.assertIsNone(resolve_activity(self.child, "reading_logged", {"session_id": partial.data["id"]}))
        awarded = self.session(6, reflection="Private reading reflection")
        self.assertEqual(awarded.status_code, 201, awarded.data)
        daily.refresh_from_db()
        source = resolve_activity(self.child, "reading_logged", {
            "reading_reward_id": daily.pk, "duration_minutes": 600, "reflection": "Untrusted prose",
        })
        self.assertIsNotNone(source)
        self.assertEqual((source["source_type"], source["source_id"]), ("reading_logged", str(daily.pk)))
        self.assertEqual(source["occurred_at"], daily.awarded_at)
        self.assertEqual(source["occurred_on"].isoformat(), "2026-10-17")
        self.assertEqual(source["context"], {})
        self.assertIsNone(resolve_activity(self.sibling, "reading_logged", {"reading_reward_id": daily.pk}))
        self.assertIsNone(resolve_activity(self.child, "reading_logged", {"reading_reward_id": daily.pk + 999}))
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type="reading_logged")
        self.assertNotIn("Private", str(fact.context))

    def test_extra_logs_corrections_deletion_and_source_replay_keep_one_daily_contribution(self):
        request_id = uuid4()
        awarded = self.session(request_id=request_id)
        self.assertEqual(awarded.status_code, 201, awarded.data)
        daily = ReadingDailyReward.objects.get(user=self.child)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=self.definition)
        self.assertEqual(occurrence.progress, 1)
        old = ChallengeOccurrence.objects.get(goal__catalog_definition=self.old_definition)
        self.assertEqual(old.progress, 0)
        changed = self.client.patch(f"/api/reading-sessions/{awarded.data['id']}/", {
            "duration_minutes": 0, "reflection": "Corrected reflection",
        }, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        deleted = self.client.delete(f"/api/reading-sessions/{awarded.data['id']}/")
        self.assertEqual(deleted.status_code, 204)
        retry = self.session(request_id=request_id)
        self.assertEqual(retry.status_code, 201, retry.data)
        self.assertIsNone(retry.data["reading_reward"])
        self.assertEqual(self.session(600).status_code, 201)
        record_activity(self.child, "reading_logged", {"reading_reward_id": daily.pk})
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 1)
        self.assertEqual(ChallengeActivity.objects.filter(user=self.child, trigger_type="reading_logged").count(), 1)
        self.assertFalse(DailyBonus.objects.filter(user=self.child).exists())

    def test_new_catalog_offer_does_not_replay_preexisting_awarded_receipts(self):
        response = self.session()
        self.assertEqual(response.status_code, 201, response.data)
        receipt = ReadingDailyReward.objects.get(user=self.child)
        ChallengeActivity.objects.filter(user=self.child, trigger_type="reading_logged").delete()
        later = NOW + timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=later):
            definition = QuestDefinition.objects.create(
                name="New reading offer", quest_type="collection", target_value=1, duration_days=14,
                trigger_filter={"allowed_triggers": ["reading_logged"]}, is_system=True,
            )
            record_activity(self.child, "reading_logged", {"reading_reward_id": receipt.pk})
            list_goals(self.child)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.progress, 0)
        self.assertIsNone(occurrence.awarded_at)

    def test_next_family_day_counts_while_same_day_across_utc_midnight_does_not(self):
        first = NOW - timedelta(hours=2)
        for at in (first, NOW, NOW + timedelta(hours=7)):
            with patch("django.utils.timezone.now", return_value=at):
                self.assertEqual(self.session().status_code, 201)
        self.assertEqual(ReadingDailyReward.objects.filter(user=self.child, awarded_at__isnull=False).count(), 2)
        self.assertEqual(ChallengeActivity.objects.filter(user=self.child, trigger_type="reading_logged").count(), 2)

    def test_parent_count_goal_backfills_saved_receipt_after_session_deletion_once(self):
        awarded = self.session()
        self.assertEqual(awarded.status_code, 201)
        self.client.delete(f"/api/reading-sessions/{awarded.data['id']}/")
        # Exercise the source scan itself, as for a receipt earned before
        # reading facts were introduced, rather than reusing today's fact.
        ChallengeActivity.objects.filter(user=self.child, trigger_type="reading_logged").delete()
        occurrence = create_goal(self.parent, self.child, {
            "name": "Reading days", "trigger_type": "reading_logged", "metric": "count", "target": Decimal(2),
            "unit": "actions", "period": "this_week", "repeat_weekly": False,
            "coin_reward": 0, "xp_reward": 0, "skill_tags": [],
        })
        self.assertEqual(occurrence.progress, 1)
        list_goals(self.child)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 1)


class ReadingCompanionContentTests(ReadingChallengeReceiptTests):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with patch("django.utils.timezone.now", return_value=NOW):
            ContentPack("content/rpg/bundled/reading-adventures", namespace="reading-adventures-").load()

    def test_three_daily_adventures_grant_supported_hatch_ingredients_and_weekly_care(self):
        for day in range(5):
            with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=day)):
                response = self.session()
                self.assertEqual(response.status_code, 201, response.data)
        starter = ChallengeOccurrence.objects.get(goal__catalog_definition__name="Reading Companion")
        routine = ChallengeOccurrence.objects.get(goal__catalog_definition__name="Reading Routine")
        self.assertEqual((starter.status, routine.status), ("completed", "completed"))
        self.assertEqual((starter.reward_receipt["coins"], routine.reward_receipt["coins"]), (0, 0))
        egg = ItemDefinition.objects.get(slug="chick-egg")
        potion = ItemDefinition.objects.get(slug="base-potion")
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=4)):
            incubation, started = PetService.start_incubation(self.child, egg.pk, potion.pk, uuid4())
        self.assertTrue(started)
        self.assertIsNone(incubation.pet_id)
        self.assertEqual((incubation.ready_at - incubation.started_at).total_seconds(), 86400)
        with patch("django.utils.timezone.now", return_value=incubation.ready_at):
            _, pet, hatched = PetService.hatch_incubation(self.child, incubation.pk)
        self.assertTrue(hatched)
        self.assertEqual((pet.species.slug, pet.potion.slug), ("chick", "base"))
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="food-birdseed").quantity, 4)
        self.assertFalse(UserInventory.objects.filter(user=self.sibling, item=egg).exists())

    def test_pack_reloads_preserve_accepted_promises_and_has_no_new_coin_payouts(self):
        self.session()
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition__name="Reading Companion")
        snapshot = occurrence.snapshot
        ContentPack("content/rpg/bundled/reading-adventures", namespace="reading-adventures-").load()
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, snapshot)
        definitions = QuestDefinition.objects.filter(name__in=["Reading Companion", "Reading Routine", "Reading Voyager"])
        self.assertEqual(definitions.count(), 3)
        self.assertEqual(set(definitions.values_list("coin_reward", flat=True)), {0})
