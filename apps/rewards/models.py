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
        DAILY_CHALLENGE = "daily_challenge", "Daily Challenge"
        EXPEDITION = "expedition", "Expedition"

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
    """A non-monetary reward that can be redeemed with Coins.

    Rewards bridge two fulfillment modes:

    - ``real_world`` (default): parent fulfils by hand (trip, treat, etc.)
    - ``digital_item``: linked to an ``rpg.ItemDefinition``; approval credits
      the item to the user's ``UserInventory`` automatically.
    - ``both``: credit the item AND flag for real-world follow-through.

    The digital path lets an RPG content pack surface its items directly in
    the shop via the ``item_definition`` FK, without needing a second
    authoring surface.
    """

    class Rarity(models.TextChoices):
        COMMON = "common", "Common"
        UNCOMMON = "uncommon", "Uncommon"
        RARE = "rare", "Rare"
        EPIC = "epic", "Epic"
        LEGENDARY = "legendary", "Legendary"

    class FulfillmentKind(models.TextChoices):
        REAL_WORLD = "real_world", "Real-world (parent fulfills)"
        DIGITAL_ITEM = "digital_item", "Digital item (inventory credit)"
        BOTH = "both", "Both"

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="rewards",
    )
    name = models.CharField(max_length=100)
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
    item_definition = models.ForeignKey(
        "rpg.ItemDefinition",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="shop_rewards",
        help_text=(
            "Optional link to an RPG ItemDefinition. When set AND "
            "fulfillment_kind is digital_item or both, redemption approval "
            "credits one of this item to the user's UserInventory."
        ),
    )
    fulfillment_kind = models.CharField(
        max_length=16,
        choices=FulfillmentKind.choices,
        default=FulfillmentKind.REAL_WORLD,
    )

    class Meta:
        ordering = ["order", "cost_coins", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "name"],
                name="reward_unique_name_per_family",
            ),
        ]

    def __str__(self):
        return f"{self.icon} {self.name} ({self.cost_coins}c)"

    def save(self, *args, **kwargs):
        # Defense-in-depth: legacy callers (tests, fixtures) may still create
        # Reward rows without ``family``; route them to the default Family so
        # the row lands somewhere sensible rather than raising IntegrityError.
        # Production paths (RewardViewSet.perform_create, MCP tools) always
        # supply an explicit family — this is purely a safety net.
        if self.family_id is None:
            from apps.families.models import Family
            family, _ = Family.objects.get_or_create(
                slug="default-family",
                defaults={"name": "Default Family"},
            )
            self.family = family
        super().save(*args, **kwargs)


class RewardRedemption(ApprovalWorkflowModel, CreatedAtModel):
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
    parent_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} → {self.reward.name} ({self.status})"


class RewardWishlist(CreatedAtModel):
    """A child has bookmarked this reward — nudge them when stock returns.

    A lightweight (user, reward) pair. Created when a child taps
    "Notify me" on an out-of-stock reward (or any reward), and cleared
    automatically when (a) the user redeems it, or (b) it's been
    notified-about-restock so a single toggle doesn't spam.

    Per-family scoping is implicit through ``reward.family`` — a child
    can only wishlist a reward in their own family because the rewards
    list is already family-filtered. We don't enforce it again at the
    DB layer (the reward FK is enough; cross-family POSTs 404 from the
    queryset filter before they reach this row).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reward_wishlist_entries",
    )
    reward = models.ForeignKey(
        Reward, on_delete=models.CASCADE, related_name="wishlist_entries",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "reward"],
                name="reward_wishlist_unique_user_reward",
            ),
        ]

    def __str__(self):
        return f"{self.user} ★ {self.reward.name}"


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
