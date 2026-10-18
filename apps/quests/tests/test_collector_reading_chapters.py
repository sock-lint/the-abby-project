"""Reading chapters give collectors a bounded next goal without trip farming."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Badge, UserBadge
from apps.quests.activity import record_activity
from apps.quests.goals import list_goals, set_pin
from apps.quests.models import ChallengeActivity, ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.reading.models import ReadingBook, ReadingDailyReward
from apps.rewards.models import CoinLedger
from apps.rpg.catalog_support import item_is_available
from apps.rpg.content.loader import ContentPack
from apps.rpg.content.validation import validate_content
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


NOW = datetime(2026, 10, 20, 12, tzinfo=datetime_timezone.utc)
PACK = "content/rpg/packs/collector-reading-2026"
NAMESPACE = "collector-reading-2026-"
CHAPTERS = {
    "Collector's Reading: Fresh Pages": (5, "Full Ark", "title-pagefinder"),
    "Collector's Reading: Far Horizons": (10, "Collector's Reading: Fresh Pages Complete", "frame-far-horizons"),
    "Collector's Reading: Living Atlas": (20, "Collector's Reading: Far Horizons Complete", "title-living-atlas"),
}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CollectorReadingChapterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with patch("django.utils.timezone.now", return_value=NOW):
            call_command("loadrpgcontent", stdout=StringIO())
            call_command("loadrpgcontent", pack=PACK, namespace=NAMESPACE, stdout=StringIO())

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=NOW)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)
        family = make_family("Collector readers", children=[
            {"username": "collector-reader"}, {"username": "collector-sibling"},
        ])
        self.child, self.sibling = family.children
        self.other = make_family("Other collectors", children=[{"username": "collector-outsider"}]).children[0]
        self.book = ReadingBook.objects.create(
            user=self.child, title="A new horizon", client_request_id=uuid4(), create_payload={},
        )
        # Isolate authored chapter behavior from independent baseline rewards.
        QuestDefinition.objects.exclude(name__in=CHAPTERS).update(is_system=False)
        Badge.objects.exclude(name__in=["Full Ark", *(f"{name} Complete" for name in CHAPTERS)]).delete()
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def unlock(self, user=None):
        return UserBadge.objects.create(user=user or self.child, badge=Badge.objects.get(name="Full Ark"))

    def read(self, day=0, minutes=10, **extra):
        self.clock.return_value = NOW + timedelta(days=day)
        response = self.client.post("/api/reading-sessions/", {
            "book": self.book.pk, "duration_minutes": minutes, "client_request_id": str(uuid4()), **extra,
        }, format="json")
        self.assertIn(response.status_code, (200, 201), response.data)
        return response

    def chapters(self, user=None):
        return {row["name"]: row for row in list_goals(user or self.child)["results"] if row["name"] in CHAPTERS}

    def test_authored_chapters_are_sequential_supported_cosmetic_goals(self):
        validate_content(ContentPack(Path(settings.BASE_DIR) / PACK)._parse_all(), strict=True)
        definitions = {row.name: row for row in QuestDefinition.objects.filter(name__in=CHAPTERS)}
        self.assertEqual(set(definitions), set(CHAPTERS))
        self.assertEqual(Badge.objects.get(name="Full Ark").criteria_value, {"count": 15})
        self.assertEqual(Badge.objects.get(name="Full Ark").criteria_type, "pet_species_owned")
        for name, (target, prerequisite, slug) in CHAPTERS.items():
            with self.subTest(chapter=name):
                definition = definitions[name]
                self.assertTrue(definition.is_system)
                self.assertFalse(definition.is_repeatable)
                self.assertEqual((definition.quest_type, definition.target_value, definition.duration_days),
                                 ("collection", target, 365))
                self.assertEqual(definition.required_badge.name, prerequisite)
                self.assertEqual(definition.trigger_filter, {"allowed_triggers": ["reading_logged"]})
                self.assertEqual((definition.coin_reward, definition.xp_reward), (0, 0))
                badge = Badge.objects.get(name=f"{name} Complete")
                self.assertEqual((badge.criteria_type, badge.criteria_value), ("quest_completed", {"quest_name": name}))
                self.assertEqual((badge.xp_bonus, badge.award_coins), (0, False))
                rewards = list(definition.reward_items.select_related("item"))
                self.assertEqual([(row.item.slug, row.quantity) for row in rewards], [(NAMESPACE + slug, 1)])
                item = rewards[0].item
                self.assertTrue(item_is_available(item))
                self.assertIn(item.item_type, {"cosmetic_title", "cosmetic_frame"})
                self.assertEqual(item.coin_value, 0)
                self.assertFalse(DropTable.objects.filter(item=item).exists())
                self.assertFalse(item.shop_rewards.exists())

    def test_reload_preserves_identities_and_accepted_reward_promises(self):
        self.unlock()
        first = next(iter(CHAPTERS))
        self.chapters()
        occurrence = ChallengeOccurrence.objects.get(goal__user=self.child, goal__name=first)
        snapshot = occurrence.snapshot
        identities = dict(ItemDefinition.objects.filter(slug__startswith=NAMESPACE).values_list("slug", "pk"))
        call_command("loadrpgcontent", pack=PACK, namespace=NAMESPACE, stdout=StringIO())
        self.assertEqual(dict(ItemDefinition.objects.filter(slug__startswith=NAMESPACE).values_list("slug", "pk")), identities)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, snapshot)
        self.assertFalse(occurrence.awarded_at)

    def test_locked_chapter_does_not_replay_pre_unlock_reading(self):
        self.read()
        receipt = ReadingDailyReward.objects.get(user=self.child)
        self.assertEqual(self.chapters(), {})
        self.clock.return_value = NOW + timedelta(hours=1)
        self.unlock()
        rows = self.chapters()
        self.assertEqual(set(rows), {next(iter(CHAPTERS))})
        self.assertEqual(next(iter(rows.values()))["progress"], "0")
        record_activity(self.child, "reading_logged", {"reading_reward_id": receipt.pk})
        self.assertEqual(next(iter(self.chapters().values()))["progress"], "0")
        self.read(day=1)
        self.assertEqual(next(iter(self.chapters().values()))["progress"], "1")

    def test_partial_logs_extra_minutes_and_retries_only_count_one_daily_adventure(self):
        self.unlock()
        first = self.read(minutes=4)
        self.assertIsNone(first.data["reading_reward"])
        self.assertEqual(next(iter(self.chapters().values()))["progress"], "0")
        request_id = str(uuid4())
        threshold = self.read(minutes=6, client_request_id=request_id, format="audiobook")
        self.assertIsNotNone(threshold.data["reading_reward"])
        retry = self.read(minutes=6, client_request_id=request_id, format="audiobook")
        self.assertEqual(retry.status_code, 200)
        self.read(minutes=600)
        receipt = ReadingDailyReward.objects.get(user=self.child)
        record_activity(self.child, "reading_logged", {"reading_reward_id": receipt.pk})
        self.assertEqual(next(iter(self.chapters().values()))["progress"], "1")
        self.assertEqual(ChallengeActivity.objects.filter(user=self.child, trigger_type="reading_logged").count(), 1)
        self.read(day=7)
        self.assertEqual(next(iter(self.chapters().values()))["progress"], "2")

    def test_all_chapters_require_35_new_reading_days_and_reward_once(self):
        self.unlock()
        for day in range(35):
            self.read(day=day, format=("print", "ebook", "audiobook")[day % 3])
            rows = self.chapters()
            completed = {name for name, row in rows.items() if row["status"] == "completed"}
            expected = set(list(CHAPTERS)[:1 if day < 14 else 2 if day < 34 else 3]) if day >= 4 else set()
            self.assertEqual(completed, expected)
            for row in rows.values():
                if row["status"] == "completed":
                    occurrence = ChallengeOccurrence.objects.get(pk=int(row["id"].split(":")[1]))
                    self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
        for _target, _prerequisite, slug in CHAPTERS.values():
            self.assertEqual(UserInventory.objects.get(user=self.child, item__slug=NAMESPACE + slug).quantity, 1)
        self.read(day=40)
        self.assertEqual(ChallengeOccurrence.objects.filter(goal__user=self.child, goal__name__in=CHAPTERS).count(), 3)
        self.assertEqual(list(UserInventory.objects.filter(user=self.child, item__slug__startswith=NAMESPACE).values_list("quantity", flat=True)), [1, 1, 1])
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS).exists())

    def test_catalog_edits_do_not_change_the_accepted_first_chapter_promise(self):
        self.unlock()
        self.chapters()
        definition = QuestDefinition.objects.get(name=next(iter(CHAPTERS)))
        definition.coin_reward = 999
        definition.xp_reward = 999
        definition.save(update_fields=["coin_reward", "xp_reward"])
        definition.reward_items.all().delete()
        for day in range(5):
            self.read(day=day)
        occurrence = ChallengeOccurrence.objects.get(goal__user=self.child, goal__name=definition.name)
        self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
        self.assertEqual([row["item_id"] for row in occurrence.reward_receipt["items"]],
                         [ItemDefinition.objects.get(slug=NAMESPACE + "title-pagefinder").pk])

    def test_progress_and_pin_remain_child_and_family_scoped(self):
        for user in (self.child, self.sibling, self.other):
            self.unlock(user)
            self.chapters(user)
        self.read()
        child_goal = next(iter(self.chapters().values()))
        self.assertEqual(child_goal["progress"], "1")
        receipt = ReadingDailyReward.objects.get(user=self.child)
        for user in (self.sibling, self.other):
            with self.subTest(user=user.username):
                record_activity(user, "reading_logged", {"reading_reward_id": receipt.pk})
                self.assertEqual(next(iter(self.chapters(user).values()))["progress"], "0")
                self.assertFalse(UserInventory.objects.filter(user=user, item__slug__startswith=NAMESPACE).exists())
                with self.assertRaisesRegex(ValueError, "Challenge not found"):
                    set_pin(user, child_goal["id"])
        self.assertEqual(ChallengeGoal.objects.filter(user=self.child, name__in=CHAPTERS).count(), 1)
