"""Explicit savings writes settle once-paid, prospective money milestones.

Money remains liquid. Reads only project saved state. New targets freeze an
admission floor above current money and previously completed milestones.
Durable covered ranges prevent repeat rewards while reserving unpaid gaps
to older unchanged goals. Accepted goals keep their frozen Coin promises.
"""
from decimal import Decimal
import logging

from django.db import transaction
from django.utils import timezone

from apps.notifications.services import defer_push_until_commit

logger = logging.getLogger(__name__)


class SavingsGoalTargetError(ValueError):
    """An accepted savings promise cannot keep its payout at a lower target."""


def _claim_savings_range(covered, start, end):
    """Return uncovered dollars and a canonical union in one linear pass.

    Stored coverage uses integer cents, with touching bands merged. Reject
    malformed coverage rather than treating it as unclaimed money.
    """
    left, right = int(start * 100), int(end * 100)
    if right <= left:
        return Decimal("0"), covered
    if not isinstance(covered, list):
        raise ValueError("The saved savings coverage is invalid.")
    uncovered = right - left
    merged = []
    union_left, union_right = left, right
    inserted = False
    previous_end = None
    for band in covered:
        if (not isinstance(band, list) or len(band) != 2
                or any(type(point) is not int for point in band)):
            raise ValueError("The saved savings coverage is invalid.")
        prior_left, prior_right = band
        if (prior_left < 0 or prior_right <= prior_left
                or (previous_end is not None and prior_left <= previous_end)):
            raise ValueError("The saved savings coverage is invalid.")
        previous_end = prior_right
        uncovered -= max(0, min(right, prior_right) - max(left, prior_left))
        if prior_right < union_left:
            merged.append(band)
        elif union_right < prior_left:
            if not inserted:
                merged.append([union_left, union_right])
                inserted = True
            merged.append(band)
        else:
            union_left = min(union_left, prior_left)
            union_right = max(union_right, prior_right)
    if not inserted:
        merged.append([union_left, union_right])
    return Decimal(uncovered) / 100, merged


