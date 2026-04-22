"""Savings-goal completion service.

A savings goal is an aspirational balance tracker — the child's money
stays fully liquid and ``current_amount`` is *computed* from
``PaymentService.get_balance(user)`` rather than stored. This service
answers the one question that can't be derived: "has the child crossed
any goal's target?" and runs the completion pipeline when they have.

Completion is one-shot: once ``is_completed`` flips to True, it stays
True forever even if the child later spends below ``target_amount``.

Completion pipeline (per newly-completed goal):
    1. Mark the goal completed (``is_completed=True``, ``completed_at=now``).
    2. Award coins scaled by target amount
       (``target_amount * settings.COINS_PER_SAVINGS_GOAL_DOLLAR``).
    3. Evaluate badges (the ``savings_goal_completed`` criterion already
       exists in ``apps/achievements/criteria.py``).
    4. Notify the child + all parents.

Invoked from two places:
    * ``PaymentService.record_entry`` — after a ledger row is written,
      so a balance-increasing entry (chore reward, project bonus, etc.)
      immediately triggers completion.
    * ``SavingsGoalSerializer.to_representation`` — a lazy check on read,
      so edits that lower a goal's target below the current balance also
      auto-complete on next fetch.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import List

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class SavingsGoalService:

    @classmethod
    def check_and_complete(cls, user) -> List:
        """Auto-complete any goals whose targets the user's balance crosses.

        Returns the list of goals newly completed by this call.
        """
        from apps.payments.services import PaymentService
        from .models import SavingsGoal

        balance = PaymentService.get_balance(user) or Decimal("0")
        if balance <= 0:
            return []

        pending = list(
            SavingsGoal.objects.filter(user=user, is_completed=False)
        )
        newly_completed = []
        for goal in pending:
            if balance >= goal.target_amount:
                cls._complete_one(goal)
                newly_completed.append(goal)
        return newly_completed

    @classmethod
    @transaction.atomic
    def _complete_one(cls, goal) -> None:
        """Mark one goal completed and fire the reward pipeline.

        Idempotent: refreshes from DB and exits early if the goal was
        already completed by a concurrent call.
        """
        # Re-read inside the transaction so concurrent completions from
        # overlapping ledger writes can't double-award.
        fresh = goal.__class__.objects.select_for_update().get(pk=goal.pk)
        if fresh.is_completed:
            return

        fresh.is_completed = True
        fresh.completed_at = timezone.now()
        fresh.save(update_fields=["is_completed", "completed_at"])

        # Mirror the in-memory goal so the caller sees updated fields.
        goal.is_completed = True
        goal.completed_at = fresh.completed_at

        cls._fire_completion_pipeline(fresh)

    @staticmethod
    def _fire_completion_pipeline(goal) -> None:
        """Award coins, evaluate badges, send notifications.

        Failures here are logged but never re-raised — the goal is
        already marked completed and we don't want a badge/notification
        failure to roll back that state.
        """
        from apps.achievements.services import BadgeService
        from apps.notifications.models import NotificationType
        from apps.notifications.services import (
            get_display_name, notify, notify_parents,
        )
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService

        user = goal.user

        # 1. Coin bonus
        try:
            rate = getattr(settings, "COINS_PER_SAVINGS_GOAL_DOLLAR", 2)
            coins = int(goal.target_amount * rate)
            if coins > 0:
                CoinService.award_coins(
                    user,
                    coins,
                    CoinLedger.Reason.ADJUSTMENT,
                    description=f"Savings goal: {goal.title}",
                )
        except Exception:
            logger.exception(
                "Savings goal %s: coin bonus failed", goal.pk,
            )

        # 2. Badge evaluation
        try:
            BadgeService.evaluate_badges(user)
        except Exception:
            logger.exception(
                "Savings goal %s: badge evaluation failed", goal.pk,
            )

        # 3. Notifications
        try:
            coins_txt = (
                f" +{coins} coins" if coins > 0 else ""
            )
            notify(
                user,
                title="Hoard complete!",
                message=f"You reached your goal: {goal.title}.{coins_txt}",
                notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
                link="/treasury?tab=hoards",
            )
            notify_parents(
                title=f"{get_display_name(user)} completed a savings goal",
                message=f"{goal.title} (${goal.target_amount})",
                notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
            )
        except Exception:
            logger.exception(
                "Savings goal %s: notification failed", goal.pk,
            )
