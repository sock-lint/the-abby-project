"""Saved challenge histories paginate without opening windows or trusting cursors."""
from datetime import timedelta
from time import time
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pydantic import ValidationError

from apps.mcp_server.challenge_schemas import ListChallengesIn
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import challenges
from apps.quests.goals import _snapshot
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChallengePaginationTests(TestCase):
    def setUp(self):
        family = make_family(
            "Paginated challenges", parents=[{"username": "page-parent", "is_staff": True},
                                            {"username": "page-coparent", "is_staff": True}],
            children=[{"username": "page-child"}, {"username": "page-sibling"}],
        )
        self.parent, self.coparent = family.parents
        self.child, self.sibling = family.children
        other = make_family("Foreign challenge pages", parents=[{"username": "foreign-page-parent", "is_staff": True}],
                            children=[{"username": "foreign-page-child"}])
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        now = timezone.now()
        self.definition = QuestDefinition.objects.create(
            name="An old retryable reading goal", is_system=True, quest_type="collection", target_value=3,
            duration_days=2, trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        self.goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=self.definition, is_catalog=True,
            name=self.definition.name, metric="count", target=3, unit="actions",
            trigger_filter=self.definition.trigger_filter, timezone_name="America/Phoenix",
            starts_at=now - timedelta(days=10), ends_at=now - timedelta(days=8),
        )
        self.old = ChallengeOccurrence.objects.create(
            goal=self.goal, starts_at=self.goal.starts_at, ends_at=self.goal.ends_at, snapshot=_snapshot(self.goal),
        )
        self.noise = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, name="Saved weekly history", metric="count", target=3,
            unit="actions", starts_at=now, ends_at=now + timedelta(days=1),
        )

    def add_modern(self, count, *, same_start=False):
        now = timezone.now()
        goals = [self.noise] * count
        if same_start:
            goals = ChallengeGoal.objects.bulk_create([
                ChallengeGoal(
                    user=self.child, family=self.child.family, name=f"Tied saved goal {index}",
                    metric="count", target=3, unit="actions", starts_at=now, ends_at=now + timedelta(days=1),
                ) for index in range(count)
            ])
        return ChallengeOccurrence.objects.bulk_create([
            ChallengeOccurrence(
                goal=goal, starts_at=now if same_start else now + timedelta(minutes=index),
                ends_at=now + timedelta(days=1), snapshot=_snapshot(self.noise),
            ) for index, goal in enumerate(goals)
        ])

    def read(self, *, actor=None, **changes):
        with override_user(actor or self.parent), CaptureQueriesContext(connection) as captured:
            result = challenges.list_challenges(ListChallengesIn(user_id=self.child.pk, **changes))
        self.assertFalse(any(query["sql"].lstrip().upper().startswith((
            "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP",
        )) for query in captured))
        return result

    def test_signed_pages_discover_retryable_attempts_older_than_recent_hundred(self):
        self.add_modern(101)
        first = self.read(limit=100)
        self.assertEqual(len(first["results"]), 100)
        self.assertNotIn(f"goal:{self.old.pk}", [row["id"] for row in first["results"]])
        self.assertEqual(first["pages"]["modern"]["total"], 102)
        self.assertTrue(first["pages"]["modern"]["has_more"])
        page = self.read(limit=100, source="modern", cursor=first["pages"]["modern"]["next_cursor"])
        self.assertEqual(len(page["results"]), 2)
        self.assertEqual(page["results"][-1]["id"], f"goal:{self.old.pk}")
        self.assertTrue(page["results"][-1]["retry"]["allowed"])
        self.assertFalse(page["pages"]["modern"]["has_more"])
        self.assertIsNone(page["pages"]["modern"]["next_cursor"])
        self.assertEqual(ChallengeOccurrence.objects.count(), 102)
        self.assertFalse(CoinLedger.objects.exists())

    def test_registered_result_schema_advertises_and_validates_history_continuations(self):
        self.add_modern(2)
        entry = mcp._tool_manager.get_tool("list_challenges")
        schema = entry.fn_metadata.output_schema
        self.assertTrue({"user_id", "source", "pages", "results", "pin", "daily_bonus",
                         "recent_receipts", "challenge_receipts", "saved_state_only"}
                        <= set(schema["properties"]))
        page_schema = schema["properties"]["pages"]["additionalProperties"]
        resolved = schema["$defs"][page_schema["$ref"].split("/")[-1]]
        self.assertTrue({"total", "has_more", "next_cursor"} <= set(resolved["properties"]))
        with override_user(self.parent, scopes=frozenset({"mcp:read"})):
            response = async_to_sync(mcp.call_tool)("list_challenges", {"params": {
                "user_id": self.child.pk, "source": "modern", "limit": 1,
            }})
        payload = response.structuredContent if hasattr(response, "structuredContent") else response[1]
        self.assertNotIn("error", payload)
        self.assertEqual(payload["pages"]["modern"]["total"], 3)
        self.assertTrue(payload["pages"]["modern"]["has_more"])
        self.assertIsInstance(payload["pages"]["modern"]["next_cursor"], str)
        self.assertEqual(set(payload["pages"]), {"modern"})

    def test_parent_default_wire_read_preserves_null_daily_bonus_and_self_scope(self):
        before = list(ChallengeOccurrence.objects.values())
        with override_user(self.parent, scopes=frozenset({"mcp:read"})):
            response = async_to_sync(mcp.call_tool)("list_challenges", {"params": {}})
        payload = response.structuredContent if hasattr(response, "structuredContent") else response[1]
        self.assertNotIn("error", payload)
        self.assertEqual(payload["user_id"], self.parent.pk)
        self.assertIsNone(payload["daily_bonus"])
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["pages"], {
            source: {"total": 0, "has_more": False, "next_cursor": None} for source in ("modern", "legacy")
        })
        self.assertTrue(payload["saved_state_only"])
        self.assertEqual(before, list(ChallengeOccurrence.objects.values()))
        self.assertFalse(CoinLedger.objects.exists())

    def test_tied_starts_have_no_duplicates_and_backdated_new_inserts_stay_out(self):
        newer = self.add_modern(3, same_start=True)
        first = self.read(source="modern", limit=2)
        self.assertEqual([row["id"] for row in first["results"]], [f"goal:{row.pk}" for row in newer[-1:0:-1]])
        inserted = ChallengeOccurrence.objects.create(
            goal=self.noise, starts_at=self.old.starts_at - timedelta(days=30),
            ends_at=self.old.ends_at, snapshot=_snapshot(self.noise),
        )
        second = self.read(source="modern", limit=2, cursor=first["pages"]["modern"]["next_cursor"])
        ids = [row["id"] for page in (first, second) for row in page["results"]]
        self.assertEqual(ids, [f"goal:{row.pk}" for row in reversed(newer)] + [f"goal:{self.old.pk}"])
        self.assertNotIn(f"goal:{inserted.pk}", ids)
        self.assertEqual(second["pages"]["modern"]["total"], 4)

    def test_default_sources_keep_legacy_results_and_independent_start_date_cursor(self):
        now = timezone.now()
        legacy = []
        for days in (2, 1, 3):
            quest = Quest.objects.create(
                definition=self.definition, start_date=now - timedelta(days=days), end_date=now + timedelta(days=1),
            )
            QuestParticipant.objects.create(quest=quest, user=self.child)
            legacy.append(quest)
        first = self.read(limit=1)
        self.assertEqual(first["results"][0]["id"], f"goal:{self.old.pk}")
        self.assertEqual(first["results"][1]["id"], f"legacy:{legacy[1].pk}")
        self.assertEqual(set(first["pages"]), {"modern", "legacy"})
        second = self.read(source="legacy", limit=2, cursor=first["pages"]["legacy"]["next_cursor"])
        self.assertEqual([row["id"] for row in second["results"]], [f"legacy:{legacy[0].pk}", f"legacy:{legacy[2].pk}"])
        self.assertEqual(set(second["pages"]), {"legacy"})
        self.assertFalse(second["pages"]["legacy"]["has_more"])
        modern = self.read(include_legacy=False)
        self.assertEqual(set(modern["pages"]), {"modern"})
        self.assertEqual(len(modern["results"]), 1)

    def test_cursor_rejects_another_source_target_actor_family_tampering_and_expiry(self):
        self.add_modern(2)
        first = self.read(source="modern", limit=1)
        cursor = first["pages"]["modern"]["next_cursor"]
        for actor, selected, source, candidate in (
            (self.parent, self.child, "legacy", cursor),
            (self.parent, self.sibling, "modern", cursor),
            (self.coparent, self.child, "modern", cursor),
            (self.other_parent, self.other_child, "modern", cursor),
            (self.parent, self.child, "modern", "tampered" + cursor),
        ):
            with self.subTest(actor=actor.pk, target=selected.pk, source=source), override_user(actor):
                with self.assertRaises(MCPValidationError):
                    challenges.list_challenges(ListChallengesIn(user_id=selected.pk, source=source, cursor=candidate))
        with patch("django.core.signing.time.time", return_value=time() + 86401):
            with self.assertRaises(MCPValidationError):
                self.read(source="modern", cursor=cursor)
        with self.assertRaises(ValidationError):
            ListChallengesIn(cursor=cursor)
        with self.assertRaises(ValidationError):
            ListChallengesIn(source="legacy", include_legacy=False)

    def test_current_permissions_and_membership_are_locked_on_later_pages(self):
        self.add_modern(2)
        first = self.read(source="modern", limit=1)
        cursor = first["pages"]["modern"]["next_cursor"]
        User = get_user_model()
        original = {"family_id": self.parent.family_id, "role": self.parent.role,
                    "is_active": self.parent.is_active, "is_staff": self.parent.is_staff}
        for changes in ({"family_id": self.other_parent.family_id}, {"role": "child"},
                        {"is_active": False}, {"is_staff": False}):
            User.objects.filter(pk=self.parent.pk).update(**changes)
            try:
                with self.subTest(changes=changes), self.assertRaises(MCPPermissionDenied):
                    self.read(source="modern", cursor=cursor)
            finally:
                User.objects.filter(pk=self.parent.pk).update(**original)

        resolve = challenges.resolve_target_user
        def move_after_selection(actor, requested_id):
            result = resolve(actor, requested_id)
            User.objects.filter(pk=self.child.pk).update(family_id=self.other_parent.family_id)
            return result
        with patch("apps.mcp_server.tools.challenges.resolve_target_user", side_effect=move_after_selection):
            with self.assertRaises(MCPNotFoundError):
                self.read(source="modern", cursor=cursor)
