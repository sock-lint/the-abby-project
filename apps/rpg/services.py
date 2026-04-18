import logging
import random
from contextlib import contextmanager
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.rpg.constants import TriggerType
from apps.rpg.models import CharacterProfile

logger = logging.getLogger(__name__)

BASE_CHECK_IN_COINS = 5
STREAK_MULTIPLIER_PER_DAY = 0.07
STREAK_MULTIPLIER_CAP = 3.0

BASE_DROP_RATES = {
    TriggerType.CLOCK_OUT: 0.40,
    TriggerType.CHORE_COMPLETE: 0.30,
    TriggerType.HOMEWORK_COMPLETE: 0.35,
    TriggerType.HOMEWORK_CREATED: 0.15,
    TriggerType.MILESTONE_COMPLETE: 0.80,
    TriggerType.PROJECT_COMPLETE: 1.00,
    TriggerType.BADGE_EARNED: 1.00,
    TriggerType.QUEST_COMPLETE: 1.00,
    TriggerType.PERFECT_DAY: 1.00,
    TriggerType.HABIT_LOG: 0.15,
}

STREAK_DROP_BONUS_PER_DAY = 0.05
STREAK_DROP_BONUS_CAP = 0.50


class StreakService:
    """Manages daily login streaks and check-in bonuses."""

    @staticmethod
    @transaction.atomic
    def record_activity(user, activity_date=None):
        """Record daily activity, update streak, and return check-in info."""
        if activity_date is None:
            activity_date = timezone.localdate()

        profile, _created = CharacterProfile.objects.select_for_update().get_or_create(
            user=user
        )

        # Already active today — no bonus
        if profile.last_active_date == activity_date:
            return {
                "is_first_today": False,
                "check_in_bonus_coins": 0,
                "streak": profile.login_streak,
            }

        # Streak logic — with streak-freeze grace for a single missed day.
        consumed_freeze = False
        save_fields = ["login_streak", "longest_login_streak", "last_active_date"]

        if profile.last_active_date is None:
            profile.login_streak = 1
        elif (activity_date - profile.last_active_date) == timedelta(days=1):
            profile.login_streak += 1
        else:
            # Gap > 1 day. A freeze is eligible if it was armed in time to
            # cover the FIRST missed day (last_active + 1). Intuition: a
            # freeze bought on Monday that expires Tuesday protects a
            # Tuesday skip, regardless of when the child returns.
            first_missed = profile.last_active_date + timedelta(days=1)
            freeze_covers = (
                profile.streak_freeze_expires_at is not None
                and profile.streak_freeze_expires_at >= first_missed
            )
            if freeze_covers:
                profile.login_streak += 1
                profile.streak_freeze_expires_at = None
                save_fields.append("streak_freeze_expires_at")
                consumed_freeze = True
            else:
                profile.login_streak = 1

        profile.last_active_date = activity_date

        # Track all-time record
        if profile.login_streak > profile.longest_login_streak:
            profile.longest_login_streak = profile.login_streak

        profile.save(update_fields=save_fields)

        # Calculate bonus coins
        multiplier = min(
            1 + profile.login_streak * STREAK_MULTIPLIER_PER_DAY,
            STREAK_MULTIPLIER_CAP,
        )
        bonus_coins = int(BASE_CHECK_IN_COINS * multiplier)

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="rpg",
            event_type="rpg.streak_updated",
            summary=f"Streak is now {profile.login_streak} day(s)",
            subject=user,
            breakdown=[
                {"label": "streak", "value": profile.login_streak, "op": "="},
                {"label": "longest", "value": profile.longest_login_streak, "op": "note"},
                {"label": "freeze consumed", "value": consumed_freeze, "op": "note"},
            ],
            extras={
                "streak": profile.login_streak,
                "longest_login_streak": profile.longest_login_streak,
                "freeze_consumed": consumed_freeze,
            },
        )

        return {
            "is_first_today": True,
            "check_in_bonus_coins": bonus_coins,
            "streak": profile.login_streak,
            "multiplier": round(multiplier, 2),
            "freeze_consumed": consumed_freeze,
        }


