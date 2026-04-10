from django.db import transaction
from django.utils import timezone

from config.services import BaseLedgerService

from .models import CoinLedger, Reward, RewardRedemption


class InsufficientCoinsError(Exception):
    pass


class RewardUnavailableError(Exception):
    pass


class CoinService(BaseLedgerService):
    ledger_model = CoinLedger
    category_field = "reason"
    default_value = 0

    @staticmethod
    def award_coins(user, amount, reason, *, description="", created_by=None, redemption=None):
        if amount == 0:
            return None
        return CoinLedger.objects.create(
            user=user,
            amount=int(amount),
            reason=reason,
            description=description,
            created_by=created_by,
            redemption=redemption,
        )

    @staticmethod
    def spend_coins(user, amount, reason, *, description="", redemption=None):
        if amount <= 0:
            return None
        balance = CoinService.get_balance(user)
        if balance < amount:
            raise InsufficientCoinsError(
                f"Need {amount} coins, have {balance}."
            )
        return CoinLedger.objects.create(
            user=user,
            amount=-int(amount),
            reason=reason,
            description=description,
            redemption=redemption,
        )


class RewardService:
    @staticmethod
    @transaction.atomic
    def request_redemption(user, reward):
        if not reward.is_active:
            raise RewardUnavailableError("Reward is not active.")
        if reward.stock is not None and reward.stock <= 0:
            raise RewardUnavailableError("Reward is out of stock.")

        balance = CoinService.get_balance(user)
        if balance < reward.cost_coins:
            raise InsufficientCoinsError(
                f"Need {reward.cost_coins} coins, have {balance}."
            )

        redemption = RewardRedemption.objects.create(
            user=user,
            reward=reward,
            coin_cost_snapshot=reward.cost_coins,
            status=(
                RewardRedemption.Status.PENDING
                if reward.requires_parent_approval
                else RewardRedemption.Status.APPROVED
            ),
        )
        # Hold coins immediately so balance reflects intent.
        CoinService.spend_coins(
            user,
            reward.cost_coins,
            CoinLedger.Reason.REDEMPTION,
            description=f"Held for redemption: {reward.name}",
            redemption=redemption,
        )
        if reward.stock is not None:
            Reward.objects.filter(pk=reward.pk).update(stock=reward.stock - 1)

        if not reward.requires_parent_approval:
            redemption.status = RewardRedemption.Status.FULFILLED
            redemption.decided_at = timezone.now()
            redemption.save(update_fields=["status", "decided_at"])
        else:
            # Notify every parent so the bell lights up without them having
            # to visit /rewards.
            from apps.projects.models import Notification, User
            display = getattr(user, "display_name", None) or user.username
            for parent in User.objects.filter(role="parent"):
                Notification.objects.create(
                    user=parent,
                    title=f"Reward request: {reward.name}",
                    message=f"{display} wants to redeem {reward.name} for {reward.cost_coins} coins.",
                    notification_type=Notification.NotificationType.REDEMPTION_REQUESTED,
                )
        return redemption

    @staticmethod
    def _finalize_decision(redemption, new_status, parent, notes):
        redemption.status = new_status
        redemption.decided_at = timezone.now()
        redemption.decided_by = parent
        if notes:
            redemption.parent_notes = notes
        redemption.save(update_fields=["status", "decided_at", "decided_by", "parent_notes"])

    @staticmethod
    @transaction.atomic
    def approve(redemption, parent, notes=""):
        if redemption.status != RewardRedemption.Status.PENDING:
            return redemption
        RewardService._finalize_decision(
            redemption, RewardRedemption.Status.FULFILLED, parent, notes,
        )
        return redemption

    @staticmethod
    @transaction.atomic
    def deny(redemption, parent, notes=""):
        if redemption.status != RewardRedemption.Status.PENDING:
            return redemption
        # Refund held coins
        CoinService.award_coins(
            redemption.user,
            redemption.coin_cost_snapshot,
            CoinLedger.Reason.REFUND,
            description=f"Refund (denied): {redemption.reward.name}",
            created_by=parent,
            redemption=redemption,
        )
        # Restore stock if tracked
        reward = redemption.reward
        if reward.stock is not None:
            Reward.objects.filter(pk=reward.pk).update(stock=reward.stock + 1)
        RewardService._finalize_decision(
            redemption, RewardRedemption.Status.DENIED, parent, notes,
        )
        return redemption
