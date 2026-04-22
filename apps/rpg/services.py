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
    # Check-in drops are intentionally 0 — the reward for daily_check_in is
    # coin bonus (via multiplier) + Companion pet growth, not item drops.
    # Kept in the map so BASE_DROP_RATES.get() returns a sensible default.
    TriggerType.DAILY_CHECK_IN: 0.0,
    # Savings-goal completion already has its own coin bonus in the service
    # pipeline; the drop is a nice-to-have on top. High enough to feel like
    # a celebration, low enough that farming it via repeated small goals
    # doesn't out-farm normal play.
    TriggerType.SAVINGS_GOAL_COMPLETE: 0.80,
}

STREAK_DROP_BONUS_PER_DAY = 0.05
STREAK_DROP_BONUS_CAP = 0.50

# Active-boost multipliers. Scholar's Draught doubles XP, Lucky Coin doubles
# earn-kind coins, Drop Charm adds 20% to effective drop rate. Each is gated
# by a timer on ``CharacterProfile`` — the ConsumableService sets the expiry,
# these helpers read it.
XP_BOOST_MULTIPLIER = 2.0
COIN_BOOST_MULTIPLIER = 2.0
DROP_BOOST_ADDITIVE = 0.20


def _boost_active(user, field_name) -> bool:
    """True when ``CharacterProfile.<field_name>`` is set to a future timestamp.

    Used to read the three timer-gated consumable boosts. Returns False when
    the user has no profile yet, the field is null, or the timer has lapsed.
    Never raises — a lookup failure must not break an award path.
    """
    try:
        row = CharacterProfile.objects.filter(user=user).values(
            field_name,
        ).first()
    except Exception:
        return False
    if not row:
        return False
    expires_at = row.get(field_name)
    if expires_at is None:
        return False
    return expires_at > timezone.now()


def xp_boost_multiplier(user) -> float:
    """Return 2.0 if Scholar's Draught is active, else 1.0."""
    return XP_BOOST_MULTIPLIER if _boost_active(user, "xp_boost_expires_at") else 1.0


def coin_boost_multiplier(user) -> float:
    """Return 2.0 if Lucky Coin is active, else 1.0."""
    return COIN_BOOST_MULTIPLIER if _boost_active(user, "coin_boost_expires_at") else 1.0


def drop_boost_additive(user) -> float:
    """Return +0.20 rate bonus if Drop Charm is active, else 0."""
    return DROP_BOOST_ADDITIVE if _boost_active(user, "drop_boost_expires_at") else 0.0


# Coin-reason set that gets doubled by an active Lucky Coin boost. Excludes
# ADJUSTMENT (check-in, salvage, parent manual adjust — mixed signs), REFUND
# (restores cost, not new earnings), REDEMPTION (spend), and EXCHANGE (has
# its own 1:1 rate that shouldn't double).
_BOOSTABLE_COIN_REASONS = frozenset({
    "hourly",
    "project_bonus",
    "bounty_bonus",
    "milestone_bonus",
    "badge_bonus",
    "chore_reward",
})