class DropService:
    """Processes item drops on task completion."""

    @staticmethod
    @transaction.atomic
    def process_drops(user, trigger_type, streak_bonus=0):
        """Roll for drops and award items to user inventory.

        Returns list of dicts: [{item_id, item_name, item_icon, item_type, item_rarity, quantity, was_salvaged}]
        """
        from apps.rpg.models import CharacterProfile, DropTable, DropLog, ItemDefinition, UserInventory
        from apps.activity.services import ActivityLogService

        base_rate = BASE_DROP_RATES.get(trigger_type, 0.20)
        effective_rate = min(base_rate + streak_bonus, 1.0)
        roll = random.random()

        if roll > effective_rate:
            ActivityLogService.record(
                category="rpg",
                event_type="rpg.drop_rolled",
                summary=f"No drop ({trigger_type})",
                subject=user,
                breakdown=[
                    {"label": "base rate", "value": base_rate, "op": "+"},
                    {"label": "streak bonus", "value": round(streak_bonus, 3), "op": "="},
                    {"label": "effective", "value": round(effective_rate, 3), "op": "note"},
                    {"label": "rolled", "value": round(roll, 3), "op": "note"},
                ],
                extras={
                    "trigger_type": str(trigger_type),
                    "rolled": round(roll, 4),
                    "effective_rate": round(effective_rate, 4),
                    "dropped": False,
                },
            )
            return []

        # Get user level
        profile = CharacterProfile.objects.filter(user=user).first()
        user_level = profile.level if profile else 0

        # Get eligible drop table entries
        entries = DropTable.objects.filter(
            trigger_type=trigger_type,
            min_level__lte=user_level,
        ).select_related("item")

        if not entries.exists():
            return []

        # Weighted random selection
        items = list(entries)
        weights = [e.weight for e in items]
        selected = random.choices(items, weights=weights, k=1)[0]
        item = selected.item

        # Check for salvage (cosmetics already owned)
        was_salvaged = False
        is_cosmetic = item.item_type in (
            ItemDefinition.ItemType.COSMETIC_FRAME,
            ItemDefinition.ItemType.COSMETIC_TITLE,
            ItemDefinition.ItemType.COSMETIC_THEME,
            ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
        )

        if is_cosmetic:
            existing = UserInventory.objects.filter(user=user, item=item).first()
            if existing:
                was_salvaged = True
                if item.coin_value > 0:
                    from apps.rewards.models import CoinLedger
                    from apps.rewards.services import CoinService
                    CoinService.award_coins(
                        user, item.coin_value, CoinLedger.Reason.ADJUSTMENT,
                        description=f"Salvaged duplicate: {item.name}",
                    )

        if not was_salvaged:
            inv, created = UserInventory.objects.get_or_create(
                user=user, item=item,
                defaults={"quantity": 1},
            )
            if not created:
                inv.quantity += 1
                inv.save(update_fields=["quantity", "updated_at"])

        # Log the drop
        drop_log = DropLog.objects.create(
            user=user, item=item, trigger_type=trigger_type,
            quantity=1, was_salvaged=was_salvaged,
        )

        ActivityLogService.record(
            category="rpg",
            event_type="rpg.drop_rolled",
            summary=(f"Salvaged duplicate: {item.name}" if was_salvaged
                     else f"Dropped: {item.name} ({item.rarity})"),
            subject=user,
            target=drop_log,
            breakdown=[
                {"label": "base rate", "value": base_rate, "op": "+"},
                {"label": "streak bonus", "value": round(streak_bonus, 3), "op": "="},
                {"label": "effective", "value": round(effective_rate, 3), "op": "note"},
                {"label": "rolled", "value": round(roll, 3), "op": "note"},
                {"label": "item", "value": f"{item.name} ({item.rarity})", "op": "note"},
            ],
            extras={
                "trigger_type": str(trigger_type),
                "rolled": round(roll, 4),
                "effective_rate": round(effective_rate, 4),
                "dropped": True,
                "item_id": item.pk,
                "item_name": item.name,
                "item_rarity": item.rarity,
                "was_salvaged": was_salvaged,
            },
        )

        return [{
            "item_id": item.pk,
            "item_name": item.name,
            "item_icon": item.icon,
            "item_type": item.item_type,
            "item_rarity": item.rarity,
            "quantity": 1,
            "was_salvaged": was_salvaged,
        }]


