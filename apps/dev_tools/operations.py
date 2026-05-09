"""Pure-Python operations behind every dev_tools command + REST endpoint.

One function per operation. Both ``apps/dev_tools/management/commands/*.py``
and ``apps/dev_tools/views.py`` call into here so the logic lives once.

Functions take resolved Django objects (``User``, etc.), NOT raw strings —
the resolver helpers in ``_helpers.py`` and the DRF serializers in
``serializers.py`` translate inputs at the boundary.

Each returns a JSON-serializable ``dict`` describing what changed. Failure
modes raise ``OperationError`` with a human-readable message — both
callers translate that (command → ``CommandError``, view → ``400``).
"""
from __future__ import annotations

import random
from datetime import timedelta
from importlib import import_module
from typing import Any

from django.db.models import F
from django.utils import timezone


class OperationError(Exception):
    """Domain error from a dev_tools operation. Caught by both UIs."""


# --------------------------------------------------------------------------
# A. Force events
# --------------------------------------------------------------------------

def force_drop(
    user,
    *,
    rarity: str | None = None,
    slug: str | None = None,
    count: int = 1,
    salvage: bool = False,
    trigger: str = "dev_tools",
) -> dict[str, Any]:
    """Write ``DropLog`` + ``UserInventory`` directly. Bypasses RNG."""
    from apps.rpg.models import DropLog, ItemDefinition, UserInventory

    if not rarity and not slug:
        raise OperationError("Must pass rarity or slug.")

    if slug:
        try:
            item = ItemDefinition.objects.get(slug=slug)
        except ItemDefinition.DoesNotExist as e:
            raise OperationError(f"No ItemDefinition with slug={slug!r}") from e
    else:
        pool = list(ItemDefinition.objects.filter(rarity=rarity))
        if not pool:
            raise OperationError(
                f"No ItemDefinition rows at rarity={rarity!r}. "
                "Run `loadrpgcontent` first."
            )
        item = random.choice(pool)

    for _ in range(count):
        if not salvage:
            inv, created = UserInventory.objects.get_or_create(
                user=user, item=item, defaults={"quantity": 1},
            )
            if not created:
                UserInventory.objects.filter(pk=inv.pk).update(
                    quantity=F("quantity") + 1,
                )
        elif item.coin_value > 0:
            from apps.rewards.models import CoinLedger
            from apps.rewards.services import CoinService

            CoinService.award_coins(
                user, item.coin_value, CoinLedger.Reason.ADJUSTMENT,
                description=f"[dev_tools] Salvaged duplicate: {item.name}",
            )

        DropLog.objects.create(
            user=user, item=item, trigger_type=trigger,
            quantity=1, was_salvaged=salvage,
        )

    return {
        "user": user.username,
        "item": {
            "id": item.pk,
            "slug": item.slug,
            "name": item.name,
            "rarity": item.rarity,
        },
        "count": count,
        "salvaged": salvage,
    }


def force_celebration(
    user,
    *,
    kind: str,
    days: int = 30,
    gift_coins: int = 500,
) -> dict[str, Any]:
    """Trigger ``CelebrationModal`` / ``BirthdayCelebrationModal`` via notification."""
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    if kind == "streak_milestone":
        n = notify(
            user,
            title=f"{days}-day streak!",
            message=f"Lit the journal {days} days running.",
            notification_type=NotificationType.STREAK_MILESTONE,
        )
        return {"kind": kind, "notification_id": n.pk, "days": days}

    if kind == "perfect_day":
        n = notify(
            user,
            title="Perfect day",
            message="Every daily ritual touched.",
            notification_type=NotificationType.PERFECT_DAY,
        )
        return {"kind": kind, "notification_id": n.pk}

    if kind == "birthday":
        from apps.chronicle.services import ChronicleService

        entry = ChronicleService.record_birthday(user)
        entry.metadata["gift_coins"] = gift_coins
        entry.save(update_fields=["metadata"])
        n = notify(
            user,
            title=(
                f"Happy birthday, "
                f"{getattr(user, 'display_label', user.username)}!"
            ),
            message=(
                "Your Yearbook has a new entry and "
                f"{gift_coins} coins are in your treasury."
            ),
            notification_type=NotificationType.BIRTHDAY,
        )
        return {
            "kind": kind,
            "notification_id": n.pk,
            "chronicle_entry_id": entry.pk,
            "gift_coins": gift_coins,
        }

    raise OperationError(f"Unknown celebration kind: {kind!r}")


# --------------------------------------------------------------------------
# B. Set state
# --------------------------------------------------------------------------

def set_streak(user, *, days: int, perfect_days: int | None = None) -> dict[str, Any]:
    from apps.rpg.models import CharacterProfile

    profile, _ = CharacterProfile.objects.get_or_create(user=user)
    profile.login_streak = days
    profile.longest_login_streak = max(profile.longest_login_streak, days)
    profile.last_active_date = timezone.localdate()

    update_fields = ["login_streak", "longest_login_streak", "last_active_date"]
    if perfect_days is not None:
        profile.perfect_days_count = perfect_days
        update_fields.append("perfect_days_count")
    profile.save(update_fields=update_fields)

    return {
        "user": user.username,
        "login_streak": profile.login_streak,
        "longest_login_streak": profile.longest_login_streak,
        "perfect_days_count": profile.perfect_days_count,
        "last_active_date": str(profile.last_active_date),
    }


