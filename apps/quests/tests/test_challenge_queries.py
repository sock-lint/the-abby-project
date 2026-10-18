from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies
from apps.quests.models import (
    ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition,
    QuestParticipant, QuestRewardItem,
)
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition
from config.tests.factories import make_family


class ChallengeListQueryTests(TestCase):
    """Adding saved challenges must not add a SELECT for every rendered row."""

    def setUp(self):
        household = make_family(
            "Challenge queries", parents=[{"username": "query-parent"}],
            children=[{"username": "query-child"}, {"username": "query-sibling"}],
        )
        self.family = household.family
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        self.now = timezone.now()
        self.item = ItemDefinition.objects.create(
            name="Accepted snack", slug="query-snack", icon="snack", item_type="food",
        )

    def measured_get(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        tables = Counter(
            match.group(1)
            for query in queries.captured_queries
            for match in re.finditer(r'\bFROM "([^"]+)"', query["sql"])
        )
        return response.data, len(queries), dict(tables)

    def assert_constant_queries(self, small, large):
        self.assertEqual(
            large[1], small[1],
            f"Challenge SELECTs grew with saved rows: {small[1]} -> {large[1]}; "
            f"table reads {small[2]} -> {large[2]}",
        )

    def saved_goal(self, name, *, catalog=False, retired=False, starts_at=None,
                   ends_at=None, completed=False, repeat_weekly=False, repeat_days=0,
                   user=None):
        user = user or self.child
        definition = None
        if catalog and not retired:
            definition = QuestDefinition.objects.create(
                name=name, description="Saved challenge", quest_type="collection",
                target_value=2, is_system=True,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
        start = starts_at or self.now - timedelta(days=1)
        end = ends_at or self.now + timedelta(days=6)
        goal = ChallengeGoal.objects.create(
            user=user, family_id=user.family_id, created_by=self.parent,
            catalog_definition=definition, is_catalog=catalog,
            name=name, description="Saved challenge", metric="count", target=2,
            unit="actions", trigger_filter={"allowed_triggers": ["chore_complete"]},
            timezone_name="America/Phoenix", starts_at=start, ends_at=end,
            repeat_weekly=repeat_weekly, repeat_days=repeat_days,
            coin_reward=5, reward_items=[{"item_id": self.item.pk, "quantity": 2}],
        )
        snapshot = {
            "name": name, "description": goal.description, "metric": "count",
            "target": "2", "unit": "actions", "filter": goal.trigger_filter,
            "coins": 5, "xp": 0, "skill_tags": [],
            "items": [{"item_id": self.item.pk, "quantity": 2}],
            "catalog_name": name if catalog else None,
            "catalog_type": "collection" if catalog else None,
        }
        return ChallengeOccurrence.objects.create(
            goal=goal, starts_at=start, ends_at=end, snapshot=snapshot,
            status="completed" if completed else "active",
            progress=Decimal(2) if completed else Decimal(0),
            completed_at=self.now if completed else None,
            awarded_at=self.now if completed else None,
            reward_receipt={"coins": 5, "xp": 0, "items": []} if completed else {},
        )

    def window_batch(self, index):
        zone = ZoneInfo("America/Phoenix")
        day = self.now.astimezone(zone).date()
        monday = day - timedelta(days=day.weekday())
        week_start = datetime.combine(monday, time.min, tzinfo=zone)
        return [
            self.saved_goal(f"Completed {index}", catalog=True, completed=True),
            self.saved_goal(f"Expired {index}", catalog=True,
                            starts_at=self.now - timedelta(days=14),
                            ends_at=self.now - timedelta(days=7)),
            self.saved_goal(f"Retired current {index}", catalog=True, retired=True,
                            repeat_days=7),
            self.saved_goal(f"Retired expired {index}", catalog=True, retired=True,
                            starts_at=self.now - timedelta(days=14),
                            ends_at=self.now - timedelta(days=7), repeat_days=7),
            self.saved_goal(f"Upcoming {index}", starts_at=self.now + timedelta(days=2),
                            ends_at=self.now + timedelta(days=9)),
            self.saved_goal(f"Weekly {index}", starts_at=week_start,
                            ends_at=week_start + timedelta(days=7), repeat_weekly=True),
        ]

    def test_warm_saved_windows_and_reward_previews_have_constant_query_count(self):
        rows = self.window_batch(0)
        self.client.get("/api/challenges/")  # Enrollment and the pin exist before measurement.
        small = self.measured_get()
        for index in range(1, 6):
            rows.extend(self.window_batch(index))

        # Accepted promises remain readable after acquisition support changes.
        ItemDefinition.objects.filter(pk=self.item.pk).update(item_type="cosmetic_pet_accessory")
        outsider = make_family("Other query household", children=[{"username": "query-outsider"}])
        hidden = self.saved_goal("Private other-family goal", user=outsider.children[0])
        before_count = ChallengeOccurrence.objects.count()
        large = self.measured_get()
        payload = large[0]
        by_name = {row["name"]: row for row in payload["results"]}
        self.assertEqual(set(by_name), {row.snapshot["name"] for row in rows})
        self.assertNotIn(f"goal:{hidden.pk}", {row["id"] for row in payload["results"]})
        self.assertEqual(len(payload["recent_receipts"]), 6)
        for index in range(6):
            self.assertEqual(by_name[f"Completed {index}"]["status"], "completed")
            self.assertEqual(by_name[f"Expired {index}"]["status"], "expired")
            self.assertEqual(by_name[f"Retired current {index}"]["origin"], "catalog")
            self.assertEqual(by_name[f"Retired expired {index}"]["status"], "expired")
            self.assertEqual(by_name[f"Upcoming {index}"]["status"], "upcoming")
            self.assertTrue(by_name[f"Weekly {index}"]["repeat_weekly"])
        for row in payload["results"] + payload["recent_receipts"]:
            self.assertEqual(row["rewards"]["items"][0]["item_id"], self.item.pk)
            self.assertEqual(row["rewards"]["items"][0]["quantity"], 2)
        self.assertEqual(ChallengeOccurrence.objects.count(), before_count)
        self.assertFalse(CoinLedger.objects.exists())
        self.assert_constant_queries(small, large)

    def legacy_batch(self, index):
        rows = []
        for accepted in (False, True):
            definition = QuestDefinition.objects.create(
                name=f"Legacy {index} {accepted}", description="Saved legacy quest",
                quest_type="collection", target_value=2, is_system=True,
            )
            reward = QuestRewardItem.objects.create(
                quest_definition=definition, item=self.item, quantity=2,
            )
            quest = Quest.objects.create(
                definition=definition, status="completed", current_progress=2,
                end_date=self.now + timedelta(days=1),
                reward_items_snapshot=(
                    [{"id": reward.pk, "item_id": self.item.pk, "quantity": 2}]
                    if accepted else None
                ),
            )
            QuestParticipant.objects.create(quest=quest, user=self.child, contribution=1)
            QuestParticipant.objects.create(quest=quest, user=self.sibling, contribution=1)
            rows.append(quest)
        return rows

    def test_warm_legacy_rewards_and_participants_have_constant_query_count(self):
        quests = self.legacy_batch(0)
        self.client.get("/api/challenges/")
        small = self.measured_get()
        for index in range(1, 6):
            quests.extend(self.legacy_batch(index))
        large = self.measured_get()
        self.assertEqual(
            {row["id"] for row in large[0]["results"]},
            {f"legacy:{quest.pk}" for quest in quests},
        )
        for row in large[0]["results"]:
            self.assertEqual({p["user"] for p in row["participants"]}, {self.child.pk, self.sibling.pk})
            self.assertEqual(row["rewards"]["items"][0]["item"], self.item.pk)
            self.assertEqual(row["rewards"]["items"][0]["quantity"], 2)
        self.assertFalse(CoinLedger.objects.exists())
        self.assert_constant_queries(small, large)

    def legacy_egg_reward(self):
        PetSpecies.objects.create(
            name="Legacy Query Wolf", slug="legacy-query-wolf", icon="W", sprite_key="wolf",
        )
        ItemDefinition.objects.filter(pk=self.item.pk).update(
            item_type="egg", metadata={"species": "Legacy Query Wolf"},
        )

    def test_warm_saved_legacy_egg_previews_have_constant_query_count(self):
        self.legacy_egg_reward()
        self.saved_goal("Legacy egg 0", completed=True)
        self.client.get("/api/challenges/")
        small = self.measured_get()
        for index in range(1, 6):
            row = self.saved_goal(f"Legacy egg {index}", completed=True)
            row.snapshot["items"][0].update(
                item_name=f"Frozen reward {index}", item_catalog_available=True,
            )
            row.save(update_fields=["snapshot"])
        large = self.measured_get()
        by_name = {row["name"]: row for row in large[0]["results"]}
        for index in range(1, 6):
            self.assertEqual(
                by_name[f"Legacy egg {index}"]["rewards"]["items"][0]["item_name"],
                f"Frozen reward {index}",
            )
        for row in large[0]["results"] + large[0]["recent_receipts"]:
            self.assertFalse(row["rewards"]["items"][0]["item_catalog_available"])
        self.assertFalse(CoinLedger.objects.exists())
        self.assert_constant_queries(small, large)
        supported_policy = {
            "schema_version": 1,
            "pets": [{"species_slug": "legacy-query-wolf", "sprite_key": "wolf", "potion_slugs": ["base"]}],
            "potion_slugs": ["base"],
        }
        with override_settings(RPG_ASSET_SUPPORT_POLICY=supported_policy):
            refreshed = self.measured_get()[0]
        for row in refreshed["results"] + refreshed["recent_receipts"]:
            self.assertTrue(row["rewards"]["items"][0]["item_catalog_available"])
        refreshed_by_name = {row["name"]: row for row in refreshed["results"]}
        self.assertEqual(
            refreshed_by_name["Legacy egg 5"]["rewards"]["items"][0]["item_name"],
            "Frozen reward 5",
        )

    def test_warm_legacy_egg_promises_have_constant_query_count(self):
        self.legacy_egg_reward()
        self.legacy_batch(0)
        self.client.get("/api/challenges/")
        small = self.measured_get()
        for index in range(1, 6):
            self.legacy_batch(index)
        large = self.measured_get()
        for row in large[0]["results"]:
            self.assertEqual(row["rewards"]["items"][0]["item"], self.item.pk)
            self.assertEqual(row["rewards"]["items"][0]["quantity"], 2)
            self.assertFalse(row["rewards"]["items"][0]["item_catalog_available"])
        self.assertFalse(CoinLedger.objects.exists())
        self.assert_constant_queries(small, large)