STREAK_MILESTONES = {3, 7, 14, 30, 60, 100}


class GameLoopService:
    """Central orchestrator called after any task completion."""

    @staticmethod
    @transaction.atomic
    def on_task_completed(user, trigger_type, context=None):
        if context is None:
            context = {}

        from apps.activity.services import (
            ActivityLogService, activity_scope, current_correlation_id,
        )

        # Re-enter the same scope if one is already open (chore approval
        # already wrapped us); otherwise open a fresh correlation scope so
        # every downstream emission shares one UUID.
        scope_cm = (
            activity_scope()
            if current_correlation_id() is None
            else _noop_scope()
        )

        with scope_cm:
            notifications = []

            # Step 1: record daily activity
            streak_result = StreakService.record_activity(user)

            # Step 2: award check-in bonus coins if first activity today
            bonus = streak_result["check_in_bonus_coins"]
            if streak_result["is_first_today"] and bonus > 0:
                from apps.rewards.models import CoinLedger
                from apps.rewards.services import CoinService

                # Suppress the inner ledger.coins.adjustment emission — the
                # rpg.check_in_bonus row below is the canonical record of
                # this calculation (base × multiplier = result).
                with activity_scope(suppress_inner_ledger=True):
                    CoinService.award_coins(
                        user,
                        bonus,
                        CoinLedger.Reason.ADJUSTMENT,
                        description="Daily check-in bonus",
                    )
                ActivityLogService.record(
                    category="rpg",
                    event_type="rpg.check_in_bonus",
                    summary=f"Daily check-in bonus: +{bonus} coins",
                    subject=user,
                    coins_delta=int(bonus),
                    breakdown=[
                        {"label": "base", "value": BASE_CHECK_IN_COINS, "op": "×"},
                        {"label": f"day {streak_result['streak']} multiplier",
                         "value": streak_result["multiplier"], "op": "="},
                        {"label": "coins awarded", "value": bonus, "op": "note"},
                    ],
                    extras={
                        "base": BASE_CHECK_IN_COINS,
                        "multiplier": streak_result["multiplier"],
                        "streak": streak_result["streak"],
                    },
                )

            # Step 3: streak milestone notification
            streak = streak_result["streak"]
            if streak in STREAK_MILESTONES:
                from apps.notifications.services import notify

                msg = f"Keep it up! You've been active {streak} days in a row."
                notify(
                    user,
                    title=f"\U0001f525 {streak}-day streak!",
                    message=msg,
                    notification_type="streak_milestone",
                    link="/",
                )
                notifications.append(f"{streak}-day streak milestone")

            # Step 4: Drop roll
            # Callers can set ``context["drops_allowed"]=False`` to suppress the
            # drop roll while still recording streak + quest progress — used by
            # daily-capped triggers like ``homework_created`` to prevent farming
            # via "create 50 assignments then delete them."
            streak_bonus = min(
                streak_result["streak"] * STREAK_DROP_BONUS_PER_DAY,
                STREAK_DROP_BONUS_CAP,
            )
            if context.get("drops_allowed", True):
                drops = DropService.process_drops(user, trigger_type, streak_bonus)
            else:
                drops = []

            if drops:
                from apps.notifications.services import notify

                drop_names = ", ".join(d["item_name"] for d in drops)
                notify(
                    user,
                    title=f"Item dropped: {drop_names}",
                    message=f"You found {drop_names}!",
                    notification_type="badge_earned",
                    link="/inventory",
                )

            # Step 5: Quest progress
            quest_result = None
            try:
                from apps.quests.services import QuestService
                quest_result = QuestService.record_progress(user, trigger_type, context)
            except Exception:
                logger.exception("Quest progress failed for user %s", user.pk)

            if quest_result and quest_result.get("completed"):
                notifications.append(f"Quest complete: {quest_result['quest_name']}")

            return {
                "trigger_type": trigger_type,
                "streak": streak_result,
                "notifications": notifications,
                "drops": drops,
                "quest": quest_result,
            }


@contextmanager
def _noop_scope():
    """No-op context manager used when we're already inside an activity scope."""
    yield


