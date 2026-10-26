"""Modern challenge mutations keep current authority and recover saved UUIDs."""
import json
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.achievements.models import Skill, SkillCategory
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import challenges
from apps.movement.models import MovementType
from apps.quests.models import ChallengeActivity, ChallengeGoal, ChallengeOccurrence, ChallengePin
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChallengeMutationFixtures(TestCase):
    def setUp(self):
        family = make_family(
            "Modern challenge boundaries", parents=[{"username": "boundary-parent", "is_staff": True}],
            children=[{"username": "boundary-child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.at = datetime(2026, 10, 26, 12, tzinfo=datetime_timezone.utc)
        family.family.timezone = "UTC"
        family.family.save(update_fields=["timezone"])

    def params(self, **changes):
        return {
            "user_id": self.child.pk, "name": "A saved parent goal", "metric": "count",
            "target": "1", "unit": "actions", "trigger_type": "habit_log", "period": "this_week",
            "coin_reward": 7, "request_id": str(uuid4()), **changes,
        }

    def call(self, tool, params, *, actor=None, write=True):
        async def invoke():
            with override_user(actor or self.parent, scopes=frozenset({"mcp:write", "mcp:read"})):
                return await mcp.call_tool(tool, {
                    "params": params, **({"confirmation": True} if write else {}),
                })

        result = async_to_sync(invoke)()
        if isinstance(result, tuple):
            blocks, payload = result
            error = False
        else:
            blocks, payload, error = result.content, result.structuredContent, bool(result.isError)
        self.assertEqual(json.loads([block.text for block in blocks if block.type == "text"][0]), payload)
        return error, payload

    def create(self, params=None):
        with patch("django.utils.timezone.now", return_value=self.at):
            error, payload = self.call("create_challenge_goal", params or self.params())
        self.assertFalse(error, payload)
        return payload


class ModernChallengeMutationAuthorityTests(ChallengeMutationFixtures):
    def test_revoked_parent_cannot_create_goal_or_award_saved_facts(self):
        ChallengeActivity.objects.create(
            user=self.child, source_type="habit_log", source_id="existing-boundary-fact",
            trigger_type="habit_log", occurred_at=self.at - timedelta(minutes=1),
            occurred_on=self.at.date(), context={},
        )
        get_user_model().objects.filter(pk=self.parent.pk).update(role="child")
        with patch("django.utils.timezone.now", return_value=self.at):
            error, payload = self.call("create_challenge_goal", self.params())
        self.assertTrue(error, payload)
        self.assertEqual(payload["error"]["code"], "permission_denied")
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_revoked_parent_cannot_pin_child_challenge(self):
        saved = self.create()
        get_user_model().objects.filter(pk=self.parent.pk).update(role="child")
        error, payload = self.call("pin_challenge", {
            "user_id": self.child.pk, "challenge_id": saved["id"],
        })
        self.assertTrue(error, payload)
        self.assertEqual(payload["error"]["code"], "permission_denied")
        self.assertFalse(ChallengePin.objects.filter(occurrence__isnull=False).exists())

    def test_current_read_and_foreign_creation_controls_deny_without_writes(self):
        saved = self.create()
        get_user_model().objects.filter(pk=self.parent.pk).update(role="child")
        error, payload = self.call("get_challenge", {
            "user_id": self.child.pk, "challenge_id": saved["id"],
        }, write=False)
        self.assertTrue(error, payload)
        self.assertEqual(payload["error"]["code"], "permission_denied")
        foreign = make_family("Foreign boundary family", parents=[{
            "username": "foreign-boundary-parent", "is_staff": True,
        }]).parents[0]
        error, payload = self.call("create_challenge_goal", self.params(), actor=foreign)
        self.assertTrue(error, payload)
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertEqual(ChallengeGoal.objects.count(), 1)

    def test_preview_create_replay_and_pin_writes_recheck_all_current_members(self):
        params = self.params()
        saved = self.create(params)
        pin_params = {"user_id": self.child.pk, "challenge_id": saved["id"]}
        self.assertEqual(self.call("pin_challenge", pin_params), (False, {"pin": saved["id"]}))
        foreign = make_family("Changed boundary family").family
        users = get_user_model().objects
        operations = (
            ("preview_challenge_goal", {key: value for key, value in params.items() if key != "request_id"}),
            ("create_challenge_goal", self.params()), ("create_challenge_goal", params),
            ("pin_challenge", pin_params), ("unpin_challenge", pin_params),
        )
        before = (list(ChallengeGoal.objects.values()), list(ChallengeOccurrence.objects.values()),
                  list(ChallengePin.objects.values()), list(CoinLedger.objects.values()))
        for member, change, expected in (
            (self.parent, {"role": "child"}, "permission_denied"),
            (self.parent, {"is_active": False}, "permission_denied"),
            (self.parent, {"is_staff": False}, "permission_denied"),
            (self.parent, {"family_id": foreign.pk}, "permission_denied"),
            (self.child, {"role": "parent"}, "not_found"),
            (self.child, {"is_active": False}, "not_found"),
            (self.child, {"family_id": foreign.pk}, "not_found"),
        ):
            original = {field: getattr(member, field) for field in change}
            users.filter(pk=member.pk).update(**change)
            try:
                for tool, payload in operations:
                    if member == self.child and change == {"role": "parent"} and tool in {"pin_challenge", "unpin_challenge"}:
                        continue  # A currently selected co-parent remains an authorized same-family target.
                    with self.subTest(member=member.username, change=change, tool=tool):
                        error, result = self.call(tool, payload)
                        self.assertTrue(error, result)
                        self.assertEqual(result["error"]["code"], expected)
            finally:
                users.filter(pk=member.pk).update(**original)
        self.assertEqual(before, (list(ChallengeGoal.objects.values()), list(ChallengeOccurrence.objects.values()),
                                  list(ChallengePin.objects.values()), list(CoinLedger.objects.values())))

    def test_pin_role_change_after_resolution_is_denied_but_current_coparent_target_remains_allowed(self):
        saved = self.create()
        params = {"user_id": self.child.pk, "challenge_id": saved["id"]}
        self.assertEqual(self.call("pin_challenge", params), (False, {"pin": saved["id"]}))
        resolve = challenges.resolve_target_user

        def resolve_then_change(actor, user_id):
            selected = resolve(actor, user_id)
            get_user_model().objects.filter(pk=selected.pk).update(role="parent")
            return selected

        before = list(ChallengePin.objects.values())
        for tool in ("pin_challenge", "unpin_challenge"):
            with patch.object(challenges, "resolve_target_user", side_effect=resolve_then_change):
                error, payload = self.call(tool, params)
            get_user_model().objects.filter(pk=self.child.pk).update(role="child")
            self.assertTrue(error, payload)
            self.assertEqual(payload["error"]["code"], "not_found")
        self.assertEqual(before, list(ChallengePin.objects.values()))
        get_user_model().objects.filter(pk=self.child.pk).update(role="parent")
        self.assertEqual(self.call("unpin_challenge", params), (False, {"pin": None}))

    def test_child_self_pin_and_parent_explicit_target_keep_saved_state(self):
        saved = self.create()
        error, payload = self.call("pin_challenge", {"challenge_id": saved["id"]}, actor=self.child)
        self.assertEqual((error, payload), (False, {"pin": saved["id"]}))
        error, payload = self.call("unpin_challenge", {
            "user_id": self.child.pk, "challenge_id": saved["id"],
        })
        self.assertEqual((error, payload), (False, {"pin": None}))
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertEqual(ChallengePin.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())


class ModernChallengeGoalRecoveryTests(ChallengeMutationFixtures):
    def test_custom_goal_uuid_replay_recovers_after_original_end_date(self):
        params = self.params(period="custom", start_date="2026-10-26", end_date="2026-10-26")
        saved = self.create(params)
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(days=1)):
            error, replay = self.call("create_challenge_goal", params)
        self.assertFalse(error, replay)
        self.assertEqual(replay["id"], saved["id"])
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_saved_reward_and_pin_recover_after_retirement_and_deleted_skill_without_repayout(self):
        category = SkillCategory.objects.create(name="Saved recovery skills")
        skill = Skill.objects.create(name="Saved recovery skill", category=category)
        ChallengeActivity.objects.create(
            user=self.child, source_type="habit_log", source_id="rewarded-recovery-fact",
            trigger_type="habit_log", occurred_at=self.at - timedelta(minutes=1),
            occurred_on=self.at.date(), context={},
        )
        params = self.params(xp_reward=15, skill_tags=[{"skill_id": skill.pk}])
        saved = self.create(params)
        self.assertEqual(saved["reward_receipt"]["coins_awarded"], 7)
        self.assertEqual(saved["reward_receipt"]["xp_awarded"], 15)
        self.call("pin_challenge", {"user_id": self.child.pk, "challenge_id": saved["id"]})
        before = (list(ChallengeGoal.objects.values()), list(ChallengeOccurrence.objects.values()),
                  list(ChallengePin.objects.values()), list(CoinLedger.objects.values()))
        Skill.objects.filter(pk=skill.pk).update(is_retired=True)
        for delete in (False, True):
            if delete:
                skill.delete()  # Historical JSON promises can outlive their referenced taxonomy row.
            with self.subTest(deleted=delete):
                error, replay = self.call("create_challenge_goal", params)
                self.assertFalse(error, replay)
                self.assertEqual(replay["id"], saved["id"])
                self.assertEqual(replay["reward_receipt"], saved["reward_receipt"])
                error, rejected = self.call("create_challenge_goal", {**params, "request_id": str(uuid4())})
                self.assertTrue(error, rejected)
                self.assertEqual(rejected["error"]["code"], "invalid_request")
        self.assertEqual(before, (list(ChallengeGoal.objects.values()), list(ChallengeOccurrence.objects.values()),
                                  list(ChallengePin.objects.values()), list(CoinLedger.objects.values())))

    def test_inactive_movement_choice_does_not_prevent_exact_saved_recovery(self):
        movement = MovementType.objects.create(name="Recovery walk", slug="recovery-walk")
        params = self.params(trigger_type="movement_session", movement_type_id=movement.pk)
        saved = self.create(params)
        MovementType.objects.filter(pk=movement.pk).update(is_active=False)
        error, replay = self.call("create_challenge_goal", params)
        self.assertFalse(error, replay)
        self.assertEqual(replay["id"], saved["id"])
        error, rejected = self.call("create_challenge_goal", {**params, "request_id": str(uuid4())})
        self.assertTrue(error, rejected)
        self.assertEqual(rejected["error"]["code"], "invalid_request")
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_current_actor_and_child_cannot_recover_former_family_result(self):
        params = self.params()
        saved = self.create(params)
        other = make_family("New recovery family").family
        get_user_model().objects.filter(pk__in=[self.parent.pk, self.child.pk]).update(family=other)
        self.parent.refresh_from_db()
        self.child.refresh_from_db()
        error, result = self.call("create_challenge_goal", params)
        self.assertTrue(error, result)
        self.assertEqual(result["error"]["code"], "not_found")
        self.assertNotIn(saved["id"], json.dumps(result))
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_missing_occurrence_never_recreates_an_accepted_uuid(self):
        params = self.params()
        self.create(params)
        ChallengeOccurrence.objects.all().delete()
        error, result = self.call("create_challenge_goal", params)
        self.assertTrue(error, result)
        self.assertEqual(result["error"]["code"], "not_found")
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_recovery_keeps_payload_fingerprints_structural_checks_and_new_date_validation(self):
        params = self.params(period="custom", start_date="2026-10-26", end_date="2026-10-26")
        self.create(params)
        with patch("django.utils.timezone.now", return_value=self.at + timedelta(days=1)):
            for changes in ({"name": "Changed"}, {"coin_reward": 8}, {"target": "2"}):
                with self.subTest(changes=changes):
                    error, result = self.call("create_challenge_goal", {**params, **changes})
                    self.assertTrue(error, result)
                    self.assertIn("different goal details", result["error"]["message"])
            error, result = self.call("create_challenge_goal", {**params, "request_id": str(uuid4())})
            self.assertTrue(error, result)
            self.assertIn("end_date", result["error"]["message"])
            for changes, code in (({"target": "0.5"}, "invalid_request"),
                                  ({"unit": "minutes"}, "invalid_request"),
                                  ({"end_date": "2026-10-25"}, "invalid_request"),
                                  ({"reward_receipt": {"coins": 999}}, "invalid_input")):
                with self.subTest(structural_change=changes):
                    error, result = self.call("create_challenge_goal", {**params, **changes})
                    self.assertTrue(error, result)
                    self.assertEqual(result["error"]["code"], code)
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_omitted_and_explicit_defaults_keep_the_native_request_fingerprint(self):
        params = self.params()
        saved = self.create(params)
        goal = ChallengeGoal.objects.get()
        fingerprint = goal.request_fingerprint
        error, replay = self.call("create_challenge_goal", {
            **params, "description": "", "xp_reward": 0, "skill_tags": [], "repeat_weekly": False,
        })
        self.assertFalse(error, replay)
        self.assertEqual(replay["id"], saved["id"])
        goal.refresh_from_db()
        self.assertEqual(goal.request_fingerprint, fingerprint)
        self.assertEqual(ChallengeGoal.objects.count(), 1)

    def test_preview_still_rejects_expired_and_unavailable_new_choices(self):
        movement = MovementType.objects.create(name="Preview recovery walk", slug="preview-recovery-walk", is_active=False)
        for changes, field in (({"period": "custom", "start_date": "2026-10-25", "end_date": "2026-10-25"}, "end_date"),
                               ({"trigger_type": "movement_session", "movement_type_id": movement.pk}, "movement_type_id"),
                               ({"skill_tags": [{"skill_id": 999999999}]}, "skill_tags")):
            params = {key: value for key, value in self.params(**changes).items() if key != "request_id"}
            with self.subTest(changes=changes), patch("django.utils.timezone.now", return_value=self.at):
                error, result = self.call("preview_challenge_goal", params)
                self.assertTrue(error, result)
                self.assertIn(field, result["error"]["message"])
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
