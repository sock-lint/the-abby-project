"""Explicit catalog attempts and future weekly controls preserve accepted work."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.quests.goals import create_goal, ingest_activity, list_goals, set_pin
from apps.quests.models import ChallengeActivity, ChallengeOccurrence, ChallengeSchedule, Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class GoalControlTests(TestCase):
    def setUp(self):
        household = make_family("Goal controls", parents=[{"username": "control-parent"}],
                                children=[{"username": "control-child"}, {"username": "control-sibling"}])
        self.parent, self.child, self.sibling = household.parents[0], *household.children
        self.skill = Skill.objects.create(name="Control skill", category=SkillCategory.objects.create(name="Control"))
        self.now = timezone.now()
        self.start = self.now - timedelta(days=10)
        with patch("django.utils.timezone.now", return_value=self.start):
            self.definition = QuestDefinition.objects.create(
                name="Try again", description="Two chores", quest_type="collection", target_value=2,
                duration_days=2, is_system=True, coin_reward=7,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            list_goals(self.child)
        self.original = ChallengeOccurrence.objects.get(goal__user=self.child)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def retry(self, occurrence=None, at=None):
        row = occurrence or self.original
        with patch("django.utils.timezone.now", return_value=at or self.now):
            return self.client.post(f"/api/challenges/goal:{row.pk}/retry/", {}, format="json")

    def weekly(self):
        return create_goal(self.parent, self.child, {
            "name": "Weekly chores", "description": "Current promise", "metric": "count", "target": Decimal(2),
            "unit": "actions", "trigger_type": "chore_complete", "period": "this_week", "repeat_weekly": True,
            "coin_reward": 3, "xp_reward": 0, "skill_tags": [],
        })

    def test_retry_is_explicit_fresh_and_idempotent(self):
        response = self.retry()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotEqual(response.data["id"], f"goal:{self.original.pk}")
        self.assertEqual(response.data["progress"], "0")
        self.assertEqual(response.data["retry_of"], f"goal:{self.original.pk}")
        replay = self.retry()
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["id"], response.data["id"])
        self.assertFalse(CoinLedger.objects.exists())

    def test_weekly_payload_exposes_server_owned_revision_and_future_setup(self):
        row = self.weekly()
        payload = next(value for value in self.client.get("/api/challenges/").data["results"]
                       if value["id"] == f"goal:{row.pk}")
        self.assertEqual(payload["goal_definition_id"], row.goal_id)
        self.assertEqual(payload["schedule"]["revision"], 0)
        self.assertEqual(payload["schedule"]["next_week"]["target"], "2")
        self.assertEqual(payload["qualifying_triggers"], ["chore_complete"])

    def schedule(self, row, data):
        self.client.force_authenticate(self.parent)
        return self.client.patch(f"/api/challenges/goals/{row.goal_id}/schedule/", data, format="json")

    def test_retry_counts_only_new_facts_and_first_attempt_to_finish_wins(self):
        ingest_activity(self.child, "chore_complete", "old", "chore_complete", occurred_at=self.start + timedelta(hours=1))
        fresh = self.retry()
        successor = ChallengeOccurrence.objects.get(pk=fresh.data["id"].split(":")[1])
        ingest_activity(self.child, "chore_complete", "old", "chore_complete", occurred_at=self.now)
        successor.refresh_from_db()
        self.assertEqual(successor.progress, 0)
        # Repairing an earlier accepted fact completes the earlier promise.
        ingest_activity(self.child, "chore_complete", "late-old", "chore_complete",
                        occurred_at=self.start + timedelta(hours=2))
        self.original.refresh_from_db()
        successor.refresh_from_db()
        self.assertEqual((self.original.status, successor.status, successor.closed_reason),
                         ("completed", "closed", "reward_already_awarded"))
        self.assertIsNone(successor.awarded_at)
        self.assertEqual(successor.reward_receipt, {})
        for index in range(3):
            ingest_activity(self.child, "chore_complete", f"new-{index}", "chore_complete", occurred_at=self.now)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [7])
        self.assertEqual(self.retry().data["id"], fresh.data["id"], "predecessor retries keep their saved successor")

    def test_successful_retry_closes_old_history_without_fabricating_an_award(self):
        fresh = self.retry()
        for index in range(2):
            ingest_activity(self.child, "chore_complete", f"new-{index}", "chore_complete", occurred_at=self.now)
        self.original.refresh_from_db()
        self.assertEqual(self.original.status, "closed")
        self.assertIsNone(self.original.awarded_at)
        self.assertEqual(self.original.reward_receipt, {})
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
        successor = ChallengeOccurrence.objects.get(pk=fresh.data["id"].split(":")[1])
        self.assertEqual(self.retry(successor, successor.ends_at + timedelta(days=1)).status_code, 409)

    def test_parent_can_retry_same_family_child_but_sibling_and_foreign_parent_cannot(self):
        self.client.force_authenticate(self.sibling)
        self.assertEqual(self.retry().status_code, 404)
        outsider = make_family("Foreign controls", parents=[{"username": "foreign-control-parent"}]).parents[0]
        self.client.force_authenticate(outsider)
        self.assertEqual(self.retry().status_code, 404)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.retry().status_code, 201)

    def test_alias_legacy_paid_history_and_repeatable_or_parent_goals_cannot_retry(self):
        alias = QuestDefinition.objects.create(name=self.definition.name, is_system=True, quest_type="collection",
                                              target_value=2, superseded_by=self.definition)
        legacy = Quest.objects.create(definition=alias, status="completed", end_date=self.start)
        QuestParticipant.objects.create(quest=legacy, user=self.child)
        self.assertEqual(self.retry().status_code, 409)
        self.assertEqual(self.retry().data["error"], "already_awarded")
        self.assertEqual(self.retry(self.weekly()).status_code, 409)

    def test_alias_uses_canonical_cooperative_and_repeatable_rules_for_retry(self):
        alias = QuestDefinition.objects.create(
            name=self.definition.name, quest_type="collection", target_value=2,
            duration_days=2, is_system=True, superseded_by=self.definition,
        )
        self.original.goal.catalog_definition = alias
        self.original.goal.save(update_fields=["catalog_definition"])
        self.definition.is_cooperative = True
        self.definition.save(update_fields=["is_cooperative"])
        response = self.retry()
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["error"], "cooperative")
        self.definition.is_cooperative = False
        self.definition.is_repeatable = True
        self.definition.save(update_fields=["is_cooperative", "is_repeatable"])
        response = self.retry()
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["error"], "repeatable")

    def test_pause_resume_never_reopens_a_previously_paused_week(self):
        from apps.quests.controls import week_start
        from apps.quests.goals import _occurrence
        row = self.weekly()
        next_start = week_start(row.goal, self.now) + timedelta(days=7)
        response = self.schedule(row, {"expected_revision": 0, "paused": True})
        self.assertEqual(response.status_code, 200, response.data)
        with patch("django.utils.timezone.now", return_value=next_start + timedelta(hours=1)):
            self.assertIsNone(_occurrence(row.goal, timezone.now()))
            resumed = self.schedule(row, {"expected_revision": 1, "paused": False})
            self.assertEqual(resumed.status_code, 200, resumed.data)
        ingest_activity(self.child, "chore_complete", "late-paused", "chore_complete", occurred_at=next_start)
        self.assertFalse(ChallengeOccurrence.objects.filter(goal=row.goal, starts_at=next_start).exists())
        self.assertIsNotNone(_occurrence(row.goal, next_start + timedelta(days=7, hours=1)))

    def test_next_week_edits_preserve_current_and_already_accepted_future_snapshots(self):
        from apps.quests.controls import week_start
        from apps.quests.goals import _occurrence
        row = self.weekly()
        start = week_start(row.goal, self.now) + timedelta(days=7)
        future = _occurrence(row.goal, start + timedelta(hours=1))
        before, future_before = row.snapshot.copy(), future.snapshot.copy()
        response = self.schedule(row, {"expected_revision": 0, "next_week": {
            "name": "More chores", "description": "Future promise", "target": "3", "coin_reward": 9,
            "xp_reward": 12, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
        }})
        self.assertEqual(response.status_code, 200, response.data)
        row.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual((row.snapshot, future.snapshot), (before, future_before))
        later = _occurrence(row.goal, start + timedelta(days=7, hours=1))
        self.assertEqual((later.snapshot["name"], later.snapshot["target"], later.snapshot["coins"]),
                         ("More chores", "3.000", 9))
        self.assertFalse(CoinLedger.objects.exists())

    def test_schedule_rejects_stale_revision_invalid_rewards_rules_and_other_family(self):
        row = self.weekly()
        self.assertEqual(self.schedule(row, {"expected_revision": 0, "paused": True}).status_code, 200)
        self.assertEqual(self.schedule(row, {"expected_revision": 0, "paused": False}).status_code, 409)
        for change in ({"target": "1.5"}, {"xp_reward": 10}, {"metric": "minutes"}, {"skill_tags": [{"skill_id": 999999}]}):
            self.assertEqual(self.schedule(row, {"expected_revision": 1, "next_week": change}).status_code, 400)
        row.goal.refresh_from_db()
        self.assertEqual(row.goal.schedule_revision, 1)

    def test_context_does_not_load_weekly_history_or_full_attempt_history(self):
        from apps.quests.controls import control_context
        row = self.weekly()
        for index in range(30):
            start = row.starts_at - timedelta(weeks=index + 1)
            ChallengeOccurrence.objects.create(goal=row.goal, starts_at=start, ends_at=start + timedelta(days=7),
                                               snapshot=row.snapshot)
            ChallengeSchedule.objects.create(goal=row.goal, starts_at=start, paused=False, snapshot=row.snapshot)
            catalog_start = self.original.starts_at - timedelta(days=index + 1)
            ChallengeOccurrence.objects.create(goal=self.original.goal, starts_at=catalog_start,
                                               ends_at=catalog_start + timedelta(days=1), snapshot=self.original.snapshot)
        context = control_context(self.child)
        self.assertEqual(context["goals"][row.goal_id].control_occurrences, [])
        self.assertEqual(len(context["goals"][row.goal_id].control_schedules), 2)
        self.assertEqual(len(context["goals"][self.original.goal_id].control_occurrences), 1)

    def test_all_expired_one_time_catalog_goals_remain_discoverable_beyond_history_limit(self):
        for index in range(25):
            with patch("django.utils.timezone.now", return_value=self.start):
                QuestDefinition.objects.create(name=f"Retryable {index}", quest_type="collection", target_value=3,
                                               is_system=True, duration_days=1,
                                               trigger_filter={"allowed_triggers": ["chore_complete"]})
                list_goals(self.child)
        response = self.client.get("/api/challenges/")
        self.assertEqual(sum(row["retry"]["allowed"] for row in response.data["results"]), 26)

    def test_schedule_and_retry_permissions_reject_unknown_fields_and_foreign_targets(self):
        row = self.weekly()
        outsider = make_family("Foreign setup", parents=[{"username": "setup-outsider"}]).parents[0]
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.patch(f"/api/challenges/goals/{row.goal_id}/schedule/",
            {"expected_revision": 0, "paused": True}, format="json").status_code, 403)
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.patch(f"/api/challenges/goals/{row.goal_id}/schedule/",
            {"expected_revision": 0, "paused": True}, format="json").status_code, 404)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.post(f"/api/challenges/goal:{self.original.pk}/retry/",
            {"user_id": self.sibling.pk}, format="json").status_code, 400)

    def test_reward_only_damage_sources_are_not_reported_as_qualifying(self):
        from apps.quests.goals import qualifying_triggers, _what_counts
        snapshot = {"metric": "damage", "filter": {"allowed_triggers": ["journal_entry", "chore_complete"],
                    "chore_ids": [1], "project_id": 2, "skill_category_id": 3, "savings_goal_id": 4}}
        self.assertEqual(qualifying_triggers(snapshot), ["chore_complete", "journal_entry"])
        # Movement is supported; a zero-damage future/retained trigger is not.
        snapshot["filter"]["allowed_triggers"] = ["creation_logged", "chore_complete"]
        self.assertEqual(qualifying_triggers(snapshot), ["chore_complete"])
        description = _what_counts(snapshot)
        self.assertIn("selected chores", description)
        self.assertIn("selected project", description)

    def test_pending_equal_timestamp_fact_cannot_enter_a_retry_but_fresh_equal_timestamp_facts_can(self):
        old = ChallengeActivity.objects.create(
            user=self.child, source_type="chore_complete", source_id="pending-before-retry",
            trigger_type="chore_complete", occurred_at=self.now, occurred_on=self.now.date(), context={},
        )
        result = self.retry()
        successor = ChallengeOccurrence.objects.get(pk=result.data["id"].split(":")[1])
        ingest_activity(self.child, old.source_type, old.source_id, old.trigger_type, occurred_at=self.now)
        successor.refresh_from_db()
        self.assertEqual(successor.progress, 0)
        # Global activity IDs may interleave across households/accounts.
        ingest_activity(self.sibling, "chore_complete", "other-child", "chore_complete", occurred_at=self.now)
        for index in range(2):
            ingest_activity(self.child, "chore_complete", f"fresh-equal-{index}", "chore_complete", occurred_at=self.now)
        successor.refresh_from_db()
        self.assertEqual((successor.progress, successor.status), (2, "completed"))
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_retry_and_replay_report_the_actual_pin_preference(self):
        set_pin(self.child, f"goal:{self.original.pk}")
        response = self.retry()
        self.assertIs(response.data["pinned"], True)
        self.assertIs(self.retry().data["pinned"], True)
        set_pin(self.child, response.data["id"], clear=True)
        self.assertIs(self.retry().data["pinned"], False)

    def test_parent_can_pause_a_goal_after_a_saved_reward_skill_was_deleted(self):
        row = create_goal(self.parent, self.child, {
            "name": "Legacy skill promise", "metric": "count", "target": Decimal(2), "unit": "actions",
            "trigger_type": "chore_complete", "period": "this_week", "repeat_weekly": True,
            "xp_reward": 5, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
        })
        original = row.snapshot.copy()
        self.skill.delete()
        response = self.schedule(row, {"expected_revision": 0, "paused": True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.data["schedule"]["next_week"]["paused"], True)
        row.refresh_from_db()
        self.assertEqual(row.snapshot, original)
        self.assertEqual(self.schedule(row, {"expected_revision": 1, "paused": False}).status_code, 400)
        self.assertEqual(self.schedule(row, {"expected_revision": 1, "next_week": {"name": "Still invalid"}}).status_code, 400)