class ConsumableService:
    """Applies the effect of a single-use ItemType.CONSUMABLE item.

    Consumables opt in by setting ``metadata = {"effect": "<slug>"}``. Each
    effect slug maps to a function here; unknown effects raise ValueError so
    a typo in content YAML doesn't quietly no-op.
    """

    @staticmethod
    @transaction.atomic
    def use(user, item_id):
        from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory

        try:
            inv = UserInventory.objects.select_for_update().get(
                user=user, item_id=item_id, quantity__gte=1,
            )
        except UserInventory.DoesNotExist:
            raise ValueError("You don't own that item")

        item = inv.item
        if item.item_type != ItemDefinition.ItemType.CONSUMABLE:
            raise ValueError("That item is not a consumable")

        effect = (item.metadata or {}).get("effect")
        if not effect:
            raise ValueError("That consumable has no effect configured")

        profile, _ = CharacterProfile.objects.select_for_update().get_or_create(user=user)
        detail = ConsumableService._apply_effect(profile, effect, item)

        inv.quantity -= 1
        if inv.quantity == 0:
            inv.delete()
        else:
            inv.save(update_fields=["quantity", "updated_at"])

        return {
            "item_id": item.pk,
            "item_name": item.name,
            "effect": effect,
            "detail": detail,
        }

    @staticmethod
    def _apply_effect(profile, effect, item):
        if effect == "streak_freeze":
            duration = int((item.metadata or {}).get("duration_days", 1))
            today = timezone.localdate()
            profile.streak_freeze_expires_at = today + timedelta(days=duration)
            profile.save(update_fields=["streak_freeze_expires_at", "updated_at"])
            return {
                "streak_freeze_expires_at": profile.streak_freeze_expires_at.isoformat(),
            }
        raise ValueError(f"Unknown consumable effect: {effect!r}")


class CosmeticService:
    """Manages equipping/unequipping cosmetic items."""

    COSMETIC_SLOT_MAP = {
        "cosmetic_frame": "active_frame",
        "cosmetic_title": "active_title",
        "cosmetic_theme": "active_theme",
        "cosmetic_pet_accessory": "active_pet_accessory",
    }

    @staticmethod
    @transaction.atomic
    def equip(user, item_id):
        """Equip a cosmetic item to the appropriate slot.

        Returns dict with slot and equipped item, or raises ValueError.
        """
        from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory

        try:
            item = ItemDefinition.objects.get(pk=item_id)
        except ItemDefinition.DoesNotExist:
            raise ValueError("Item not found")

        slot = CosmeticService.COSMETIC_SLOT_MAP.get(item.item_type)
        if not slot:
            raise ValueError("That item is not a cosmetic")

        # Must own the item
        if not UserInventory.objects.filter(user=user, item=item, quantity__gte=1).exists():
            raise ValueError("You don't own that item")

        profile, _ = CharacterProfile.objects.get_or_create(user=user)
        setattr(profile, slot, item)
        profile.save(update_fields=[slot, "updated_at"])

        return {"slot": slot, "item_id": item.pk, "item_name": item.name}

    @staticmethod
    @transaction.atomic
    def unequip(user, slot):
        """Clear a cosmetic slot."""
        from apps.rpg.models import CharacterProfile

        if slot not in CosmeticService.COSMETIC_SLOT_MAP.values():
            raise ValueError(f"Invalid slot: {slot}")

        profile, _ = CharacterProfile.objects.get_or_create(user=user)
        setattr(profile, slot, None)
        profile.save(update_fields=[slot, "updated_at"])

        return {"slot": slot}

    @staticmethod
    def list_owned_cosmetics(user):
        """Return cosmetic items the user owns, grouped by slot."""
        from apps.rpg.models import ItemDefinition, UserInventory

        cosmetic_types = list(CosmeticService.COSMETIC_SLOT_MAP.keys())
        entries = UserInventory.objects.filter(
            user=user, item__item_type__in=cosmetic_types,
        ).select_related("item")

        result = {slot: [] for slot in CosmeticService.COSMETIC_SLOT_MAP.values()}
        for entry in entries:
            slot = CosmeticService.COSMETIC_SLOT_MAP[entry.item.item_type]
            result[slot].append(entry.item)
        return result
