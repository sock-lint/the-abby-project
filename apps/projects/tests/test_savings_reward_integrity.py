"""Saving the same money under fresh goal identities cannot mint rewards."""
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.db.models import Sum
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.criteria import _savings_goal_completed
from apps.achievements.models import Badge, UserBadge
from apps.achievements.services import BadgeService
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPValidationError
from apps.mcp_server.schemas import ListSavingsGoalsIn, UpdateSavingsGoalIn
from apps.mcp_server.shapes import savings_goal_to_dict
from apps.mcp_server.tools.savings import list_savings_goals, update_savings_goal
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import SavingsGoal, SavingsRewardProgress
from apps.projects.savings_service import SavingsGoalService
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(COINS_PER_SAVINGS_GOAL_DOLLAR=2)
class SavingsRewardIntegrityTests(TestCase):
    def setUp(self):
        self.family = make_family("Savings integrity", parents=[{"username": "saving-parent"}],
            children=[{"username": "saving-child"}])
        self.child = self.family.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def money(self, amount, *, hooked=True, kind="adjustment"):
        if hooked:
            return PaymentService.record_entry(self.child, Decimal(amount), kind)
        return PaymentLedger.objects.create(user=self.child, amount=Decimal(amount), entry_type=kind)

    def create(self, title="New target", target="50.00"):
        response = self.client.post("/api/savings-goals/", {"title": title, "target_amount": target}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return SavingsGoal.objects.get(pk=response.data["id"])

    def savings_coins(self):
        return CoinLedger.objects.filter(user=self.child, description__startswith="Savings goal:").aggregate(
            total=Sum("amount"))["total"] or 0

    def test_new_already_funded_goals_complete_without_coins_or_game_rewards(self):
        self.money("50.00", hooked=False)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
            first = self.create("Funded one")
            second = self.create("Funded two")
        self.assertTrue(first.is_completed and second.is_completed)
        self.assertEqual(self.savings_coins(), 0)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("50.00"))
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 1)
        game.assert_not_called()
        self.assertFalse(Notification.objects.filter(user=self.child, message__contains="+100 coins").exists())

    def test_rest_reads_and_mcp_reads_never_complete_or_reward_saved_goals(self):
        goal = SavingsGoal.objects.create(user=self.child, title="Pending read", target_amount=50)
        self.money("50.00", hooked=False)
        notifications = Notification.objects.count()
        self.assertEqual(self.client.get("/api/savings-goals/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/savings-goals/{goal.pk}/").status_code, 200)
        self.assertFalse(savings_goal_to_dict(goal)["is_completed"])
        with override_user(self.family.parents[0]):
            payload = list_savings_goals(ListSavingsGoalsIn(user_id=self.child.pk))
        self.assertFalse(payload["goals"][0]["is_completed"])
        goal.refresh_from_db()
        self.assertFalse(goal.is_completed)
        self.assertEqual(self.savings_coins(), 0)
        self.assertEqual(Notification.objects.count(), notifications)

    def test_background_pulse_get_cannot_settle_savings_or_advance_milestones(self):
        goal = self.create("Pending pulse target")
        self.money("50.00", hooked=False)
        response = self.client.get("/api/pulse/")
        self.assertEqual(response.status_code, 200)
        row = next(row for row in response.data["savings_goals"] if row["id"] == goal.pk)
        self.assertFalse(row["is_completed"])
        goal.refresh_from_db()
        self.assertFalse(goal.is_completed)
        self.assertEqual(self.savings_coins(), 0)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_balance, Decimal("0.00"))

    def test_overlapping_targets_pay_the_new_money_only_once(self):
        first = self.create("First fifty")
        second = self.create("Second fifty")
        self.money("50.00")
        self.assertEqual(self.savings_coins(), 100)
        self.assertTrue(SavingsGoal.objects.get(pk=first.pk).is_completed)
        self.assertTrue(SavingsGoal.objects.get(pk=second.pk).is_completed)
        SavingsGoalService.check_and_complete(self.child)
        self.assertEqual(self.savings_coins(), 100)

    def test_already_funded_goal_does_not_burn_an_older_goals_unpaid_savings(self):
        earlier = self.create("A", "100.00")
        self.money("60.00")
        self.create("B", "50.00")
        self.money("40.00")
        earlier.refresh_from_db()
        self.assertTrue(earlier.is_completed)
        self.assertEqual(self.savings_coins(), 200)

    def test_partial_later_goal_preserves_the_older_goals_unpaid_lower_range(self):
        earlier = self.create("Save the whole hundred", "100.00")
        self.money("60.00")
        later = self.create("Save twenty more", "80.00")
        self.money("20.00")
        self.assertEqual(self.savings_coins(), 40)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges, [[6000, 8000]])
        self.money("20.00")
        earlier.refresh_from_db()
        later.refresh_from_db()
        self.assertTrue(earlier.is_completed and later.is_completed)
        self.assertEqual(self.savings_coins(), 200)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges, [[0, 10000]])
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child,
            description__startswith="Savings goal:").order_by("pk").values_list("amount", flat=True)), [40, 160])

    def test_partial_range_survives_deletion_and_pays_each_goals_frozen_rate(self):
        earlier = self.create("Earlier rate two", "100.00")
        self.money("60.00")
        with override_settings(COINS_PER_SAVINGS_GOAL_DOLLAR=4):
            later = self.create("Later rate four", "80.00")
        self.money("20.00")
        self.assertEqual(self.savings_coins(), 80)
        self.assertEqual(self.client.delete(f"/api/savings-goals/{later.pk}/").status_code, 204)
        self.money("-80.00", kind="coin_exchange")
        self.money("100.00")
        earlier.refresh_from_db()
        self.assertTrue(earlier.is_completed)
        self.assertEqual(self.savings_coins(), 240)
        SavingsGoalService.check_and_complete(self.child)
        self.assertEqual(self.savings_coins(), 240)

    def test_new_or_retargeted_goals_after_spending_cannot_claim_older_goals_unpaid_holes(self):
        earlier = self.create("Original hundred", "100.00")
        retargeted = self.create("A later choice", "200.00")
        self.money("60.00")
        later = self.create("Save twenty more", "80.00")
        self.money("20.00")
        self.assertEqual(self.savings_coins(), 40)
        self.assertEqual(self.client.delete(f"/api/savings-goals/{later.pk}/").status_code, 204)
        self.money("-80.00", kind="coin_exchange")
        fresh = self.create("New identity after spending", "50.00")
        response = self.client.patch(f"/api/savings-goals/{retargeted.pk}/", {"target_amount": "250.00"})
        self.assertEqual(response.status_code, 200)
        retargeted.refresh_from_db()
        self.assertEqual(fresh.reward_start_balance, Decimal("80.00"))
        self.assertEqual(retargeted.reward_start_balance, Decimal("80.00"))
        self.money("50.00")
        self.assertFalse(SavingsGoal.objects.get(pk=fresh.pk).reward_qualifies)
        self.assertEqual(self.savings_coins(), 40)
        self.money("50.00")
        self.assertTrue(SavingsGoal.objects.get(pk=earlier.pk).reward_qualifies)
        self.assertEqual(self.savings_coins(), 200)

    def test_zero_funded_completion_reserves_admission_but_not_an_older_goals_coverage(self):
        earlier = self.create("Older hundred", "100.00")
        self.money("60.00")
        funded = self.create("Already funded fifty", "50.00")
        self.assertFalse(funded.reward_qualifies)
        progress = SavingsRewardProgress.objects.get(user=self.child)
        self.assertEqual(progress.recognized_balance, Decimal("50.00"))
        self.assertEqual(progress.recognized_ranges, [])
        self.money("-60.00", kind="coin_exchange")
        fresh = self.create("Fresh fifty after spending", "50.00")
        self.assertEqual(fresh.reward_start_balance, Decimal("50.00"))
        self.money("50.00")
        self.assertEqual(self.savings_coins(), 0)
        self.assertFalse(SavingsGoal.objects.get(pk=fresh.pk).reward_qualifies)
        self.money("50.00")
        self.assertTrue(SavingsGoal.objects.get(pk=earlier.pk).reward_qualifies)
        self.assertEqual(self.savings_coins(), 200)

    def test_uncovered_fragments_round_once_and_zero_coin_claims_still_reserve_their_range(self):
        earlier = self.create("Save one dollar", "1.00")
        self.money("0.30")
        middle = self.create("Save forty more cents", "0.70")
        self.money("0.40")
        middle.refresh_from_db()
        self.assertTrue(middle.reward_qualifies)
        self.assertEqual(self.savings_coins(), 0)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges, [[30, 70]])
        self.money("0.30")
        earlier.refresh_from_db()
        self.assertTrue(earlier.reward_qualifies)
        # Two uncovered $0.30 fragments total $0.60, paying one Coin at 2/$.
        self.assertEqual(self.savings_coins(), 1)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges, [[0, 100]])

    def test_older_goal_subtracts_multiple_disjoint_paid_bands_then_merges_coverage(self):
        earlier = self.create("Original hundred", "100.00")
        self.money("20.00")
        self.create("Twenty through forty", "40.00")
        self.money("20.00")
        self.assertEqual(self.savings_coins(), 40)
        self.money("20.00")
        self.create("Sixty through eighty", "80.00")
        self.money("20.00")
        self.assertEqual(self.savings_coins(), 80)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges,
            [[2000, 4000], [6000, 8000]])
        self.money("20.00")
        earlier.refresh_from_db()
        self.assertTrue(earlier.reward_qualifies)
        self.assertEqual(self.savings_coins(), 200)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges, [[0, 10000]])

    def test_raised_legacy_target_covers_only_its_original_accepted_principal(self):
        earlier = self.create("Unchanged hundred", "100.00")
        legacy = SavingsGoal.objects.create(user=self.child, title="Accepted fifty", target_amount=50,
            reward_policy_version=1, legacy_coin_reward=100, legacy_target_amount=50)
        SavingsGoalService.update_goal(legacy, target_amount=Decimal("75.00"))
        self.money("75.00")
        self.assertEqual(self.savings_coins(), 100)
        progress = SavingsRewardProgress.objects.get(user=self.child)
        self.assertEqual(progress.recognized_balance, Decimal("75.00"))
        self.assertEqual(progress.recognized_ranges, [[0, 5000]])
        self.money("-75.00", kind="coin_exchange")
        fresh = self.create("New eighty after spending", "80.00")
        self.assertEqual(fresh.reward_start_balance, Decimal("75.00"))
        self.money("100.00")
        earlier.refresh_from_db()
        self.assertTrue(earlier.reward_qualifies)
        self.assertEqual(self.savings_coins(), 200)

    def test_newly_lowered_funded_target_cannot_burn_an_unchanged_goals_savings(self):
        earlier = self.create("Unchanged hundred", "100.00")
        changed = self.create("Changed from two hundred", "200.00")
        self.money("60.00")
        response = self.client.patch(f"/api/savings-goals/{changed.pk}/", {"target_amount": "50.00"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SavingsGoal.objects.get(pk=changed.pk).reward_qualifies)
        self.money("40.00")
        self.assertTrue(SavingsGoal.objects.get(pk=earlier.pk).is_completed)
        self.assertEqual(self.savings_coins(), 200)

    def test_many_ascending_targets_share_one_qualifying_financial_milestone(self):
        goals = [SavingsGoal.objects.create(user=self.child, title=f"Target {number}",
            target_amount=Decimal(number) / 2) for number in range(1, 101)]
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game, patch(
            "apps.achievements.services.BadgeService.evaluate_badges",
        ) as badges:
            self.money("50.00")
        self.assertEqual(self.savings_coins(), 100)
        self.assertEqual(SavingsGoal.objects.filter(user=self.child, is_completed=True).count(), 100)
        self.assertEqual(list(SavingsGoal.objects.filter(user=self.child, reward_qualifies=True).values_list(
            "pk", flat=True)), [goals[-1].pk])
        game.assert_called_once()
        self.assertEqual(game.call_args.args[2], {"savings_goal_id": goals[-1].pk})
        badges.assert_called_once()
        self.assertFalse(_savings_goal_completed(self.child, {"count": 2}))

    def test_coalescing_retains_each_increment_starting_balance_and_frozen_rate(self):
        earlier = self.create("Save the first thirty", "30.00")
        self.money("40.00", hooked=False)
        with override_settings(COINS_PER_SAVINGS_GOAL_DOLLAR=4):
            later = SavingsGoal.objects.create(user=self.child, title="Save ten more", target_amount=50)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
            self.money("10.00")
        # The first $30 retains its 2-Coin rate; the later goal recognizes
        # only $10 above its own $40 starting balance at its frozen rate of 4.
        self.assertEqual(self.savings_coins(), 100)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child,
            description__startswith="Savings goal:").order_by("pk").values_list("amount", flat=True)), [60, 40])
        earlier.refresh_from_db()
        later.refresh_from_db()
        self.assertTrue(earlier.is_completed and later.is_completed)
        self.assertFalse(earlier.reward_qualifies)
        self.assertTrue(later.reward_qualifies)
        game.assert_called_once()
        self.assertEqual(game.call_args.args[2], {"savings_goal_id": later.pk})

    def test_legacy_goals_keep_each_frozen_award_and_qualifying_event_in_shared_batch(self):
        legacy = [SavingsGoal.objects.create(user=self.child, title=f"Accepted {target}",
            target_amount=target, reward_policy_version=1, legacy_coin_reward=target * 2, legacy_target_amount=target)
            for target in (30, 50)]
        new = self.create("New seventy-five", "75.00")
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
            self.money("75.00")
        self.assertEqual(self.savings_coins(), 60 + 100 + 50)
        self.assertEqual(game.call_count, 3)
        self.assertEqual(set(SavingsGoal.objects.filter(user=self.child, reward_qualifies=True).values_list(
            "pk", flat=True)), {legacy[0].pk, legacy[1].pk, new.pk})

    def test_high_water_survives_deleted_goals_exchange_and_reearning(self):
        first = self.create("Initial fifty")
        self.money("50.00")
        self.assertEqual(self.savings_coins(), 100)
        self.client.delete(f"/api/savings-goals/{first.pk}/")
        self.money("-50.00", kind="coin_exchange")
        self.create("Rebuilt fifty")
        self.money("50.00")
        self.assertEqual(self.savings_coins(), 100)
        self.create("Genuinely new seventy-five", "75.00")
        self.money("25.00")
        self.assertEqual(self.savings_coins(), 150)

    def test_goal_starting_balance_and_rate_are_frozen_for_new_savings(self):
        self.money("50.00", hooked=False)
        goal = self.create("Reach one hundred", "100.00")
        with override_settings(COINS_PER_SAVINGS_GOAL_DOLLAR=9):
            self.money("50.00")
        self.assertEqual(self.savings_coins(), 100)
        self.assertTrue(SavingsGoal.objects.get(pk=goal.pk).is_completed)

    def test_failed_award_retains_money_but_rolls_back_goal_and_milestone_for_retry(self):
        goal = self.create("Retry safely")
        with patch("apps.rewards.services.CoinService.award_coins", side_effect=RuntimeError("unavailable")):
            self.money("50.00")
        goal.refresh_from_db()
        self.assertFalse(goal.is_completed)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("50.00"))
        self.assertEqual(self.savings_coins(), 0)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges, [])
        SavingsGoalService.check_and_complete(self.child)
        SavingsGoalService.check_and_complete(self.child)
        self.assertEqual(self.savings_coins(), 100)

    def test_game_reward_failure_rolls_back_paid_milestone_for_explicit_retry(self):
        goal = self.create("Strict game-loop retry")
        with patch("apps.rpg.services.GameLoopService.on_task_completed", side_effect=RuntimeError("game failed")):
            self.money("50.00")
        goal.refresh_from_db()
        self.assertFalse(goal.is_completed or goal.reward_qualifies)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_balance, Decimal("0.00"))
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_ranges, [])
        self.assertEqual(self.savings_coins(), 0)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("50.00"))
        SavingsGoalService.update_goal(goal, title="Retried by explicit edit")
        goal.refresh_from_db()
        self.assertEqual(goal.reward_start_balance, Decimal("0.00"))
        self.assertTrue(goal.reward_qualifies)
        self.assertEqual(self.savings_coins(), 100)

    def test_failed_settlement_discards_external_pushes_from_partial_game_rewards(self):
        self.create("No premature push")

        def incomplete_game_reward(*args, **kwargs):
            from apps.notifications.services import notify
            notify(self.child, "Transient reward")
            raise RuntimeError("later game step failed")

        with patch("apps.rpg.services.GameLoopService.on_task_completed", side_effect=incomplete_game_reward), patch(
            "apps.notifications.services._push_now",
        ) as push:
            with self.captureOnCommitCallbacks(execute=True):
                self.money("50.00")
        push.assert_not_called()
        self.assertEqual(self.savings_coins(), 0)

    def test_nonpositive_new_targets_are_rejected_before_any_reward_state(self):
        for target in ("0.00", "-1.00"):
            with self.subTest(target=target):
                response = self.client.post("/api/savings-goals/", {"title": "Invalid", "target_amount": target})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(SavingsGoal.objects.filter(user=self.child).exists())
        self.assertFalse(SavingsRewardProgress.objects.filter(user=self.child).exists())

    def test_funded_goals_do_not_unlock_badges_during_a_later_evaluation(self):
        self.money("50.00", hooked=False)
        self.create("No new saving")
        badge = Badge.objects.create(name="Actual new saving", criteria_type="savings_goal_completed",
            criteria_value={"count": 1}, rarity="common")
        self.assertFalse(_savings_goal_completed(self.child, {"count": 1}))
        BadgeService.evaluate_badges(self.child, scopes={"savings", "badges"})
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())

    def test_foreign_family_cannot_edit_or_complete_another_goal(self):
        goal = self.create("Our pending target")
        other = make_family("Other savings", parents=[{"username": "other-saving-parent"}],
            children=[{"username": "other-saving-child"}])
        self.client.force_authenticate(other.children[0])
        response = self.client.patch(f"/api/savings-goals/{goal.pk}/", {"target_amount": "1.00"})
        self.assertEqual(response.status_code, 404)
        with override_user(other.parents[0]), self.assertRaises(MCPNotFoundError):
            update_savings_goal(UpdateSavingsGoalIn(goal_id=goal.pk, target_amount=Decimal("1.00")))
        goal.refresh_from_db()
        self.assertEqual(goal.target_amount, Decimal("50.00"))

    def test_explicit_target_update_completes_without_needing_a_read(self):
        goal = self.create("Larger target", "100.00")
        self.money("50.00", hooked=False)
        response = self.client.patch(f"/api/savings-goals/{goal.pk}/", {"target_amount": "50.00"})
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertTrue(goal.is_completed)
        self.assertFalse(goal.reward_qualifies)
        self.assertEqual(self.savings_coins(), 0)

    def test_mcp_explicit_update_settles_eligible_goal(self):
        goal = self.create("MCP update", "100.00")
        self.money("50.00", hooked=False)
        with override_user(self.family.parents[0]):
            result = update_savings_goal(UpdateSavingsGoalIn(goal_id=goal.pk, target_amount=Decimal("50.00")))
        self.assertTrue(result["is_completed"])
        self.assertEqual(self.savings_coins(), 0)

    def test_lowering_precreated_targets_cannot_split_existing_money_into_reward_events(self):
        goals = [self.create(f"Future target {number}", "100.00") for number in range(3)]
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
            self.money("50.00")
            for number, goal in enumerate(goals, start=1):
                response = self.client.patch(f"/api/savings-goals/{goal.pk}/", {
                    "target_amount": str(Decimal(number) / 100)})
                self.assertEqual(response.status_code, 200)
        self.assertEqual(SavingsGoal.objects.filter(user=self.child, is_completed=True).count(), 3)
        self.assertFalse(SavingsGoal.objects.filter(user=self.child, reward_qualifies=True).exists())
        game.assert_not_called()
        self.assertEqual(self.savings_coins(), 0)
        self.assertFalse(_savings_goal_completed(self.child, {"count": 1}))

    def test_increasing_target_only_rewards_savings_after_the_explicit_change(self):
        goal = self.create("Original fifty")
        self.money("25.00")
        response = self.client.patch(f"/api/savings-goals/{goal.pk}/", {"target_amount": "75.00"})
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.reward_start_balance, Decimal("25.00"))
        self.money("50.00")
        self.assertEqual(self.savings_coins(), 100)

    def test_same_target_and_metadata_edits_preserve_the_original_savings_baseline(self):
        goal = self.create("Frozen baseline")
        self.money("50.00", hooked=False)
        response = self.client.patch(f"/api/savings-goals/{goal.pk}/", {
            "target_amount": "50.00", "title": "Same target, renamed", "icon": "star"})
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.reward_start_balance, Decimal("0.00"))
        self.assertTrue(goal.is_completed and goal.reward_qualifies)
        self.assertEqual(self.savings_coins(), 100)

    def test_internal_reward_fields_cannot_be_supplied_by_clients(self):
        self.money("50.00", hooked=False)
        response = self.client.post("/api/savings-goals/", {"title": "Forged reward", "target_amount": "50.00",
            "reward_policy_version": 1, "legacy_coin_reward": 9999,
            "reward_start_balance": "0.00", "reward_qualifies": True}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.savings_coins(), 0)
        goal = SavingsGoal.objects.get(pk=response.data["id"])
        self.assertEqual(goal.reward_policy_version, 2)
        self.assertFalse(goal.reward_qualifies)

    def test_migration_preserves_fixed_legacy_promises_and_existing_balances(self):
        old = SavingsGoal.objects.create(user=self.child, title="Already accepted", target_amount=50,
            reward_policy_version=1)
        self.money("10.00", hooked=False)
        CoinLedger.objects.create(user=self.child, amount=700, reason="adjustment", description="Synthetic existing balance")
        migration = import_module("apps.projects.migrations.0025_savings_reward_milestones")
        migration.freeze_existing_savings(apps, None)
        old.refresh_from_db()
        self.assertEqual(old.legacy_coin_reward, 100)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_balance, Decimal("10.00"))
        with override_settings(COINS_PER_SAVINGS_GOAL_DOLLAR=9):
            migration.freeze_existing_savings(apps, None)
            response = self.client.patch(f"/api/savings-goals/{old.pk}/", {"target_amount": "40.00"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.savings_coins(), 0)
            old.refresh_from_db()
            self.assertEqual(old.target_amount, Decimal("50.00"))
            self.money("40.00")
        self.assertEqual(self.savings_coins(), 100)
        old.refresh_from_db()
        self.assertTrue(old.is_completed and old.reward_qualifies)
        self.assertEqual(old.legacy_coin_reward, 100)
        self.assertEqual(old.legacy_target_amount, Decimal("50.00"))
        self.assertEqual(old.reward_start_balance, Decimal("0.00"))
        SavingsGoalService.check_and_complete(self.child)
        self.assertEqual(self.savings_coins(), 100)

    def test_legacy_thousand_dollar_target_cannot_be_lowered_to_mint_its_frozen_promise(self):
        old = SavingsGoal.objects.create(user=self.child, title="Accepted thousand", target_amount=1000,
            reward_policy_version=1)
        self.money("10.00", hooked=False)
        import_module("apps.projects.migrations.0025_savings_reward_milestones").freeze_existing_savings(apps, None)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
            response = self.client.patch(f"/api/savings-goals/{old.pk}/", {
                "target_amount": "1.00", "title": "Changed in same rejected write"})
        self.assertEqual(response.status_code, 400, {"response": response.data, "savings_coins": self.savings_coins()})
        self.assertIn("target_amount", response.data)
        old.refresh_from_db()
        self.assertEqual(old.title, "Accepted thousand")
        self.assertEqual(old.target_amount, Decimal("1000.00"))
        self.assertFalse(old.is_completed)
        self.assertEqual(self.savings_coins(), 0)
        game.assert_not_called()

    def test_mcp_legacy_target_reduction_returns_domain_validation_without_awards(self):
        old = SavingsGoal.objects.create(user=self.child, title="Accepted MCP target", target_amount=1000,
            reward_policy_version=1)
        self.money("10.00", hooked=False)
        import_module("apps.projects.migrations.0025_savings_reward_milestones").freeze_existing_savings(apps, None)
        with override_user(self.family.parents[0]), self.assertRaises(MCPValidationError) as error:
            update_savings_goal(UpdateSavingsGoalIn(goal_id=old.pk, target_amount=Decimal("1.00")))
        self.assertEqual(error.exception.code, "invalid_request")
        self.assertIn("target_amount", error.exception.field_errors)
        old.refresh_from_db()
        self.assertEqual(old.target_amount, Decimal("1000.00"))
        self.assertFalse(old.is_completed)
        self.assertEqual(self.savings_coins(), 0)

    def test_legacy_metadata_same_and_higher_targets_keep_original_accepted_promise(self):
        old = SavingsGoal.objects.create(user=self.child, title="Accepted fifty", target_amount=50,
            reward_policy_version=1)
        self.money("10.00", hooked=False)
        import_module("apps.projects.migrations.0025_savings_reward_milestones").freeze_existing_savings(apps, None)
        same = self.client.patch(f"/api/savings-goals/{old.pk}/", {
            "target_amount": "50.00", "title": "Renamed legacy", "icon": "star"})
        self.assertEqual(same.status_code, 200, same.data)
        raised = self.client.patch(f"/api/savings-goals/{old.pk}/", {"target_amount": "75.00"})
        self.assertEqual(raised.status_code, 200, raised.data)
        self.money("40.00")
        old.refresh_from_db()
        self.assertFalse(old.is_completed)
        self.assertEqual(old.legacy_coin_reward, 100)
        self.assertEqual(old.legacy_target_amount, Decimal("50.00"))
        self.assertEqual(old.title, "Renamed legacy")
        self.assertEqual(old.icon, "star")
        self.money("25.00")
        self.assertEqual(self.savings_coins(), 100)
        old.refresh_from_db()
        self.assertTrue(old.is_completed and old.reward_qualifies)
        self.assertEqual(old.legacy_target_amount, Decimal("50.00"))
        self.assertEqual(old.legacy_coin_reward, 100)
        self.assertEqual(old.reward_start_balance, Decimal("0.00"))
        SavingsGoalService.check_and_complete(self.child)
        self.assertEqual(self.savings_coins(), 100)

    def test_migration_keeps_completed_legacy_history_without_replaying_awards(self):
        old = SavingsGoal.objects.create(user=self.child, title="Historical", target_amount=100,
            reward_policy_version=1, is_completed=True)
        migration = import_module("apps.projects.migrations.0025_savings_reward_milestones")
        migration.freeze_existing_savings(apps, None)
        old.refresh_from_db()
        self.assertTrue(old.is_completed and old.reward_qualifies)
        self.assertEqual(old.legacy_target_amount, Decimal("100.00"))
        self.assertEqual(SavingsRewardProgress.objects.get(user=self.child).recognized_balance, Decimal("100.00"))
        self.assertEqual(self.savings_coins(), 0)
        self.assertTrue(_savings_goal_completed(self.child, {"count": 1}))