def is_boostable_coin_reason(reason) -> bool:
    """True when a positive coin award for this reason should honor coin_boost."""
    return str(reason) in _BOOSTABLE_COIN_REASONS


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
        streak_broken = False
        prior_streak = profile.login_streak
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
                # A streak long enough to matter got broken — worth flagging.
                # 3 is the existing "Three Day Streak" threshold; anything
                # below that isn't really a streak worth a comeback nudge.
                streak_broken = prior_streak >= 3
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

        # Companion pets passively grow from the daily check-in — the
        # slow-burn bonding loop for kids whose engagement isn't heavy
        # project work. Wrapped so a pet-service failure never breaks
        # the streak flow.
        try:
            from apps.pets.services import PetService
            PetService.auto_grow_companions(user)
        except Exception:
            logger.exception("Companion auto-growth hook failed")

        # If the prior streak broke (not covered by freeze), offer a
        # comeback-quest notification so the child sees a low-stakes
        # path back. We don't auto-assign — the child opts in from the
        # notification to respect the one-active-quest limit.
        if streak_broken:
            try:
                from apps.notifications.models import NotificationType
                from apps.notifications.services import notify
                from apps.quests.models import Quest, QuestDefinition

                has_active = Quest.objects.filter(
                    participants__user=user, status=Quest.Status.ACTIVE,
                ).exists()
                comeback = QuestDefinition.objects.filter(name="Comeback Kid").first()
                if not has_active and comeback:
                    notify(
                        user,
                        title="Your streak reset — ready to rebuild?",
                        message=(
                            f"Your {prior_streak}-day streak just ended. "
                            "The Comeback Kid quest asks for just 3 habit logs "
                            "to rebuild the loop — claim a Streak Freeze when "
                            "you finish it."
                        ),
                        notification_type=NotificationType.COMEBACK_SUGGESTED,
                        link=f"/quests?suggest={comeback.pk}",
                    )
            except Exception:
                logger.exception("Streak-break comeback suggestion failed")

        return {
            "is_first_today": True,
            "check_in_bonus_coins": bonus_coins,
            "streak": profile.login_streak,
            "multiplier": round(multiplier, 2),
            "freeze_consumed": consumed_freeze,
            "streak_broken": streak_broken,
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
        boost_bonus = drop_boost_additive(user)
        effective_rate = min(base_rate + streak_bonus + boost_bonus, 1.0)
        roll = random.random()

        if roll > effective_rate:
            ActivityLogService.record(
                category="rpg",
                event_type="rpg.drop_rolled",
                summary=f"No drop ({trigger_type})",
                subject=user,
                breakdown=[
                    {"label": "base rate", "value": base_rate, "op": "+"},
                    {"label": "streak bonus", "value": round(streak_bonus, 3), "op": "+"},
                    {"label": "drop boost", "value": round(boost_bonus, 3), "op": "="},
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
                {"label": "streak bonus", "value": round(streak_bonus, 3), "op": "+"},
                {"label": "drop boost", "value": round(boost_bonus, 3), "op": "="},
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

            # Step 5b: Daily challenge progress — lightweight slot separate
            # from the main quest. Wrapped so the parent flow never breaks
            # if the daily-challenge subsystem is misbehaving.
            daily_result = None
            try:
                from apps.quests.services import DailyChallengeService
                challenge, newly_complete = DailyChallengeService.record_progress(
                    user, trigger_type, context,
                )
                if challenge:
                    daily_result = {
                        "challenge_id": challenge.pk,
                        "challenge_type": challenge.challenge_type,
                        "progress": challenge.current_progress,
                        "target": challenge.target_value,
                        "newly_completed": newly_complete,
                    }
                    if newly_complete:
                        notifications.append(
                            f"Daily challenge complete: "
                            f"{challenge.get_challenge_type_display()}"
                        )
            except Exception:
                logger.exception("Daily-challenge progress hook failed")

            # Step 6: Chronicle firsts — wrapped so a chronicle failure never
            # breaks the parent flow.
            try:
                result_chronicle = GameLoopService._record_chronicle_firsts(
                    user, trigger_type, context
                )
            except Exception:  # pragma: no cover — defensive
                logger.exception("Chronicle firsts hook failed")
                result_chronicle = None

            return {
                "trigger_type": trigger_type,
                "streak": streak_result,
                "notifications": notifications,
                "drops": drops,
                "quest": quest_result,
                "daily_challenge": daily_result,
                "chronicle": result_chronicle,
            }


    @staticmethod
    def _record_chronicle_firsts(user, trigger_type, context):
        from apps.chronicle.firsts import slug_for
        from apps.chronicle.services import ChronicleService

        mapped = slug_for(trigger_type, context or {})
        if mapped is None:
            return None
        event_slug, title, icon_slug = mapped
        entry = ChronicleService.record_first(
            user,
            event_slug=event_slug,
            title=title,
            icon_slug=icon_slug,
        )
        if entry:
            from apps.notifications.models import Notification, NotificationType

            Notification.objects.create(
                user=user,
                notification_type=NotificationType.CHRONICLE_FIRST_EVER,
                title=title,
                message=f"{title} — added to your Yearbook.",
            )
        return {"entry_id": entry.id if entry else None, "event_slug": event_slug}


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

        # Track distinct effects ever used so Alchemist-style badges have a
        # data source. Refetch to avoid a stale copy if _apply_effect saved.
        profile.refresh_from_db(fields=["consumable_effects_used"])
        used = list(profile.consumable_effects_used or [])
        if effect not in used:
            used.append(effect)
            profile.consumable_effects_used = used
            profile.save(update_fields=["consumable_effects_used", "updated_at"])

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
        meta = item.metadata or {}
        if effect == "streak_freeze":
            duration = int(meta.get("duration_days", 1))
            today = timezone.localdate()
            profile.streak_freeze_expires_at = today + timedelta(days=duration)
            profile.streak_freezes_used += 1
            profile.save(update_fields=[
                "streak_freeze_expires_at", "streak_freezes_used", "updated_at",
            ])
            return {
                "streak_freeze_expires_at": profile.streak_freeze_expires_at.isoformat(),
            }
        if effect == "xp_boost":
            hours = int(meta.get("duration_hours", 24))
            expires = timezone.now() + timedelta(hours=hours)
            profile.xp_boost_expires_at = expires
            profile.save(update_fields=["xp_boost_expires_at", "updated_at"])
            return {"xp_boost_expires_at": expires.isoformat()}
        if effect == "coin_boost":
            hours = int(meta.get("duration_hours", 24))
            expires = timezone.now() + timedelta(hours=hours)
            profile.coin_boost_expires_at = expires
            profile.save(update_fields=["coin_boost_expires_at", "updated_at"])
            return {"coin_boost_expires_at": expires.isoformat()}
        if effect == "drop_boost":
            hours = int(meta.get("duration_hours", 24))
            expires = timezone.now() + timedelta(hours=hours)
            profile.drop_boost_expires_at = expires
            profile.save(update_fields=["drop_boost_expires_at", "updated_at"])
            return {"drop_boost_expires_at": expires.isoformat()}
        if effect == "growth_tonic":
            feeds = int(meta.get("feeds", 3))
            profile.pet_growth_boost_remaining += feeds
            profile.save(update_fields=["pet_growth_boost_remaining", "updated_at"])
            return {"pet_growth_boost_remaining": profile.pet_growth_boost_remaining}
        if effect == "rage_breaker":
            from apps.quests.models import Quest
            active = Quest.objects.filter(
                participants__user=profile.user,
                status=Quest.Status.ACTIVE,
                definition__quest_type="boss",
                rage_shield__gt=0,
            ).first()
            if not active:
                raise ValueError("No active boss quest with a rage shield to break")
            old_shield = active.rage_shield
            active.rage_shield = 0
            active.save(update_fields=["rage_shield", "updated_at"])
            return {"quest_name": active.definition.name, "rage_cleared": old_shield}
        if effect == "growth_surge":
            # One-shot big growth boost to the user's currently active pet.
            # Applies directly to UserPet.growth_points, bypassing the food
            # mechanic (so it stacks with a feed on the same day).
            from apps.pets.models import UserMount, UserPet
            amount = int(meta.get("growth", 30))
            pet = UserPet.objects.filter(
                user=profile.user, is_active=True, evolved_to_mount=False,
            ).first()
            if not pet:
                raise ValueError("No active unevolved pet to accelerate")
            pet.growth_points = min(100, pet.growth_points + amount)
            evolved_mount = None
            if pet.growth_points >= 100:
                pet.evolved_to_mount = True
                pet.save(update_fields=["growth_points", "evolved_to_mount", "updated_at"])
                mount, _ = UserMount.objects.get_or_create(
                    user=profile.user, species=pet.species, potion=pet.potion,
                )
                evolved_mount = mount.pk
            else:
                pet.save(update_fields=["growth_points", "updated_at"])
            return {
                "pet_id": pet.pk,
                "growth_added": amount,
                "new_growth": pet.growth_points,
                "evolved_to_mount": bool(evolved_mount),
            }
        if effect == "feast_platter":
            # Sweeping small growth boost to every unevolved pet in the user's
            # stable. Only one pet can be "active" per user, but Feast Platter
            # is a party treat — intentionally affects all.
            from apps.pets.models import UserPet
            per_pet = int(meta.get("growth", 10))
            pets = list(
                UserPet.objects.select_for_update().filter(
                    user=profile.user, evolved_to_mount=False,
                )
            )
            if not pets:
                raise ValueError("No pets to feed")
            for pet in pets:
                pet.growth_points = min(100, pet.growth_points + per_pet)
                pet.save(update_fields=["growth_points", "updated_at"])
            return {
                "pets_fed": len(pets),
                "growth_per_pet": per_pet,
            }
        if effect == "mystery_box":
            # Grants a single random item from a weighted pool of common +
            # uncommon non-cosmetic items. Simpler than trying to re-roll a
            # previous drop; "open the box and see what you got" reads well.
            from apps.rpg.models import ItemDefinition, UserInventory
            eligible = list(
                ItemDefinition.objects.filter(
                    rarity__in=meta.get("rarities", ["common", "uncommon"]),
                ).exclude(
                    item_type__startswith="cosmetic_",
                ).exclude(item_type=ItemDefinition.ItemType.CONSUMABLE)
            )
            if not eligible:
                raise ValueError("Mystery box has no eligible items to grant")
            weights = [5 if i.rarity == "common" else 2 for i in eligible]
            granted = random.choices(eligible, weights=weights, k=1)[0]
            inv, _ = UserInventory.objects.get_or_create(
                user=profile.user, item=granted,
                defaults={"quantity": 0},
            )
            inv.quantity += 1
            inv.save(update_fields=["quantity", "updated_at"])
            return {
                "granted_item_id": granted.pk,
                "granted_item_name": granted.name,
                "granted_rarity": granted.rarity,
            }
        if effect == "lucky_dip":
            # Cosmetic-only version of mystery_box. Weighted toward lower rarity
            # so legendary drops stay special. Honors already-owned: dupes
            # salvage to coin_value like the drop path.
            from apps.rewards.models import CoinLedger
            from apps.rewards.services import CoinService
            from apps.rpg.models import ItemDefinition, UserInventory
            eligible = list(
                ItemDefinition.objects.filter(
                    rarity__in=meta.get("rarities", ["uncommon", "rare", "epic"]),
                    item_type__startswith="cosmetic_",
                )
            )
            if not eligible:
                raise ValueError("Lucky dip has no eligible cosmetics to grant")
            rarity_weights = {"common": 10, "uncommon": 6, "rare": 3, "epic": 1, "legendary": 1}
            weights = [rarity_weights.get(i.rarity, 1) for i in eligible]
            granted = random.choices(eligible, weights=weights, k=1)[0]
            existing = UserInventory.objects.filter(
                user=profile.user, item=granted,
            ).first()
            salvaged = False
            if existing:
                salvaged = True
                if granted.coin_value > 0:
                    CoinService.award_coins(
                        profile.user, granted.coin_value, CoinLedger.Reason.ADJUSTMENT,
                        description=f"Lucky Dip salvage: {granted.name}",
                    )
            else:
                UserInventory.objects.create(
                    user=profile.user, item=granted, quantity=1,
                )
            return {
                "granted_item_id": granted.pk,
                "granted_item_name": granted.name,
                "granted_rarity": granted.rarity,
                "salvaged": salvaged,
            }
        if effect == "quest_reroll":
            # Rolls a random eligible QuestDefinition and starts it. Eligibility
            # mirrors QuestService.start_quest's guards: not already active,
            # system quest (parent quests can be hand-picked), badge gate passed.
            from apps.achievements.models import UserBadge
            from apps.quests.models import Quest, QuestDefinition
            from apps.quests.services import QuestService
            if Quest.objects.filter(
                participants__user=profile.user, status=Quest.Status.ACTIVE,
            ).exists():
                raise ValueError(
                    "You already have an active quest — finish it before rerolling"
                )
            user_badge_ids = set(
                UserBadge.objects.filter(user=profile.user).values_list("badge_id", flat=True)
            )
            candidates = [
                q for q in QuestDefinition.objects.filter(is_system=True)
                if q.required_badge_id is None or q.required_badge_id in user_badge_ids
            ]
            if not candidates:
                raise ValueError("No eligible quests to reroll into")
            picked = random.choice(candidates)
            quest = QuestService.start_quest(profile.user, picked.pk)
            return {
                "quest_id": quest.pk,
                "quest_name": picked.name,
                "quest_type": picked.quest_type,
            }
        if effect == "morale_tonic":
            # Same field as growth_tonic (pet_growth_boost_remaining) but a
            # longer duration by default. A distinct effect slug means it
            # counts toward ``consumable_variety`` separately from growth_tonic.
            feeds = int(meta.get("feeds", 5))
            profile.pet_growth_boost_remaining += feeds
            profile.save(update_fields=["pet_growth_boost_remaining", "updated_at"])
            return {"pet_growth_boost_remaining": profile.pet_growth_boost_remaining}
        if effect == "skill_tonic":
            # Grants a fixed XP bolt to the user's highest-level SkillProgress
            # row. No "pick a skill" UI needed — the tonic finds the leader
            # and tops it up. Tiebreak: most recently updated.
            from apps.achievements.models import SkillProgress, XP_THRESHOLDS
            amount = int(meta.get("xp", 50))
            progress = SkillProgress.objects.filter(
                user=profile.user, unlocked=True,
            ).order_by("-level", "-xp_points", "-id").first()
            if progress is None:
                raise ValueError("You need to unlock a skill first")
            progress.xp_points += amount
            # Promote levels while we can — mirrors SkillService's level math.
            while progress.level + 1 in XP_THRESHOLDS and (
                progress.xp_points >= XP_THRESHOLDS[progress.level + 1]
            ):
                progress.level += 1
            progress.save(update_fields=["xp_points", "level"])
            return {
                "skill_id": progress.skill_id,
                "skill_name": progress.skill.name,
                "xp_awarded": amount,
                "new_level": progress.level,
                "new_xp": progress.xp_points,
            }
        if effect == "food_basket":
            # Hands out N random food items — low-effort pet-prep kit for
            # kids who want to build up a feeding stockpile.
            from apps.rpg.models import ItemDefinition, UserInventory
            count = int(meta.get("count", 2))
            foods = list(ItemDefinition.objects.filter(
                item_type=ItemDefinition.ItemType.FOOD,
            ))
            if not foods:
                raise ValueError("Food basket has no eligible foods")
            picks = random.choices(foods, k=count)
            granted = []
            for item in picks:
                inv, _ = UserInventory.objects.get_or_create(
                    user=profile.user, item=item, defaults={"quantity": 0},
                )
                inv.quantity += 1
                inv.save(update_fields=["quantity", "updated_at"])
                granted.append({"item_id": item.pk, "item_name": item.name})
            return {"granted": granted, "count": count}
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

        # Trigger badge eval so Dressed-for-the-Quest (cosmetic_full_set) and
        # any future cosmetic-state badges can fire the moment the final slot
        # is filled. Wrapped so a badge-eval error can't block the equip.
        try:
            from apps.achievements.services import BadgeService
            BadgeService.evaluate_badges(user)
        except Exception:
            logger.exception("Badge evaluation after cosmetic equip failed")

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
