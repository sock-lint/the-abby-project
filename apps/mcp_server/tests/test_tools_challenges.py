"""Modern MCP challenge authoring shares the real validator and reward service."""
import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pydantic import ValidationError

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.mcp_server.challenge_schemas import (
    CreateChallengeGoalIn, ListChallengesIn, PinChallengeIn, PreviewChallengeGoalIn,
)
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.tools import challenges
from apps.quests.goals import create_goal
from apps.quests.models import (
    ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal,
    ChallengeOccurrence, ChallengePin, DailyBonus, DailyChallenge, QuestDefinition,
)
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class ModernChallengeToolsTests(TestCase):
    def setUp(self):
        household = make_family("MCP challenge household", parents=[{"username": "challenge-parent"}],
                                children=[{"username": "challenge-child"}, {"username": "challenge-sibling"}])
        self.parent, self.child, self.sibling = household.parents[0], *household.children
        self.other = make_family("Other MCP household", parents=[{"username": "other-challenge-parent"}],
                                 children=[{"username": "other-challenge-child"}])
        category = SkillCategory.objects.create(name="MCP Challenge skills")
        self.skill = Skill.objects.create(name="Challenge persistence", category=category)

    def fields(self, **overrides):
        fields = {"user_id": self.child.pk, "name": "Move three times", "metric": "count",
                  "target": "3", "unit": "actions", "trigger_type": "movement_session",
                  "period": "this_week", "coin_reward": 7, "xp_reward": 15,
                  "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]}
        return {**fields, **overrides}

    def occurrence(self, child=None, **overrides):
        child = child or self.child
        fields = self.fields(user_id=child.pk, **overrides)
        fields["target"] = Decimal(fields["target"])
        return create_goal(self.parent, child, fields)

    def assert_no_database_writes(self, invoke):
        with CaptureQueriesContext(connection) as queries:
            result = invoke()
        mutations = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"))]
        self.assertEqual(mutations, [])
        return result

    def test_fresh_audit_and_preview_do_not_enroll_or_materialize_catalog_goals(self):
        QuestDefinition.objects.create(name="Unenrolled catalog", quest_type="collection", target_value=2,
                                       is_system=True, trigger_filter={"allowed_triggers": ["movement_session"]})
        with override_user(self.parent):
            audit = self.assert_no_database_writes(lambda: challenges.list_challenges(ListChallengesIn(user_id=self.child.pk)))
            preview = self.assert_no_database_writes(lambda: challenges.preview_challenge_goal(PreviewChallengeGoalIn(**self.fields())))
        self.assertEqual(audit["results"], [])
        self.assertTrue(audit["saved_state_only"])
        self.assertFalse(audit["daily_bonus"]["awarded"])
        self.assertTrue(preview["valid"])
        self.assertFalse(preview["saved"])
        self.assertEqual(preview["goal"]["target"], "3.000")
        self.assertEqual(preview["timezone"], self.child.family.timezone)
        self.assertTrue(preview["may_award_on_create"])
        for model in (ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, ChallengeContribution,
                      ChallengePin, DailyBonus, DailyChallenge, CoinLedger, SkillProgress):
            self.assertEqual(model.objects.count(), 0, model.__name__)

    def test_audit_returns_frozen_promises_actual_receipts_and_no_private_source_context(self):
        occurrence = self.occurrence()
        ChallengeGoal.objects.filter(pk=occurrence.goal_id).update(coin_reward=999)
        now = timezone.now()
        occurrence.status = "completed"
        occurrence.awarded_at = now
        occurrence.reward_receipt = {"coins": 14, "xp": 30, "items": [{"item_name": "Saved egg", "quantity": 1}]}
        occurrence.save(update_fields=["status", "awarded_at", "reward_receipt"])
        ChallengeActivity.objects.create(user=self.child, source_type="journal", source_id="synthetic",
            trigger_type="journal_entry", occurred_at=now, occurred_on=now.date(),
            context={"private_text": "Do not transfer journal prose", "_receipt": {"goals": [{"id": "saved-receipt"}]}})
        DailyBonus.objects.create(user=self.child, date=timezone.localdate(), timezone_name="America/Phoenix",
                                  completed_at=now, awarded_at=now, coins_awarded=20, xp_awarded=40)
        with override_user(self.parent):
            audit = self.assert_no_database_writes(lambda: challenges.list_challenges(ListChallengesIn(user_id=self.child.pk)))
        row = audit["results"][0]
        self.assertEqual(row["origin"], "parent")
        self.assertEqual(row["rewards"]["coins"], 7)
        self.assertEqual(row["reward_receipt"]["coins_awarded"], 14)
        self.assertEqual(row["reward_receipt"]["xp_awarded"], 30)
        self.assertEqual(row["reward_receipt"]["items"], occurrence.reward_receipt["items"])
        self.assertEqual(audit["recent_receipts"][0], row)
        self.assertEqual(audit["challenge_receipts"], [{"goals": [{"id": "saved-receipt"}]}])
        self.assertEqual(audit["daily_bonus"]["coins_awarded"], 20)
        self.assertNotIn("Do not transfer", json.dumps(audit))

    def test_create_requires_uuid_and_uses_service_backfill_and_once_only_rewards(self):
        with self.assertRaises(ValidationError):
            CreateChallengeGoalIn(**self.fields())
        now = timezone.now()
        ChallengeActivity.objects.create(user=self.child, source_type="movement_session", source_id="existing",
            trigger_type="movement_session", occurred_at=now - timedelta(minutes=1),
            occurred_on=timezone.localdate(), context={"duration_minutes": 5})
        params = CreateChallengeGoalIn(**self.fields(target="1"), request_id=uuid4())
        with override_user(self.parent):
            first = challenges.create_challenge_goal(params)
            retry = challenges.create_challenge_goal(params)
        self.assertEqual(first["id"], retry["id"])
        self.assertEqual(first["reward_receipt"], retry["reward_receipt"])
        self.assertEqual(first["reward_receipt"]["status"], "awarded")
        self.assertEqual(first["reward_receipt"]["coins_awarded"], 7)
        self.assertEqual(first["reward_receipt"]["xp_awarded"], 15)
        self.assertEqual(ChallengeGoal.objects.filter(created_by=self.parent).count(), 1)
        self.assertEqual(ChallengeContribution.objects.count(), 1)
        self.assertEqual(list(CoinLedger.objects.values_list("amount", flat=True)), [7])
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)
        with override_user(self.parent), self.assertRaisesMessage(MCPValidationError, "different goal details"):
            challenges.create_challenge_goal(params.model_copy(update={"name": "Changed request"}))
        self.assertEqual(CoinLedger.objects.count(), 1)

    def test_preview_uses_domain_validation_for_units_skills_dates_and_recurrence(self):
        cases = [{"metric": "minutes", "trigger_type": "chore_complete", "unit": "minutes"},
                 {"metric": "count", "target": "0.5"}, {"unit": "km"},
                 {"xp_reward": 10, "skill_tags": []},
                 {"skill_tags": [{"skill_id": 999999, "xp_weight": 1}]},
                 {"period": "custom"}, {"period": "from_today", "repeat_weekly": True}]
        with override_user(self.parent):
            for fields in cases:
                with self.subTest(fields=fields), self.assertRaises(MCPValidationError):
                    challenges.preview_challenge_goal(PreviewChallengeGoalIn(**self.fields(**fields)))
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_family_and_parent_gates_apply_before_any_goal_mutation(self):
        with override_user(self.other.parents[0]):
            for invoke in (lambda: challenges.list_challenges(ListChallengesIn(user_id=self.child.pk)),
                           lambda: challenges.preview_challenge_goal(PreviewChallengeGoalIn(**self.fields())),
                           lambda: challenges.create_challenge_goal(CreateChallengeGoalIn(**self.fields(), request_id=uuid4()))):
                with self.assertRaises(MCPNotFoundError):
                    invoke()
        with override_user(self.child):
            self.assertEqual(challenges.list_challenges(ListChallengesIn())["user_id"], self.child.pk)
            with self.assertRaises(MCPPermissionDenied):
                challenges.list_challenges(ListChallengesIn(user_id=self.sibling.pk))
            with self.assertRaises(MCPPermissionDenied):
                challenges.preview_challenge_goal(PreviewChallengeGoalIn(**self.fields()))
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            challenges.preview_challenge_goal(PreviewChallengeGoalIn(**self.fields(user_id=self.parent.pk)))
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_parent_pin_targets_child_and_never_changes_progress_or_pays(self):
        occurrence = self.occurrence()
        params = PinChallengeIn(user_id=self.child.pk, challenge_id=f"goal:{occurrence.pk}")
        with override_user(self.parent):
            self.assertEqual(challenges.pin_challenge(params), {"pin": params.challenge_id})
            self.assertEqual(challenges.pin_challenge(params), {"pin": params.challenge_id})
            self.assertEqual(challenges.unpin_challenge(params), {"pin": None})
            self.assertEqual(challenges.unpin_challenge(params), {"pin": None})
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 0)
        self.assertIsNone(occurrence.awarded_at)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())
        with override_user(self.other.parents[0]), self.assertRaises(MCPNotFoundError):
            challenges.pin_challenge(params)
        with override_user(self.sibling), self.assertRaises(MCPValidationError):
            challenges.pin_challenge(PinChallengeIn(challenge_id=params.challenge_id))

    def test_audit_and_inputs_are_bounded_and_reject_server_owned_fields(self):
        for index in range(3):
            self.occurrence(name=f"Goal {index}")
        with override_user(self.parent):
            payload = challenges.list_challenges(ListChallengesIn(user_id=self.child.pk, limit=2))
        self.assertEqual(len(payload["results"]), 2)
        with self.assertRaises(ValidationError):
            ListChallengesIn(limit=101)
        for extra in ({"progress": 5}, {"reward_receipt": {"coins": 999}}, {"is_catalog": True}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                PreviewChallengeGoalIn(**self.fields(), **extra)
