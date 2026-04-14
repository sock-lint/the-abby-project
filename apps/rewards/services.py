import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.db import transaction

from apps.projects.notifications import get_display_name, notify, notify_parents
from config.services import BaseLedgerService, finalize_decision

from .models import CoinLedger, ExchangeRequest, Reward, RewardRedemption

logger = logging.getLogger(__name__)


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
            # Auto-fulfill: no parent decision, so decided_by stays null.
            finalize_decision(redemption, RewardRedemption.Status.FULFILLED, None)
        else:
            from apps.projects.models import Notification
            display = get_display_name(user)
            notify_parents(
                title=f"Reward request: {reward.name}",
                message=f"{display} wants to redeem {reward.name} for {reward.cost_coins} coins.",
                notification_type=Notification.NotificationType.REDEMPTION_REQUESTED,
                link="/rewards",
            )
        return redemption

    @staticmethod
    @transaction.atomic
    def approve(redemption, parent, notes=""):
        if redemption.status != RewardRedemption.Status.PENDING:
            return redemption
        finalize_decision(redemption, RewardRedemption.Status.FULFILLED, parent, notes)
        return redemption

    @staticmethod
    @transaction.atomic
    def reject(redemption, parent, notes=""):
        """Refund held coins, restore stock, and stamp the redemption as denied.

        The persisted status stays ``DENIED`` (DB enum value, notification type,
        and the frontend status-pill color are all keyed to ``"denied"``);
        only the callable/route name is normalized to ``reject`` to match
        chores/homework.
        """
        if redemption.status != RewardRedemption.Status.PENDING:
            return redemption
        CoinService.award_coins(
            redemption.user,
            redemption.coin_cost_snapshot,
            CoinLedger.Reason.REFUND,
            description=f"Refund (denied): {redemption.reward.name}",
            created_by=parent,
            redemption=redemption,
        )
        reward = redemption.reward
        if reward.stock is not None:
            Reward.objects.filter(pk=reward.pk).update(stock=reward.stock + 1)
        finalize_decision(redemption, RewardRedemption.Status.DENIED, parent, notes)
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

        from apps.projects.models import Notification
        display = get_display_name(user)
        notify_parents(
            title=f"Exchange request: ${dollar_amount}",
            message=f"{display} wants to exchange ${dollar_amount} for {coin_amount} coins.",
            notification_type=Notification.NotificationType.EXCHANGE_REQUESTED,
            link="/rewards",
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

        finalize_decision(exchange, ExchangeRequest.Status.APPROVED, parent, notes)
        logger.info("Exchange approved: user=%s $%s -> %d coins", user, dollar_amount, coin_amount)

        from apps.projects.models import Notification
        notify(
            user,
            title="Exchange approved!",
            message=f"Your exchange of ${dollar_amount} for {coin_amount} coins was approved.",
            notification_type=Notification.NotificationType.EXCHANGE_APPROVED,
            link="/rewards",
        )

        return exchange

    @staticmethod
    @transaction.atomic
    def reject(exchange, parent, notes=""):
        """Mark an exchange request as denied. No ledger side-effects (money
        is verified at approve-time, not held at request-time).

        Persisted status stays ``DENIED`` for backward compatibility; only
        the method/route name is normalized to match chores/homework.
        """
        if exchange.status != ExchangeRequest.Status.PENDING:
            return exchange

        finalize_decision(exchange, ExchangeRequest.Status.DENIED, parent, notes)

        from apps.projects.models import Notification
        msg = f"Your exchange of ${exchange.dollar_amount} was denied."
        if notes:
            msg += f" Note: {notes}"
        notify(
            exchange.user,
            title="Exchange denied",
            message=msg,
            notification_type=Notification.NotificationType.EXCHANGE_DENIED,
            link="/rewards",
        )

        return exchange
