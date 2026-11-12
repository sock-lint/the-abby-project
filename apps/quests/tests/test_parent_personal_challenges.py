"""Parents participate as themselves while household supervision stays separate."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.movement.models import MovementType, MovementTypeSkillTag
from apps.quests.activity import record_activity, retry_pending_activity
from apps.quests.models import (
    ChallengeActivity, ChallengeContribution, ChallengeGoal, ChallengeOccurrence,
    DailyBonus, QuestDefinition, QuestRewardItem, QuestSkillTag,
)
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


class ParentPersonalChallengeTests(TestCase):
    def setUp(self):
        household = make_family(
            "Personal challenge family",
            parents=[{"username": "challenge-parent"}, {"username": "challenge-coparent"}],
            children=[{"username": "challenge-child"}],
        )
        self.parent, self.coparent = household.parents
        self.child = household.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.client.credentials(HTTP_X_ABBY_SPACE="personal")
        category = SkillCategory.objects.create(name="Personal movement")
        self.skill = Skill.objects.create(name="Steadiness", category=category)
        self.running = MovementType.objects.create(name="Personal run", slug="personal-run")
        MovementTypeSkillTag.objects.create(movement_type=self.running, skill=self.skill)
        self.definition = QuestDefinition.objects.create(
            name="A personal beginning", description="Record two movement sessions", quest_type="collection",
            target_value=2, duration_days=7, is_system=True, coin_reward=7, xp_reward=12,
            trigger_filter={"allowed_triggers": ["movement_session"]},
        )
        QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill)
        self.snack = ItemDefinition.objects.create(slug="personal-promised-food", name="My promised snack", item_type="food")
        self.reward = QuestRewardItem.objects.create(quest_definition=self.definition, item=self.snack, quantity=2)

    def log_movement(self, minutes=5):
        response = self.client.post("/api/movement-sessions/", {
            "movement_type_id": self.running.pk, "duration_minutes": minutes,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def own_goal(self, user=None):
        return self.client.post("/api/challenges/goals/", {
            "user_id": (user or self.parent).pk, "name": "My movement goal",
            "trigger_type": "movement_session", "metric": "count", "target": 1,
            "unit": "actions", "period": "this_week", "repeat_weekly": True,
            "coin_reward": 3, "xp_reward": 6,
            "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
        }, format="json")

    def test_parent_catalog_and_saved_activity_award_own_challenge_and_bonus_once(self):
        response = self.client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["daily_bonus"])
        occurrence = ChallengeOccurrence.objects.get(goal__user=self.parent)
        # Later catalog edits cannot change this account's accepted promise.
        self.definition.coin_reward = 999
        self.definition.xp_reward = 999
        self.definition.save(update_fields=["coin_reward", "xp_reward"])
        self.reward.quantity = 9
        self.reward.save(update_fields=["quantity"])
        self.assertEqual(self.client.post(f"/api/challenges/goal:{occurrence.pk}/pin/", {}, format="json").status_code, 200)
        first = self.log_movement()
        self.log_movement()
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (2, "completed"))
        self.assertEqual(occurrence.reward_receipt["coins"], 7)
        self.assertEqual(occurrence.reward_receipt["xp"], 12)
        self.assertEqual(DailyBonus.objects.get(user=self.parent).coins_awarded, 10)
        self.assertGreaterEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, 32)
        self.parent.character_profile.refresh_from_db()
        self.assertEqual(self.parent.character_profile.login_streak, 1)
        before = list(CoinLedger.objects.filter(user=self.parent).values_list("pk", "amount"))
        record_activity(self.parent, "movement_session", {"session_id": first.data["id"], "duration_minutes": 99999})
        self.client.get("/api/challenges/")
        self.assertEqual(list(CoinLedger.objects.filter(user=self.parent).values_list("pk", "amount")), before)
        self.assertEqual(ChallengeContribution.objects.filter(occurrence=occurrence).count(), 2)
        self.assertEqual(UserInventory.objects.get(user=self.parent, item=self.snack).quantity, 2)
        self.assertFalse(ChallengeGoal.objects.filter(user__in=[self.child, self.coparent]).exists())
        self.assertFalse(CoinLedger.objects.filter(user__in=[self.child, self.coparent]).exists())
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.role, "parent")

    def test_parent_cannot_credit_child_saved_work_as_personal_evidence(self):
        self.client.force_authenticate(self.child)
        child_source = self.log_movement(10)
        self.client.force_authenticate(self.parent)
        self.client.get("/api/challenges/")
        result = record_activity(self.parent, "movement_session", {"session_id": child_source.data["id"]})
        self.assertEqual(result, {"goals": [], "daily_bonus": None})
        self.assertFalse(ChallengeActivity.objects.filter(user=self.parent).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.parent).exists())
        self.assertEqual(ChallengeOccurrence.objects.get(goal__user=self.parent).progress, 0)

    def test_personal_goals_create_for_self_and_preserve_future_setup(self):
        response = self.own_goal()
        self.assertEqual(response.status_code, 201, response.data)
        goal = ChallengeGoal.objects.get(user=self.parent, is_catalog=False)
        self.assertEqual(response.data["origin"], "parent")
        schedule = self.client.patch(f"/api/challenges/goals/{goal.pk}/schedule/", {
            "expected_revision": 0, "paused": True,
        }, format="json")
        self.assertEqual(schedule.status_code, 200, schedule.data)
        self.log_movement()
        occurrence = goal.occurrences.get()
        self.assertEqual((occurrence.progress, occurrence.status), (1, "completed"))

    def test_personal_goal_creation_rechecks_self_authority_under_account_lock(self):
        from apps.quests import goals
        native_create = goals.create_goal
        users = type(self.parent).objects
        other = make_family("Moved personal parent")
        for changes in ({"is_active": False}, {"role": "child"}, {"family_id": other.family.pk}):
            before = {field: getattr(self.parent, field) for field in changes}

            def changed_account(parent, child, data, **kwargs):
                users.filter(pk=parent.pk).update(**changes)
                return native_create(parent, child, data, **kwargs)

            try:
                with self.subTest(changes=changes), patch(
                    "apps.quests.goal_views.create_goal", side_effect=changed_account,
                ):
                    response = self.own_goal()
                    self.assertEqual(response.status_code, 403, response.data)
                    self.assertFalse(ChallengeGoal.objects.exists())
                    self.assertFalse(CoinLedger.objects.exists())
            finally:
                users.filter(pk=self.parent.pk).update(**before)

    def test_personal_mode_forbids_child_and_coparent_selectors(self):
        for user in (self.child, self.coparent):
            with self.subTest(target=user.pk):
                self.assertEqual(self.client.get(f"/api/challenges/?user_id={user.pk}").status_code, 404)
                self.assertEqual(self.own_goal(user).status_code, 404)
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_personal_parent_cannot_retry_or_reschedule_child_goal(self):
        self.client.credentials()
        created = self.own_goal(self.child)
        self.assertEqual(created.status_code, 201, created.data)
        goal = ChallengeGoal.objects.get(user=self.child)
        self.client.credentials(HTTP_X_ABBY_SPACE="personal")
        schedule = self.client.patch(f"/api/challenges/goals/{goal.pk}/schedule/", {
            "expected_revision": 0, "paused": True,
        }, format="json")
        self.assertEqual(schedule.status_code, 404)
        occurrence = goal.occurrences.get()
        retry = self.client.post(f"/api/challenges/goal:{occurrence.pk}/retry/", {}, format="json")
        self.assertEqual(retry.status_code, 404)

    def test_family_management_and_child_self_participation_remain_available(self):
        self.client.credentials()
        self.assertEqual(self.own_goal(self.child).status_code, 201)
        self.assertEqual(self.client.get(f"/api/challenges/?user_id={self.child.pk}").status_code, 200)
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["origin"] == "catalog" for row in response.data["results"]))
        self.assertEqual(self.own_goal().status_code, 403)
        self.assertEqual(self.client.get(f"/api/challenges/?user_id={self.parent.pk}").status_code, 404)

    def test_parent_can_open_and_retry_only_own_accepted_catalog_window(self):
        self.client.get("/api/challenges/")
        occurrence = ChallengeOccurrence.objects.filter(goal__user=self.parent).first()
        self.assertIsNotNone(occurrence)
        opened = self.client.post(f"/api/challenges/goal:{occurrence.pk}/opened/", {}, format="json")
        self.assertEqual(opened.status_code, 200, opened.data)
        old_end = occurrence.ends_at
        with patch("django.utils.timezone.now", return_value=old_end + timedelta(seconds=1)):
            retried = self.client.post(f"/api/challenges/goal:{occurrence.pk}/retry/", {}, format="json")
        self.assertEqual(retried.status_code, 201, retried.data)
        self.assertEqual(ChallengeOccurrence.objects.filter(goal=occurrence.goal).count(), 2)

    def test_personal_legacy_assignment_targets_self_and_uses_native_progress(self):
        legacy = QuestDefinition.objects.create(
            name="My saved quest", description="A personal legacy promise", quest_type="collection",
            target_value=1, duration_days=7, created_by=self.parent, coin_reward=4,
            trigger_filter={"allowed_triggers": ["movement_session"]},
        )
        denied = self.client.post(f"/api/quests/{legacy.pk}/assign/", {"user_id": self.child.pk}, format="json")
        self.assertEqual(denied.status_code, 404)
        assigned = self.client.post(f"/api/quests/{legacy.pk}/assign/", {"user_id": self.parent.pk}, format="json")
        self.assertEqual(assigned.status_code, 201, assigned.data)
        self.log_movement()
        history = self.client.get("/api/quests/history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data[0]["status"], "completed")
        self.assertTrue(CoinLedger.objects.filter(user=self.parent, amount=4).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertEqual(self.client.post(f"/api/quests/{legacy.pk}/co-op/", {
            "user_ids": [self.parent.pk, self.child.pk],
        }, format="json").status_code, 404)

    def test_parent_failed_payout_is_repaired_from_same_saved_evidence(self):
        self.definition.target_value = 1
        self.definition.save(update_fields=["target_value"])
        with self.assertLogs("apps.quests.activity", level="ERROR"):
            with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("retry me")):
                self.log_movement(10)
        self.assertEqual(ChallengeActivity.objects.filter(user=self.parent, processed_at__isnull=True).count(), 1)
        self.assertEqual(retry_pending_activity(self.parent), 1)
        occurrence = ChallengeOccurrence.objects.get(goal__user=self.parent)
        self.assertEqual(occurrence.status, "completed")
        self.assertEqual(DailyBonus.objects.filter(user=self.parent, awarded_at__isnull=False).count(), 1)
        before = CoinLedger.objects.filter(user=self.parent).count()
        self.assertEqual(retry_pending_activity(self.parent), 0)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent).count(), before)
