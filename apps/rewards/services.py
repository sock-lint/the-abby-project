import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.db import transaction

from apps.notifications.models import NotificationType
from apps.notifications.services import get_display_name, notify, notify_parents
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
        # Apply Lucky Coin boost to earn-kind positive awards only. Skips
        # ADJUSTMENT (check-in/salvage/parent-manual — mixed signs), REFUND
        # (restores cost), REDEMPTION (spend), and EXCHANGE (has its own
        # 1:1 rate). See is_boostable_coin_reason for the whitelist.
        from apps.rpg.services import coin_boost_multiplier, is_boostable_coin_reason
        boosted_amount = int(amount)
        if amount > 0 and is_boostable_coin_reason(reason):
            multiplier = coin_boost_multiplier(user)
            if multiplier > 1.0:
                boosted_amount = int(amount * multiplier)
                if description:
                    description = f"{description} (Lucky Coin ×{multiplier:g})"
        entry = CoinLedger.objects.create(
            user=user,
            amount=boosted_amount,
            reason=reason,
            description=description,
            created_by=created_by,
            redemption=redemption,
        )
        CoinService._record_activity(entry, created_by=created_by)
        return entry

    @staticmethod
    def spend_coins(user, amount, reason, *, description="", redemption=None):
        if amount <= 0:
            return None
        balance = CoinService.get_balance(user)
        if balance < amount:
            raise InsufficientCoinsError(
                f"Need {amount} coins, have {balance}."
            )
        entry = CoinLedger.objects.create(
            user=user,
            amount=-int(amount),
            reason=reason,
            description=description,
            redemption=redemption,
        )
        CoinService._record_activity(entry, created_by=None)
        return entry

    @staticmethod
    def _record_activity(entry, *, created_by):
        """Emit a ledger.coins.* event unless an outer AwardService scope suppressed it."""
        from apps.activity.services import ActivityLogService, ledger_suppressed

        if ledger_suppressed():
            return

        direction = "+" if entry.amount >= 0 else ""
        summary = (
            entry.description
            or f"Coins {direction}{entry.amount} ({entry.reason})"
        )
        ActivityLogService.record(
            category="ledger",
            event_type=f"ledger.coins.{entry.reason}",
            summary=summary,
            actor=created_by,
            subject=entry.user,
            target=entry,
            coins_delta=int(entry.amount),
            breakdown=[
                {"label": entry.reason, "value": int(entry.amount), "op": "="},
            ],
            extras={"reason": entry.reason, "description": entry.description or ""},
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

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="approval",
            event_type="reward.redeem",
            summary=f"Redemption requested: {reward.name}",
            actor=user,
            subject=user,
            target=redemption,
            coins_delta=-int(reward.cost_coins),
            breakdown=[
                {"label": "cost", "value": int(reward.cost_coins), "op": "="},
                {"label": "reward", "value": reward.name, "op": "note"},
            ],
            extras={
                "reward_id": reward.pk,
                "reward_name": reward.name,
                "cost_coins": int(reward.cost_coins),
            },
        )

        if not reward.requires_parent_approval:
            # Auto-fulfill: no parent decision, so decided_by stays null.
            finalize_decision(
                redemption, RewardRedemption.Status.FULFILLED, None,
                activity_category="approval",
                activity_event_type="reward.approve",
                activity_summary=f"Redemption auto-fulfilled: {reward.name}",
                activity_subject=user,
                activity_extras={"reward_id": reward.pk, "auto": True},
            )
            RewardService._maybe_credit_digital_item(redemption)
        else:
            display = get_display_name(user)
            notify_parents(
                title=f"Reward request: {reward.name}",
                message=f"{display} wants to redeem {reward.name} for {reward.cost_coins} coins.",
                notification_type=NotificationType.REDEMPTION_REQUESTED,
                link="/rewards",
            )
        return redemption

    @staticmethod
    @transaction.atomic
    def approve(redemption, parent, notes=""):
        if redemption.status != RewardRedemption.Status.PENDING:
            return redemption
        finalize_decision(
            redemption, RewardRedemption.Status.FULFILLED, parent, notes,
            activity_category="approval",
            activity_event_type="reward.approve",
            activity_summary=f"Redemption approved: {redemption.reward.name}",
            activity_subject=redemption.user,
            activity_extras={
                "reward_id": redemption.reward_id,
                "coin_cost": int(redemption.coin_cost_snapshot),
            },
        )
        RewardService._maybe_credit_digital_item(redemption)
        return redemption

    @staticmethod
    def _maybe_credit_digital_item(redemption):
        """Credit the linked ItemDefinition to UserInventory when the reward
        is a digital-item fulfillment.

        Idempotent-ish: only fires from ``approve``'s transition into
        ``FULFILLED``, so it never double-credits even if this method is
        called repeatedly. A noop for ``real_world`` rewards or rewards
        without a linked item. Missing FK + non-real_world kind is logged
        but not raised — we don't want a mis-configured reward to block
        an approval the parent already greenlit.
        """
        reward = redemption.reward
        if reward.fulfillment_kind == Reward.FulfillmentKind.REAL_WORLD:
            return
        if reward.item_definition_id is None:
            logger.warning(
                "Reward %s has fulfillment_kind=%s but no item_definition; "
                "skipping inventory credit.",
                reward.pk, reward.fulfillment_kind,
            )
            return
        from apps.rpg.models import UserInventory
        inv, _ = UserInventory.objects.select_for_update().get_or_create(
            user=redemption.user,
            item=reward.item_definition,
            defaults={"quantity": 0},
        )
        inv.quantity = inv.quantity + 1
        inv.save(update_fields=["quantity"])

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
        finalize_decision(
            redemption, RewardRedemption.Status.DENIED, parent, notes,
            activity_category="approval",
            activity_event_type="reward.reject",
            activity_summary=f"Redemption rejected: {reward.name}",
            activity_subject=redemption.user,
            activity_extras={
                "reward_id": reward.pk,
                "refunded_coins": int(redemption.coin_cost_snapshot),
            },
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

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="approval",
            event_type="exchange.request",
            summary=f"Exchange requested: ${dollar_amount} → {coin_amount} coins",
            actor=user,
            subject=user,
            target=exchange,
            breakdown=[
                {"label": "dollars", "value": str(dollar_amount), "op": "×"},
                {"label": "rate", "value": int(rate), "op": "="},
                {"label": "coins", "value": coin_amount, "op": "note"},
            ],
            extras={
                "dollar_amount": str(dollar_amount),
                "coin_amount": coin_amount,
                "exchange_rate": int(rate),
            },
        )

        display = get_display_name(user)
        notify_parents(
            title=f"Exchange request: ${dollar_amount}",
            message=f"{display} wants to exchange ${dollar_amount} for {coin_amount} coins.",
            notification_type=NotificationType.EXCHANGE_REQUESTED,
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

        finalize_decision(
            exchange, ExchangeRequest.Status.APPROVED, parent, notes,
            activity_category="approval",
            activity_event_type="exchange.approve",
            activity_summary=(
                f"Exchange approved: ${dollar_amount} → {coin_amount} coins"
            ),
            activity_subject=user,
            activity_extras={
                "dollar_amount": str(dollar_amount),
                "coin_amount": coin_amount,
                "exchange_rate": int(exchange.exchange_rate),
            },
        )
        logger.info("Exchange approved: user=%s $%s -> %d coins", user, dollar_amount, coin_amount)

        notify(
            user,
            title="Exchange approved!",
            message=f"Your exchange of ${dollar_amount} for {coin_amount} coins was approved.",
            notification_type=NotificationType.EXCHANGE_APPROVED,
            link="/rewards",
        )

        # Chronicle hook — wrapped so a chronicle failure never breaks approval.
        try:
            from apps.chronicle.services import ChronicleService
            ChronicleService.record_first(
                exchange.user,
                event_slug="first_exchange_approved",
                title="First money \u2192 coins exchange",
                icon_slug="coin-stack",
                metadata={
                    "dollar_amount": str(dollar_amount),
                    "coin_amount": coin_amount,
                    "exchange_rate": int(exchange.exchange_rate),
                },
            )
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).exception(
                "Chronicle hook failed in ExchangeService.approve"
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

        finalize_decision(
            exchange, ExchangeRequest.Status.DENIED, parent, notes,
            activity_category="approval",
            activity_event_type="exchange.deny",
            activity_summary=f"Exchange denied: ${exchange.dollar_amount}",
            activity_subject=exchange.user,
            activity_extras={
                "dollar_amount": str(exchange.dollar_amount),
                "coin_amount": exchange.coin_amount,
            },
        )

        msg = f"Your exchange of ${exchange.dollar_amount} was denied."
        if notes:
            msg += f" Note: {notes}"
        notify(
            exchange.user,
            title="Exchange denied",
            message=msg,
            notification_type=NotificationType.EXCHANGE_DENIED,
            link="/rewards",
        )

        return exchange
