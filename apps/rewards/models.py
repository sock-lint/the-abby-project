from django.conf import settings
from django.db import models

from config.base_models import ApprovalWorkflowModel, CreatedAtModel


class CoinLedger(CreatedAtModel):
    """Append-only ledger of Coin transactions.

    Coins are a non-monetary progression currency, parallel to PaymentLedger.
    Positive amounts = earned; negative = spent or refunded.
    """

    class Reason(models.TextChoices):
        HOURLY = "hourly", "Hourly"
        PROJECT_BONUS = "project_bonus", "Project Bonus"
        BOUNTY_BONUS = "bounty_bonus", "Bounty Bonus"
        MILESTONE_BONUS = "milestone_bonus", "Milestone Bonus"
        BADGE_BONUS = "badge_bonus", "Badge Bonus"
        REDEMPTION = "redemption", "Redemption"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Adjustment"
        CHORE_REWARD = "chore_reward", "Chore Reward"
        EXCHANGE = "exchange", "Exchange"
        HOMEWORK_REWARD = "homework_reward", "Homework Reward"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="coin_entries",
    )
    amount = models.IntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    description = models.CharField(max_length=200, blank=True)
    redemption = models.ForeignKey(
        "rewards.RewardRedemption", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="coin_entries",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_coin_entries",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} {self.amount:+d} ({self.reason})"


class Reward(CreatedAtModel):
    """A non-monetary reward that can be redeemed with Coins."""

    class Rarity(models.TextChoices):
        COMMON = "common", "Common"
        UNCOMMON = "uncommon", "Uncommon"
        RARE = "rare", "Rare"
        EPIC = "epic", "Epic"
        LEGENDARY = "legendary", "Legendary"

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to="rewards/", blank=True, null=True)
    cost_coins = models.PositiveIntegerField()
    rarity = models.CharField(
        max_length=10, choices=Rarity.choices, default=Rarity.COMMON
    )
    stock = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Null = unlimited; otherwise remaining inventory.",
    )
    requires_parent_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "cost_coins", "name"]

    def __str__(self):
        return f"{self.icon} {self.name} ({self.cost_coins}c)"


class RewardRedemption(ApprovalWorkflowModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELED = "canceled", "Canceled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="redemptions",
    )
    reward = models.ForeignKey(
        Reward, on_delete=models.PROTECT, related_name="redemptions",
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING,
    )
    coin_cost_snapshot = models.PositiveIntegerField(
        help_text="Cost at time of request — authoritative for refunds.",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    parent_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"{self.user} → {self.reward.name} ({self.status})"


class ExchangeRequest(ApprovalWorkflowModel, CreatedAtModel):
    """A request to exchange money for coins, pending parent approval."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="exchange_requests",
    )
    dollar_amount = models.DecimalField(max_digits=8, decimal_places=2)
    coin_amount = models.PositiveIntegerField()
    exchange_rate = models.PositiveIntegerField(
        help_text="COINS_PER_DOLLAR at time of request — authoritative for fulfillment.",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
    )
    parent_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ${self.dollar_amount} → {self.coin_amount}c ({self.status})"
