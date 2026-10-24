"""Legacy household RPG tools retain current authority, not an authentication snapshot."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.mcp_server.auth import _resolve_access
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import achievements, rewards
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger, Reward
from apps.rewards.services import CoinService, RewardService
from config.tests.factories import make_family, make_oauth_token


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   MCP_RESOURCE_URL="http://synthetic.invalid/mcp")
class RemainingRPGAuthorityTests(TestCase):
    def setUp(self):
        home = make_family("Remaining RPG", parents=[{"username": "rpg-parent", "is_staff": True}],
                           children=[{"username": "rpg-child"}, {"username": "rpg-sibling"}])
        self.parent, self.child, self.sibling = home.parents[0], *home.children
        other = make_family("Foreign RPG", children=[{"username": "rpg-foreign"}])
        self.other_family, self.foreign = other.family, other.children[0]
        token, _ = make_oauth_token(self.parent, scope="mcp:read mcp:write")
        self.actor, self.scopes = _resolve_access(token.token)
        self.category = SkillCategory.objects.create(name="Private practice category")
        self.skill = Skill.objects.create(name="Private practice", category=self.category)
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=37, level=1)
        self.badge = Badge.objects.create(name="Earned practice badge", criteria_type="projects_completed",
                                          criteria_value={"count": 99}, award_coins=False, xp_bonus=0)
        UserBadge.objects.create(user=self.child, badge=self.badge)
        self.reward = Reward.objects.create(family=self.parent.family, name="Private household treat",
                                           cost_coins=5, stock=3, requires_parent_approval=True)
        self.unused_reward = Reward.objects.create(family=self.parent.family, name="Unused household treat", cost_coins=1)
        CoinService.award_coins(self.child, 50, CoinLedger.Reason.ADJUSTMENT)
        self.redemption = RewardService.request_redemption(self.child, self.reward)
        self.definition = QuestDefinition.objects.create(name="Private household quest", quest_type="boss",
                                                         target_value=100, created_by=self.parent, is_system=False)
        self.quest = Quest.objects.create(definition=self.definition, end_date=timezone.now() + timedelta(days=7))
        QuestParticipant.objects.create(quest=self.quest, user=self.child, contribution=7)

    def wire(self, name, params=None, *, actor=None, scopes=None, confirmation=True):
        with override_user(actor or self.actor, scopes=self.scopes if scopes is None else scopes):
            result = async_to_sync(mcp.call_tool)(name, {"params": params or {}, "confirmation": confirmation})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def assert_error(self, result, code):
        self.assertIn("error", result, result)
        self.assertEqual(result["error"]["code"], code, result)

    def operations(self):
        target = {"user_id": self.child.pk}
        return [
            ("get_skill_tree", {**target, "category_id": self.category.pk}),
            ("list_earned_badges", target), ("list_rewards", {}), ("get_coin_balance", target),
            ("adjust_coins", {**target, "amount": 13, "description": "Parent adjustment"}),
            ("approve_redemption", {"redemption_id": self.redemption.pk}),
            ("reject_redemption", {"redemption_id": self.redemption.pk}),
            ("create_reward", {"name": "New treat", "cost_coins": 1}),
            ("update_reward", {"reward_id": self.reward.pk, "name": "Changed treat"}),
            ("delete_reward", {"reward_id": self.unused_reward.pk}),
            ("list_quests", {}), ("get_quest", {"quest_id": self.quest.pk}),
            ("list_quest_catalog", {}),
            ("assign_quest", {**target, "definition_id": self.definition.pk}),
            ("assign_co_op_quest", {"user_ids": [self.child.pk, self.sibling.pk], "definition_id": self.definition.pk}),
            ("cancel_quest", {"quest_id": self.quest.pk}),
            ("set_quest_definition_skill_tags", {"quest_definition_id": self.definition.pk, "skill_tags": []}),
            ("delete_quest_definition", {"quest_definition_id": self.definition.pk}),
            ("create_quest_definition", {"name": "New private quest", "description": "Private practice",
                                         "quest_type": "boss", "target_value": 100}),
        ]

    def test_each_legacy_household_handler_rechecks_authenticated_parent(self):
        for changes in ({"family": self.other_family}, {"role": "child"},
                        {"is_staff": False}, {"is_active": False}):
            get_user_model().objects.filter(pk=self.parent.pk).update(**changes)
            try:
                for name, params in self.operations():
                    with self.subTest(changes=changes, tool=name):
                        self.assert_error(self.wire(name, params), "permission_denied")
            finally:
                get_user_model().objects.filter(pk=self.parent.pk).update(
                    family_id=self.parent.family_id, role="parent", is_staff=True, is_active=True,
                )

    def test_departed_parent_cannot_read_private_progress_or_grant_coins(self):
        before = list(CoinLedger.objects.values())
        get_user_model().objects.filter(pk=self.parent.pk).update(family=self.other_family)
        self.assert_error(self.wire("get_skill_tree", {"user_id": self.child.pk, "category_id": self.category.pk}),
                          "permission_denied")
        self.assert_error(self.wire("adjust_coins", {"user_id": self.child.pk, "amount": 13, "description": "Adjustment"}),
                          "permission_denied")
        self.assertEqual(list(CoinLedger.objects.values()), before)

    def test_target_move_after_scalar_resolution_cannot_read_or_change_new_family_data(self):
        for module, name, params, resolver in (
            (rewards, "adjust_coins", {"user_id": self.child.pk, "amount": 13, "description": "Adjustment"}, "resolve_child_in_family"),
            (achievements, "get_skill_tree", {"user_id": self.child.pk, "category_id": self.category.pk}, "resolve_target_user"),
        ):
            original = getattr(module, resolver)

            def moved(actor, child_id):
                target = original(actor, child_id)
                get_user_model().objects.filter(pk=target.pk).update(family=self.other_family)
                return target

            before = list(CoinLedger.objects.values())
            with self.subTest(tool=name), patch.object(module, resolver, side_effect=moved):
                self.assert_error(self.wire(name, params), "not_found")
            self.assertEqual(list(CoinLedger.objects.values()), before)
            get_user_model().objects.filter(pk=self.child.pk).update(family_id=self.parent.family_id)

    def test_inactive_child_history_is_readable_without_awards(self):
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)
        before = list(CoinLedger.objects.values())
        for name, params in (
            ("get_skill_tree", {"user_id": self.child.pk, "category_id": self.category.pk}),
            ("list_earned_badges", {"user_id": self.child.pk}),
            ("get_coin_balance", {"user_id": self.child.pk}),
            ("list_quests", {"user_id": self.child.pk}), ("get_quest", {"quest_id": self.quest.pk}),
        ):
            with self.subTest(tool=name):
                self.assertNotIn("error", self.wire(name, params))
        self.assertEqual(list(CoinLedger.objects.values()), before)

    def test_parent_and_child_self_reads_preserve_scope_and_confirmation_controls(self):
        self.assertEqual(self.wire("get_coin_balance", {"user_id": self.child.pk})["balance"], 45)
        self.assertEqual(self.wire("get_coin_balance", actor=self.child)["balance"], 45)
        self.assertEqual(self.wire("get_quest", {"quest_id": self.quest.pk}, actor=self.child)["id"], self.quest.pk)
        params = {"user_id": self.child.pk, "amount": 13, "description": "Adjustment"}
        self.assert_error(self.wire("adjust_coins", params, confirmation=False), "confirmation_required")
        self.assert_error(self.wire("adjust_coins", params, scopes=frozenset({"mcp:read"})), "permission_denied")
        self.assert_error(self.wire("adjust_coins", {**params, "user_id": self.foreign.pk}), "not_found")
        self.assertEqual(self.wire("adjust_coins", params)["new_balance"], 58)

    def test_existing_uuid_redemption_replay_still_rechecks_authority(self):
        request = {"reward_id": self.reward.pk, "request_id": str(uuid4())}
        first = self.wire("request_redemption", request, actor=self.child)
        self.assertNotIn("error", first)
        self.assertEqual(self.wire("request_redemption", request, actor=self.child), first)
        before = list(CoinLedger.objects.values())
        get_user_model().objects.filter(pk=self.child.pk).update(family=self.other_family)
        self.assert_error(self.wire("request_redemption", request, actor=self.child), "permission_denied")
        self.assertEqual(list(CoinLedger.objects.values()), before)

    def test_local_parent_coins_do_not_gain_a_staff_requirement(self):
        get_user_model().objects.filter(pk=self.parent.pk).update(is_staff=False)
        ordinary_parent = get_user_model().objects.get(pk=self.parent.pk)
        result = self.wire("adjust_coins", {"user_id": self.child.pk, "amount": 2, "description": "Adjustment"},
                           actor=ordinary_parent)
        self.assertEqual(result["new_balance"], 47)
