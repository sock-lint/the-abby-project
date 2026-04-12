from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.db import transaction
from django.utils import timezone

from config.services import BaseLedgerService

from .models import CoinLedger, ExchangeRequest, Reward, RewardRedemption


class InsufficientCoinsError(Exception):
    pass


class InsufficientFundsError(Exception):
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


class ExchangeService:
    """Handles money → coins exchange requests and parent approval."""

    @staticmethod
    @transaction.atomic
    def request_exchange(user, dollar_amount):
        from apps.payments.services import PaymentService

        try:
            dollar_amount = Decimal(str(dollar_amount))
        except (InvalidOperation, TypeError):
            raise ValueError("Invalid dollar amount.")

        if dollar_amount < Decimal("1.00"):
            raise ValueError("Minimum exchange is $1.00.")

        balance = PaymentService.get_balance(user)
        if balance < dollar_amount:
            raise InsufficientFundsError(
                f"Need ${dollar_amount}, have ${balance}."
            )

        rate = django_settings.COINS_PER_DOLLAR
        coin_amount = int(dollar_amount * rate)

        exchange = ExchangeRequest.objects.create(
            user=user,
            dollar_amount=dollar_amount,
            coin_amount=coin_amount,
            exchange_rate=rate,
        )

        from apps.projects.models import Notification, User
        display = getattr(user, "display_name", None) or user.username
        for parent in User.objects.filter(role="parent"):
            Notification.objects.create(
                user=parent,
                title=f"Exchange request: ${dollar_amount}",
                message=(
                    f"{display} wants to exchange ${dollar_amount} "
                    f"for {coin_amount} coins."
                ),
                notification_type=Notification.NotificationType.EXCHANGE_REQUESTED,
            )

        return exchange

    @staticmethod
    @transaction.atomic
    def approve(exchange, parent, notes=""):
        if exchange.status != ExchangeRequest.Status.PENDING:
            return exchange

        from apps.payments.models import PaymentLedger
        from apps.payments.services import PaymentService

        user = exchange.user
        dollar_amount = exchange.dollar_amount
        coin_amount = exchange.coin_amount

        balance = PaymentService.get_balance(user)
        if balance < dollar_amount:
            raise InsufficientFundsError(
                f"Insufficient balance: need ${dollar_amount}, have ${balance}."
            )

        PaymentService.record_entry(
            user,
            -dollar_amount,
            PaymentLedger.EntryType.COIN_EXCHANGE,
            description=f"Coin exchange: ${dollar_amount} → {coin_amount} coins",
            created_by=parent,
        )

        CoinService.award_coins(
            user,
            coin_amount,
            CoinLedger.Reason.EXCHANGE,
            description=f"Exchange: ${dollar_amount} → {coin_amount} coins",
            created_by=parent,
        )

        exchange.status = ExchangeRequest.Status.APPROVED
        exchange.decided_at = timezone.now()
        exchange.decided_by = parent
        if notes:
            exchange.parent_notes = notes
        exchange.save(update_fields=[
            "status", "decided_at", "decided_by", "parent_notes",
        ])

        from apps.projects.models import Notification
        Notification.objects.create(
            user=user,
            title="Exchange approved!",
            message=(
                f"Your exchange of ${dollar_amount} for "
                f"{coin_amount} coins was approved."
            ),
            notification_type=Notification.NotificationType.EXCHANGE_APPROVED,
        )

        return exchange

    @staticmethod
    @transaction.atomic
    def deny(exchange, parent, notes=""):
        if exchange.status != ExchangeRequest.Status.PENDING:
            return exchange

        exchange.status = ExchangeRequest.Status.DENIED
        exchange.decided_at = timezone.now()
        exchange.decided_by = parent
        if notes:
            exchange.parent_notes = notes
        exchange.save(update_fields=[
            "status", "decided_at", "decided_by", "parent_notes",
        ])

        from apps.projects.models import Notification
        msg = f"Your exchange of ${exchange.dollar_amount} was denied."
        if notes:
            msg += f" Note: {notes}"
        Notification.objects.create(
            user=exchange.user,
            title="Exchange denied",
            message=msg,
            notification_type=Notification.NotificationType.EXCHANGE_DENIED,
        )

        return exchange
