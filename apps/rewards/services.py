import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
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


def _lock_decision(instance):
    """Refresh a caller's possibly stale decision while holding its row lock.

    Call inside an atomic block. Keep the supplied instance current because
    the shared approval views serialize it after the service returns.
    """
    type(instance).objects.select_for_update().get(pk=instance.pk)
    instance.refresh_from_db()


class CoinService(BaseLedgerService):
    ledger_model = CoinLedger
    category_field = "reason"
    default_value = 0

    @staticmethod
    def award_coins(user, amount, reason, *, description="", created_by=None, redemption=None, source=""):
        # Internal attribution describes the actual award without changing its
        # reason, multiplier or amount. Never infer older sources from text.
        if source not in CoinLedger.Source.values:
            raise ValueError("Unknown Coin award source.")
        source_reasons = {
            CoinLedger.Source.EXPEDITION: CoinLedger.Reason.EXPEDITION,
            CoinLedger.Source.EXPEDITION_SALVAGE: CoinLedger.Reason.ADJUSTMENT,
            CoinLedger.Source.COIN_POUCH: CoinLedger.Reason.ADJUSTMENT,
        }
        if source and (amount <= 0 or reason != source_reasons[source]):
            raise ValueError("Coin award source requires a positive award with its matching reason.")
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
            source=source,
            description=description,
            created_by=created_by,
            redemption=redemption,
        )
        CoinService._record_activity(entry, created_by=created_by)
        return entry

    @staticmethod
    @transaction.atomic
    def spend_coins(user, amount, reason, *, description="", redemption=None):
        if amount <= 0:
            return None
        # Every purchase shares this wallet lock, including print exchanges
        # and shop redemptions. Atomic alone cannot serialize a SUM + INSERT
        # on different purchases. NO KEY UPDATE allows concurrent earn-side
        # ledger inserts while serializing all spends for this user.
        User.objects.select_for_update(no_key=True).get(pk=user.pk)
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
        from .availability import reward_is_available

        # Wallet/decision paths share this lock order: child, then offer (or
        # child, redemption, offer). Metadata edits need only the offer lock.
        user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
        # Callers may hold an offer fetched before another child bought its
        # final item, or before a parent edited it. Serialize reservations on
        # the authoritative row before checking eligibility, price and stock.
        reward = Reward.objects.select_for_update(no_key=True).get(pk=reward.pk)
        if reward.family_id != user.family_id:
            raise RewardUnavailableError("This reward is not currently available.")
        if not reward_is_available(reward):
            raise RewardUnavailableError("This reward is not currently available.")
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
            fulfillment_kind_snapshot=reward.fulfillment_kind,
            item_definition_snapshot_id=(
                reward.item_definition_id
                if reward.fulfillment_kind != Reward.FulfillmentKind.REAL_WORLD
                else None
            ),
            stock_reserved=reward.stock is not None,
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
            Reward.objects.filter(pk=reward.pk).update(stock=F("stock") - 1)
            # Low-stock signal — fire once when stock crosses into the
            # 0/1 zone so parents can restock or retire the prize before
            # an awkward "out of stock" conversation. We refresh from DB
            # because F() doesn't touch the in-memory instance.
            try:
                reward.refresh_from_db(fields=["stock"])
                if reward.stock is not None and reward.stock in (0, 1):
                    notify_parents(
                        title=(
                            f"Reward low: {reward.name} ({reward.stock} left)"
                            if reward.stock == 1
                            else f"Reward sold out: {reward.name}"
                        ),
                        message=(
                            "Restock or retire it on the Manage page so the "
                            "shop stays fresh."
                        ),
                        notification_type=NotificationType.LOW_REWARD_STOCK,
                        link="/manage",
                        about_user=user,
                    )
            except Exception:
                logger.exception("Low-stock notification failed for reward %s", reward.pk)

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
            # Digital delivery is immediate. A real-world promise still needs
            # a parent's separate handover receipt, even without pre-approval.
            finalize_decision(
                redemption, RewardService._approved_status(redemption), None,
                activity_category="approval",
                activity_event_type="reward.approve",
                activity_summary=f"Redemption automatically approved: {reward.name}",
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
                about_user=user,
            )
        return redemption

    @staticmethod
    def _approved_status(redemption):
        return (
            RewardRedemption.Status.FULFILLED
            if redemption.fulfillment_kind_snapshot == Reward.FulfillmentKind.DIGITAL_ITEM
            else RewardRedemption.Status.APPROVED
        )

    @staticmethod
    @transaction.atomic
    def approve(redemption, parent, notes=""):
        User.objects.select_for_update(no_key=True).get(pk=redemption.user_id)
        _lock_decision(redemption)
        if redemption.status != RewardRedemption.Status.PENDING:
            return redemption
        finalize_decision(
            redemption, RewardService._approved_status(redemption), parent, notes,
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
    @transaction.atomic
    def deliver(redemption, parent):
        """Confirm real-world handover once without repeating a saved payment.

        Approval owns digital delivery, the Coin debit, and the saved promise.
        This transition owns only its own audit receipt; past fulfilled rows
        stay untouched rather than acquiring an invented handover date.
        """
        from django.utils import timezone
        from apps.activity.services import ActivityLogService

        child = User.objects.select_for_update(no_key=True).get(pk=redemption.user_id)
        if (
            getattr(parent, "role", None) != "parent"
            or not parent.family_id
            or parent.family_id != child.family_id
        ):
            raise PermissionDenied("Only a parent in this family can confirm delivery.")
        _lock_decision(redemption)
        if redemption.user_id != child.pk:
            raise PermissionDenied("This request changed. Refresh it before confirming delivery.")
        if redemption.status == RewardRedemption.Status.FULFILLED:
            return redemption
        if (
            redemption.status != RewardRedemption.Status.APPROVED
            or redemption.fulfillment_kind_snapshot not in (
                Reward.FulfillmentKind.REAL_WORLD, Reward.FulfillmentKind.BOTH,
            )
        ):
            raise RewardUnavailableError("Approve this real-world reward before confirming delivery.")
        redemption.status = RewardRedemption.Status.FULFILLED
        redemption.delivered_at = timezone.now()
        redemption.delivered_by = parent
        redemption.save(update_fields=["status", "delivered_at", "delivered_by"])
        ActivityLogService.record(
            category="approval", event_type="reward.deliver",
            summary=f"Reward delivered: {redemption.reward.name}",
            actor=parent, subject=child, target=redemption,
            extras={"reward_id": redemption.reward_id, "status": redemption.status},
        )
        return redemption

    @staticmethod
    def _maybe_credit_digital_item(redemption):
        """Credit the requested ItemDefinition, independently of offer edits.

        Called once within the locked approval transition (or
        the initial auto-approval transaction). A noop for ``real_world``
        rewards. An earlier misconfigured digital promise with no recoverable
        item remains pending for correction or denial; it cannot be silently
        fulfilled without delivering the promised inventory.
        """
        if redemption.fulfillment_kind_snapshot == Reward.FulfillmentKind.REAL_WORLD:
            return
        if redemption.item_definition_snapshot_id is None:
            raise RewardUnavailableError(
                "The saved digital reward has no inventory item. Deny it to refund the held coins."
            )
        from apps.rpg.models import UserInventory
        # ``select_for_update`` already locks the row, but pairing with
        # ``F("quantity") + 1`` makes the increment correct under any
        # locking regime — no read-modify-write window the lock has to
        # cover. Refresh after to keep the in-memory object consistent
        # in case the caller inspects it.
        inv, _ = UserInventory.objects.select_for_update().get_or_create(
            user=redemption.user,
            item_id=redemption.item_definition_snapshot_id,
            defaults={"quantity": 0},
        )
        UserInventory.objects.filter(pk=inv.pk).update(
            quantity=F("quantity") + 1,
        )
        inv.refresh_from_db(fields=["quantity"])

    @staticmethod
    @transaction.atomic
    def reject(redemption, parent, notes=""):
        """Refund held coins, restore stock, and stamp the redemption as denied.

        The persisted status stays ``DENIED`` (DB enum value, notification type,
        and the frontend status-pill color are all keyed to ``"denied"``);
        only the callable/route name is normalized to ``reject`` to match
        chores/homework.
        """
        User.objects.select_for_update(no_key=True).get(pk=redemption.user_id)
        _lock_decision(redemption)
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
        reward = Reward.objects.select_for_update(no_key=True).get(pk=redemption.reward_id)
        if redemption.stock_reserved and reward.stock is not None:
            Reward.objects.filter(pk=reward.pk).update(stock=F("stock") + 1)
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
            about_user=user,
        )

        return exchange

    @staticmethod
    @transaction.atomic
    def approve(exchange, parent, notes=""):
        # Defence in depth on the one service method that moves real money.
        # ``parent`` is otherwise used only for attribution, so nothing here
        # would have stopped a non-parent caller: the viewset's permission
        # class was the only gate, and when ExchangeRequestViewSet's approve
        # was wired by hand its @action gate was silently inert (see
        # ApprovalActionMixin.get_permissions). Both API call sites already
        # check the role — DRF via IsParent, MCP via require_parent() — so this
        # only fires if a future caller forgets.
        if getattr(parent, "role", None) != User.Role.PARENT:
            raise PermissionDenied("Only a parent can approve an exchange.")

        _lock_decision(exchange)
        if exchange.status != ExchangeRequest.Status.PENDING:
            return exchange

        from apps.payments.models import PaymentLedger
        from apps.payments.services import PaymentService

        user = exchange.user
        dollar_amount = exchange.dollar_amount
        coin_amount = exchange.coin_amount

        # Different pending requests can spend the same wallet. Serialize
        # their balance check and debit on the stable user row, including
        # when there are no prior ledger rows to lock.
        User.objects.select_for_update(no_key=True).get(pk=user.pk)
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
        _lock_decision(exchange)
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