class SavingsGoalService:
    @classmethod
    @transaction.atomic
    def create_goal(cls, user, **data):
        from .models import SavingsGoal, User
        User.objects.select_for_update(no_key=True).get(pk=user.pk)
        goal = SavingsGoal.objects.create(user=user, **data)
        cls.check_and_complete(user)
        goal.refresh_from_db()
        return goal

    @classmethod
    @transaction.atomic
    def update_goal(cls, goal, **data):
        from apps.payments.services import PaymentService
        from .models import SavingsGoal, SavingsRewardProgress, User
        User.objects.select_for_update(no_key=True).get(pk=goal.user_id)
        fresh = SavingsGoal.objects.select_for_update().get(pk=goal.pk, user_id=goal.user_id)
        if fresh.reward_policy_version == 1 and "target_amount" in data:
            if fresh.legacy_target_amount is None:
                raise SavingsGoalTargetError("The accepted savings target snapshot is unavailable.")
            if data["target_amount"] < fresh.legacy_target_amount:
                raise SavingsGoalTargetError(
                    f"This accepted goal keeps its original ${fresh.legacy_target_amount:.2f} target. "
                    "Create a new goal for a lower amount.")
        if (fresh.reward_policy_version == 2 and "target_amount" in data
                and data["target_amount"] != fresh.target_amount):
            # A newly chosen target recognizes only future saving. Otherwise
            # pre-created distant goals could be lowered cent by cent to farm
            # milestone events against money that is already available.
            progress = SavingsRewardProgress.objects.select_for_update().get(user_id=fresh.user_id)
            fresh.reward_start_balance = max(fresh.reward_start_balance,
                PaymentService.get_balance(fresh.user), progress.recognized_balance)
        for field in ("title", "target_amount", "icon"):
            if field in data:
                setattr(fresh, field, data[field])
        fresh.save()
        cls.check_and_complete(fresh.user)
        fresh.refresh_from_db()
        return fresh

    @staticmethod
    @transaction.atomic
    def delete_goal(goal):
        from .models import SavingsGoal, User
        # Source-deletion signals also take the user gate. Keep the same lock
        # order as completion, while retaining its independent high-water row.
        User.objects.select_for_update(no_key=True).get(pk=goal.user_id)
        fresh = SavingsGoal.objects.select_for_update().filter(pk=goal.pk, user_id=goal.user_id).first()
        if fresh is not None:
            fresh.delete()

    @classmethod
    @transaction.atomic
    @defer_push_until_commit()
    def check_and_complete(cls, user):
        """Settle eligible goals on a write, holding user then milestone locks.

        Required awards share this transaction with completion and the high-
        water mark. PaymentService catches a failed settlement outside this
        savepoint, retaining the money entry and leaving goals retryable.
        """
        from apps.payments.services import PaymentService
        from .models import SavingsGoal, SavingsRewardProgress, User

        User.objects.select_for_update(no_key=True).get(pk=user.pk)
        balance = max(Decimal("0"), PaymentService.get_balance(user))
        pending = list(SavingsGoal.objects.select_for_update().filter(
            user=user, is_completed=False, target_amount__lte=balance,
        ).order_by("reward_policy_version", "target_amount", "pk"))
        if not pending:
            return []
        progress, _ = SavingsRewardProgress.objects.select_for_update().get_or_create(
            user=user, defaults={"recognized_balance": balance,
                "recognized_ranges": [[0, int(balance * 100)]] if balance > 0 else []})
        settlements = []
        qualifying_new = None
        # Every pending accepted legacy goal keeps its fixed promise for its
        # original $0-target range. Newer identities are not paid for those
        # dollars first, so the outcome cannot depend on how deposits split.
        reserved = progress.recognized_ranges
        for limit in SavingsGoal.objects.filter(user=user, is_completed=False, reward_policy_version=1,
                                               legacy_target_amount__isnull=False).values_list(
                                                   "legacy_target_amount", flat=True):
            reserved = _claim_savings_range(reserved, Decimal("0"), limit)[1]
        for goal in pending:
            legacy = goal.reward_policy_version == 1
            if legacy and (goal.legacy_coin_reward is None or goal.legacy_target_amount is None):
                raise ValueError("The accepted savings reward snapshot is unavailable.")
            if legacy and goal.target_amount < goal.legacy_target_amount:
                raise SavingsGoalTargetError("The goal is below its accepted savings target.")
            start = Decimal("0") if legacy else goal.reward_start_balance
            end = goal.legacy_target_amount if legacy else goal.target_amount
            new_savings, reserved = _claim_savings_range(reserved, start, end)
            _, progress.recognized_ranges = _claim_savings_range(progress.recognized_ranges, start, end)
            coins = goal.legacy_coin_reward if legacy else int(new_savings * goal.reward_rate_snapshot)
            settlements.append((goal, coins))
            if not legacy and new_savings > 0:
                qualifying_new = goal
            # Admission is separate from paid coverage: new identities cannot
            # acquire earlier holes after spending, while unchanged old goals
            # may still recognize those dollars using their frozen floor.
            progress.recognized_balance = max(progress.recognized_balance, goal.target_amount)

        # One balance write can reach many ascending targets. Preserve each
        # increment's frozen Coin rate, but recognize one new financial
        # milestone rather than one reward event per disposable goal identity.
        # Accepted legacy goals retain their individual promised events.
        for goal, _ in settlements:
            goal.reward_qualifies = goal.reward_policy_version == 1 or goal is qualifying_new
            goal.is_completed = True
            goal.completed_at = timezone.now()
            goal.save(update_fields=["is_completed", "completed_at", "reward_qualifies"])
        progress.save(update_fields=["recognized_balance", "recognized_ranges"])
        for goal, coins in settlements:
            cls._fire_completion_pipeline(goal, coins)
            cls._notify_completion(goal, coins)
        return pending

    @staticmethod
    def _fire_completion_pipeline(goal, coins):
        from apps.achievements.services import BadgeService
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService
        from apps.rpg.constants import TriggerType
        from apps.rpg.services import GameLoopService

        if coins > 0:
            CoinService.award_coins(goal.user, coins, CoinLedger.Reason.ADJUSTMENT,
                description=f"Savings goal: {goal.title}")
        if not goal.reward_qualifies:
            return
        BadgeService.evaluate_badges(goal.user, scopes={"savings", "badges"})
        GameLoopService.on_task_completed(goal.user, TriggerType.SAVINGS_GOAL_COMPLETE,
            {"savings_goal_id": goal.pk}, strict=True)

    @staticmethod
    def _notify_completion(goal, coins):
        from apps.notifications.models import NotificationType
        from apps.notifications.services import get_display_name, notify, notify_parents

        try:
            # Notification storage is optional and cannot break settlement.
            with transaction.atomic():
                coins_txt = f" +{coins} coins" if coins > 0 else ""
                notify(goal.user, title="Savings goal reached!",
                    message=f"You reached your goal: {goal.title}.{coins_txt}",
                    notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
                    link=("/treasury?tab=hoards&space=personal" if goal.user.role == "parent"
                          else "/treasury?tab=hoards"))
                notify_parents(title=f"{get_display_name(goal.user)} completed a savings goal",
                    message=f"{goal.title} (${goal.target_amount})",
                    notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
                    link=f"/family?child={goal.user_id}" if goal.user.role == "child" else "/family",
                    about_user=goal.user)
        except Exception:
            logger.exception("Savings goal %s: notification failed", goal.pk)
