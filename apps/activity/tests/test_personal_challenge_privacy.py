"""Real challenge payouts keep parent goal details out of household audit reads."""
import json
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory, UserBadge
from apps.activity.models import ActivityEvent
from apps.activity.access import visible_activity_events
from apps.activity.services import ActivityLogService
from apps.chores.models import Chore
from apps.habits.models import Habit
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.movement.models import MovementType, MovementTypeSkillTag
from apps.quests.models import ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant, QuestSkillTag
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


class PersonalChallengeActivityPrivacyTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "private-goal-observer", "is_staff": True},
                      {"username": "private-goal-owner", "is_staff": True}]
    family_children = [{"username": "private-goal-child"}]

    def setUp(self):
        self.observer, self.owner = self.parents
        self.child = self.children[0]
        category = SkillCategory.objects.create(name="Activity privacy skill category")
        self.skill = Skill.objects.create(name="Activity privacy skill", category=category)
        self.movement = MovementType.objects.create(name="Shared family walk", slug="private-goal-walk")
        MovementTypeSkillTag.objects.create(movement_type=self.movement, skill=self.skill)
        self.definition = QuestDefinition.objects.create(
            name="My accepted catalog challenge", description="Catalog details", quest_type="collection",
            target_value=1, duration_days=7, is_system=True, coin_reward=7, xp_reward=12,
            trigger_filter={"allowed_triggers": ["movement_session"]},
        )
        QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill)

    def complete_challenges(self, target):
        self.client.force_authenticate(target if target.role == "parent" else self.observer)
        headers = {"HTTP_X_ABBY_SPACE": "personal"} if target.role == "parent" else {}
        response = self.client.post("/api/challenges/goals/", {
            "user_id": target.pk, "name": "My private authored challenge",
            "description": "A private personal goal note", "trigger_type": "movement_session",
            "metric": "count", "target": 1, "unit": "actions", "period": "this_week",
            "coin_reward": 3, "xp_reward": 6,
            "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
        }, format="json", **headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.client.force_authenticate(target)
        response = self.client.post("/api/movement-sessions/", {
            "movement_type_id": self.movement.pk, "duration_minutes": 15,
        }, format="json", **headers)
        self.assertEqual(response.status_code, 201, response.content)
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=target).select_related("goal"))
        self.assertEqual(len(occurrences), 2)
        self.assertEqual({row.status for row in occurrences}, {"completed"})
        self.assertEqual(sorted((row.reward_receipt["coins"], row.reward_receipt["xp"]) for row in occurrences),
                         [(3, 6), (7, 12)])
        events = list(ActivityEvent.objects.filter(subject=target, event_type__in=["award.coins", "award.xp"]))
        challenge_events = [row for row in events if any(goal.goal.name in row.summary for goal in occurrences)]
        self.assertEqual(len(challenge_events), 4)
        return occurrences, challenge_events

    def read_events(self, actor, query=""):
        self.client.force_authenticate(actor)
        response = self.client.get(f"/api/activity/{query}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def wire(self, actor, name, **params):
        with override_user(actor, scopes=frozenset({"mcp:read"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params})
        return result.structuredContent if hasattr(result, "structuredContent") else result[1]

    def test_real_parent_custom_and_catalog_payouts_are_private_in_list_filters_and_detail(self):
        occurrences, events = self.complete_challenges(self.owner)
        hidden_ids = {row.pk for row in events}
        for query in ("", f"?subject={self.owner.pk}", "?category=award", "?event_type=award.xp"):
            with self.subTest(query=query):
                rows = self.read_events(self.observer, query)
                self.assertFalse(hidden_ids.intersection(row["id"] for row in rows))
                self.assertNotIn("My private authored challenge", json.dumps(rows))
                self.assertNotIn(self.definition.name, json.dumps(rows))
        for event in events:
            self.assertEqual(self.client.get(f"/api/activity/{event.pk}/").status_code, 404)
        own_rows = self.read_events(self.owner, f"?subject={self.owner.pk}")
        self.assertTrue(hidden_ids.issubset({row["id"] for row in own_rows}))
        for event in events:
            source = event.context["private_challenge"]
            self.assertEqual(source["domain"], "quests.challengeoccurrence")
            self.assertEqual(source["owner_id"], self.owner.pk)
            self.assertIn(source["source_id"], {row.pk for row in occurrences})
            self.assertEqual(self.client.get(f"/api/activity/{event.pk}/").status_code, 200)

    def test_child_custom_and_catalog_payouts_remain_visible_to_both_parents(self):
        _, events = self.complete_challenges(self.child)
        event_ids = {row.pk for row in events}
        for parent in self.parents:
            rows = self.read_events(parent, f"?subject={self.child.pk}")
            self.assertTrue(event_ids.issubset({row["id"] for row in rows}))
        self.assertTrue(all("private_challenge" not in event.context for event in events))
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/activity/").status_code, 403)

    def test_unrelated_parent_movement_habits_and_untyped_historical_awards_remain_visible(self):
        self.complete_challenges(self.owner)
        self.client.force_authenticate(self.owner)
        habit = self.client.post("/api/habits/", {
            "name": "Shared parent habit", "habit_type": "positive",
        }, format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(habit.status_code, 201, habit.content)
        saved_habit = Habit.objects.get(name="Shared parent habit")
        logged = self.client.post(f"/api/habits/{saved_habit.pk}/log/", {"direction": 1},
                                  format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(logged.status_code, 200, logged.content)
        chore = Chore.objects.create(family=self.family, title="Shared parent chore", created_by=self.owner,
                                     assigned_to=self.owner, coin_reward=2)
        completed = self.client.post(f"/api/chores/{chore.pk}/complete/", {},
                                     format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(completed.status_code, 201, completed.content)
        # Historical generic awards lack a domain identity. Do not infer it
        # from a coincidentally identical user-authored summary.
        historical = ActivityLogService.record(
            category="award", event_type="award.coins", subject=self.owner,
            summary="Challenge complete: My private authored challenge", coins_delta=1,
        )
        rows = self.read_events(self.observer, f"?subject={self.owner.pk}")
        self.assertIn(historical.pk, {row["id"] for row in rows})
        self.assertTrue(any(row["event_type"] == "habit.tap" for row in rows))
        self.assertTrue(any(row["event_type"] == "chore.submit" for row in rows))
        self.assertTrue(any("Movement: Shared family walk" in row["summary"] for row in rows))

    def test_mcp_challenge_and_economy_reads_preserve_owner_child_and_coparent_boundaries(self):
        _, events = self.complete_challenges(self.owner)
        _, child_events = self.complete_challenges(self.child)
        before = list(CoinLedger.objects.values_list("pk", "amount"))

        for tool in ("list_challenges", "get_coin_balance", "list_coin_ledger", "get_economy_audit"):
            denied = self.wire(self.observer, tool, user_id=self.owner.pk)
            if tool in {"list_challenges", "get_coin_balance"}:
                self.assertEqual(denied.get("error", {}).get("code"), "not_found", denied)
            else:
                self.assertNotIn("error", denied, denied)
                self.assertNotIn("My private authored challenge", json.dumps(denied))
                self.assertNotIn(self.definition.name, json.dumps(denied))
            for actor, target in ((self.owner, self.owner), (self.observer, self.child)):
                allowed = self.wire(actor, tool, user_id=target.pk)
                self.assertNotIn("error", allowed, allowed)
        self.assertEqual(list(CoinLedger.objects.values_list("pk", "amount")), before)
        self.assertTrue(events and child_events)
        for actor in (self.owner, self.child):
            own = self.wire(actor, "get_coin_balance")
            explicit = self.wire(actor, "get_coin_balance", user_id=actor.pk)
            self.assertEqual(own, explicit)
            self.assertTrue(own["recent_ledger"])
        foreign = make_family("Foreign Coin observer", parents=[{"username": "foreign-coin-observer"}]).parents[0]
        denied = self.wire(foreign, "get_coin_balance", user_id=self.owner.pk)
        self.assertEqual(denied.get("error", {}).get("code"), "not_found", denied)

    def test_foreign_household_never_sees_parent_or_child_awards(self):
        self.complete_challenges(self.owner)
        self.complete_challenges(self.child)
        foreign = make_family("Foreign private goal family", parents=[{"username": "foreign-private-observer"}])
        self.assertEqual(self.read_events(foreign.parents[0]), [])

    def test_legacy_parent_challenge_progress_payout_expiry_and_rage_details_are_private(self):
        self.definition.is_system = False
        self.definition.created_by = self.owner
        self.definition.save(update_fields=["is_system", "created_by"])
        self.client.force_authenticate(self.owner)
        assigned = self.client.post(f"/api/quests/{self.definition.pk}/assign/", {"user_id": self.owner.pk},
                                    format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(assigned.status_code, 201, assigned.content)
        response = self.client.post("/api/movement-sessions/", {
            "movement_type_id": self.movement.pk, "duration_minutes": 5,
        }, format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(response.status_code, 201, response.content)
        quest = Quest.objects.get(definition=self.definition)
        self.assertEqual(quest.status, "completed")
        self.assertTrue(CoinLedger.objects.filter(user=self.owner, amount=7).exists())
        self.assertTrue(ActivityEvent.objects.filter(subject=self.owner, event_type="quest.progress").exists())
        self.assertTrue(ActivityEvent.objects.filter(subject=self.owner, event_type="quest.complete").exists())
        self.assertFalse(any(self.definition.name in row["summary"] for row in self.read_events(self.observer)))
        self.assertTrue(any(self.definition.name in row["summary"] for row in self.read_events(self.owner)))

        # Lifecycle workers also emit named details without a user request.
        for target in (self.owner, self.child):
            stale = Quest.objects.create(definition=self.definition, end_date=timezone.now() - timedelta(days=1))
            QuestParticipant.objects.create(quest=stale, user=target)
            QuestService._log_rage_event(stale, 0, "up")
        self.assertEqual(QuestService.expire_quests(), 2)
        observed = self.read_events(self.observer)
        lifecycle = [row for row in observed if row["event_type"] in {"system.rage_shield_tick", "system.quest_expire"}]
        self.assertEqual(len(lifecycle), 2)
        self.assertEqual({row["subject"]["id"] for row in lifecycle}, {self.child.pk})

    def test_earlier_typed_parent_quest_events_are_hidden_without_parsing_summary(self):
        quest = Quest.objects.create(definition=self.definition, end_date=timezone.now() + timedelta(days=1))
        QuestParticipant.objects.create(quest=quest, user=self.owner)
        event = ActivityLogService.record(category="quest", event_type="quest.progress", target=quest,
                                          subject=self.owner, summary="An arbitrary historical title")
        # Simulate an older event, retaining its real domain target only.
        ActivityEvent.objects.filter(pk=event.pk).update(context={"breakdown": [], "extras": {}})
        self.assertNotIn(event.pk, {row["id"] for row in self.read_events(self.observer)})
        self.assertIn(event.pk, {row["id"] for row in self.read_events(self.owner)})

    def test_shared_scoping_retains_privacy_when_the_original_goal_is_deleted(self):
        occurrences, events = self.complete_challenges(self.owner)
        event_ids = {row.pk for row in events}
        for occurrence in occurrences:
            occurrence.goal.delete()
        self.assertFalse(event_ids.intersection(visible_activity_events(self.observer).values_list("pk", flat=True)))
        self.assertTrue(event_ids.issubset(set(visible_activity_events(self.owner).values_list("pk", flat=True))))
        self.assertFalse(visible_activity_events(self.child).exists())

    def assign_legacy(self, target):
        self.client.force_authenticate(target if target.role == "parent" else self.observer)
        response = self.client.post(f"/api/quests/{self.definition.pk}/assign/", {"user_id": target.pk},
                                    format="json", **({"HTTP_X_ABBY_SPACE": "personal"}
                                                      if target.role == "parent" else {}))
        self.assertEqual(response.status_code, 201, response.content)
        return Quest.objects.get(participants__user=target)

    def test_mcp_legacy_instance_reads_protect_parent_participation_and_preserve_shared_catalog(self):
        parent_quest = self.assign_legacy(self.owner)
        child_quest = self.assign_legacy(self.child)
        foreign = make_family("Foreign legacy instance", parents=[{"username": "foreign-legacy-owner"}]).parents[0]
        foreign_quest = self.assign_legacy(foreign)
        for actor, target, quest in ((self.owner, self.owner, parent_quest),
                                    (self.observer, self.child, child_quest),
                                    (self.child, self.child, child_quest)):
            with self.subTest(actor=actor.pk, target=target.pk):
                listed = self.wire(actor, "list_quests", user_id=target.pk)
                self.assertEqual([row["id"] for row in listed["quests"]], [quest.pk])
                self.assertEqual(self.wire(actor, "get_quest", quest_id=quest.pk)["id"], quest.pk)
        for quest in (parent_quest, foreign_quest):
            with self.subTest(hidden_instance=quest.pk):
                result = self.wire(self.observer, "get_quest", quest_id=quest.pk)
                self.assertEqual(result.get("error", {}).get("code"), "not_found", result)
        for target in (self.owner, foreign):
            with self.subTest(hidden_target=target.pk):
                result = self.wire(self.observer, "list_quests", user_id=target.pk)
                self.assertEqual(result.get("error", {}).get("code"), "not_found", result)
        self.assertEqual([row["id"] for row in self.wire(self.observer, "list_quests")["quests"]], [child_quest.pk])
        # Definitions remain household/global authoring choices, independently
        # of a parent's private accepted instance.
        catalog = self.wire(self.observer, "list_quest_catalog")
        self.assertNotIn("error", catalog, catalog)
        self.assertIn(self.definition.pk, {row["id"] for row in catalog["quest_definitions"]})

    def test_mcp_legacy_read_rechecks_current_participant_role(self):
        quest = self.assign_legacy(self.child)
        type(self.child).objects.filter(pk=self.child.pk).update(role="parent")
        result = self.wire(self.observer, "get_quest", quest_id=quest.pk)
        self.assertEqual(result.get("error", {}).get("code"), "not_found", result)
        result = self.wire(self.observer, "list_quests", user_id=self.child.pk)
        self.assertEqual(result.get("error", {}).get("code"), "not_found", result)

    def test_nested_badge_award_inherits_parent_challenge_privacy_without_changing_child_contexts(self):
        badge = Badge.objects.create(
            name="A completion keepsake", criteria_type="quest_completed",
            criteria_value={"quest_name": self.definition.name}, xp_bonus=1,
        )
        self.complete_challenges(self.owner)
        self.assertTrue(UserBadge.objects.filter(user=self.owner, badge=badge).exists())
        event = ActivityEvent.objects.get(subject=self.owner, event_type="award.badge")
        self.assertEqual(event.context["private_challenge"]["owner_id"], self.owner.pk)
        self.assertNotIn(event.pk, {row["id"] for row in self.read_events(self.observer)})
        self.assertIn(event.pk, {row["id"] for row in self.read_events(self.owner)})
        self.complete_challenges(self.child)
        child_event = ActivityEvent.objects.get(subject=self.child, event_type="award.badge")
        self.assertNotIn("private_challenge", child_event.context)
        self.assertIn(child_event.pk, {row["id"] for row in self.read_events(self.observer)})

    def test_captured_private_owner_survives_role_and_household_changes(self):
        _, events = self.complete_challenges(self.owner)
        event_ids = {row.pk for row in events}
        users = type(self.owner).objects
        users.filter(pk=self.owner.pk).update(role="child")
        self.assertFalse(event_ids.intersection(visible_activity_events(self.observer).values_list("pk", flat=True)))
        new_family = make_family("Moved private owner family", parents=[{"username": "moved-private-observer"}])
        users.filter(pk=self.owner.pk).update(role="parent", family=new_family.family)
        self.owner.refresh_from_db()
        self.assertFalse(event_ids.intersection(visible_activity_events(new_family.parents[0]).values_list("pk", flat=True)))
        self.assertTrue(event_ids.issubset(set(visible_activity_events(self.owner).values_list("pk", flat=True))))