def set_reward_stock(*, reward_ref: str, stock: int) -> dict[str, Any]:
    """Lookup by id (numeric) or fuzzy name match."""
    from apps.rewards.models import Reward

    if reward_ref.isdigit():
        reward = Reward.objects.filter(pk=int(reward_ref)).first()
    else:
        qs = Reward.objects.filter(name__icontains=reward_ref)
        count = qs.count()
        if count > 1:
            names = list(qs.values_list("name", flat=True)[:5])
            raise OperationError(
                f"reward={reward_ref!r} matched {count} rewards: "
                f"{', '.join(names)}. Be more specific."
            )
        reward = qs.first()

    if reward is None:
        raise OperationError(f"No Reward found for reward={reward_ref!r}.")

    prev = reward.stock
    reward.stock = stock
    reward.save(update_fields=["stock"])

    return {
        "reward_id": reward.pk,
        "name": reward.name,
        "prev_stock": prev,
        "new_stock": stock,
    }


def expire_journal(user, *, days_back: int = 1) -> dict[str, Any]:
    from apps.chronicle.models import ChronicleEntry

    today = timezone.localdate()
    target_day = today - timedelta(days=days_back)
    chapter_year = target_day.year if target_day.month >= 8 else target_day.year - 1

    existing_today = ChronicleEntry.objects.filter(
        user=user, kind=ChronicleEntry.Kind.JOURNAL, occurred_on=today,
    ).first()
    if existing_today is not None:
        existing_today.occurred_on = target_day
        existing_today.chapter_year = chapter_year
        existing_today.save(update_fields=["occurred_on", "chapter_year"])
        return {
            "user": user.username,
            "entry_id": existing_today.pk,
            "occurred_on": str(target_day),
            "action": "backdated",
        }

    existing_target = ChronicleEntry.objects.filter(
        user=user, kind=ChronicleEntry.Kind.JOURNAL, occurred_on=target_day,
    ).first()
    if existing_target is not None:
        return {
            "user": user.username,
            "entry_id": existing_target.pk,
            "occurred_on": str(target_day),
            "action": "noop_already_present",
        }

    entry = ChronicleEntry.objects.create(
        user=user,
        kind=ChronicleEntry.Kind.JOURNAL,
        occurred_on=target_day,
        chapter_year=chapter_year,
        title=f"{target_day.strftime('%B')} {target_day.day} entry",
        summary="Synthesized by dev_tools.expire_journal for lock-state testing.",
        is_private=True,
    )
    return {
        "user": user.username,
        "entry_id": entry.pk,
        "occurred_on": str(target_day),
        "action": "created",
    }


# Backdating values picked to fall safely INSIDE each band defined by
# apps.pets.services.HAPPINESS_THRESHOLDS = {happy:3, bored:7, stale:14}.
PET_HAPPINESS_DAYS_BACK = {
    "happy": 0,
    "bored": 4,
    "stale": 8,
    "away": 15,
}


def set_pet_happiness(user, *, level: str, pet_id: int | None = None) -> dict[str, Any]:
    from apps.pets.models import UserPet

    if level not in PET_HAPPINESS_DAYS_BACK:
        raise OperationError(
            f"Unknown happiness level={level!r}. Use one of "
            f"{list(PET_HAPPINESS_DAYS_BACK)}."
        )

    days_back = PET_HAPPINESS_DAYS_BACK[level]
    target = timezone.now() - timedelta(days=days_back)

    qs = UserPet.objects.filter(user=user, evolved_to_mount=False)
    if pet_id is not None:
        qs = qs.filter(pk=pet_id)

    pet_count = qs.count()
    if pet_count == 0:
        raise OperationError(
            f"No matching unevolved UserPet rows for user={user.username}"
            + (f", pet={pet_id}" if pet_id else "")
            + ". Hatch one first."
        )

    qs.update(last_fed_at=target)
    return {
        "user": user.username,
        "level": level,
        "pets_updated": pet_count,
        "last_fed_at": str(target.date()),
    }


# --------------------------------------------------------------------------
# C. Tick scheduled tasks
# --------------------------------------------------------------------------

def tick_perfect_day() -> dict[str, Any]:
    from apps.rpg.tasks import evaluate_perfect_day_task

    return {"task": "evaluate_perfect_day_task", "result": evaluate_perfect_day_task()}


# --------------------------------------------------------------------------
# D. Day reset
# --------------------------------------------------------------------------

DAY_COUNTER_KINDS = {
    "homework": ("apps.homework.models", "HomeworkDailyCounter"),
    "creation": ("apps.creations.models", "CreationDailyCounter"),
    "movement": ("apps.movement.models", "MovementDailyCounter"),
}


def reset_day_counters(user, *, kind: str = "all") -> dict[str, Any]:
    today = timezone.localdate()
    targets = (
        DAY_COUNTER_KINDS
        if kind == "all"
        else {kind: DAY_COUNTER_KINDS[kind]}
        if kind in DAY_COUNTER_KINDS
        else None
    )
    if targets is None:
        raise OperationError(
            f"Unknown counter kind={kind!r}. "
            f"Use one of {list(DAY_COUNTER_KINDS)} or 'all'."
        )

    deleted = {}
    for k, (module_path, cls_name) in targets.items():
        cls = getattr(import_module(module_path), cls_name)
        qs = cls.objects.filter(user=user, occurred_on=today)
        count = qs.count()
        qs.delete()
        deleted[k] = count

    return {"user": user.username, "deleted": deleted}
