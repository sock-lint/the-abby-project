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


# --------------------------------------------------------------------------
# E. Toast & ceremony coverage (added 2026-05-11)
#
# Each op below drives one of the surfaces enumerated under the "Toast &
# ceremony reveals" section of docs/manual-testing.md. They share a few
# constraints:
#   * Notifications go through ``apps.notifications.services.notify`` so
#     the row shape matches production fan-outs.
#   * Pet/mount lookups always verify ``user`` ownership before touching
#     state — the kid-targeting flows already protect cross-family
#     access via ``get_child_or_404`` at the view layer, but the op stays
#     defensive in case a future caller skips the view.
#   * The pre-positioning ops (set_pet_growth, grant_hatch_ingredients,
#     clear_mount_breed_cooldowns) intentionally do NOT trigger the
#     resulting ceremony themselves — the modal is launched from the
#     child's UI tap. The op seeds state; the tester verifies.
# --------------------------------------------------------------------------

# 12 notification types the child-side ``useApprovalToasts`` hook watches.
# Mirrors ``APPROVAL_TYPES`` in frontend/src/hooks/useApprovalToasts.js.
# Exchange uses ``denied`` instead of ``rejected`` to match the model enum.
APPROVAL_NOTIFICATION_TYPES = {
    ("chore", "approved"): "chore_approved",
    ("chore", "rejected"): "chore_rejected",
    ("homework", "approved"): "homework_approved",
    ("homework", "rejected"): "homework_rejected",
    ("creation", "approved"): "creation_approved",
    ("creation", "rejected"): "creation_rejected",
    ("exchange", "approved"): "exchange_approved",
    ("exchange", "rejected"): "exchange_denied",
    ("chore_proposal", "approved"): "chore_proposal_approved",
    ("chore_proposal", "rejected"): "chore_proposal_rejected",
    ("habit_proposal", "approved"): "habit_proposal_approved",
    ("habit_proposal", "rejected"): "habit_proposal_rejected",
}

APPROVAL_TITLES = {
    "chore": ("Chore approved", "Chore returned"),
    "homework": ("Homework approved", "Homework returned"),
    "creation": ("Creation approved", "Creation returned"),
    "exchange": ("Exchange approved", "Exchange denied"),
    "chore_proposal": ("Duty proposal approved", "Duty proposal returned"),
    "habit_proposal": ("Ritual proposal approved", "Ritual proposal returned"),
}


def force_approval_notification(
    user, *, flow: str, outcome: str, note: str = "",
) -> dict[str, Any]:
    """Insert one approval-style ``Notification`` row for ``ApprovalToastStack``."""
    from apps.notifications.services import notify

    key = (flow, outcome)
    if key not in APPROVAL_NOTIFICATION_TYPES:
        raise OperationError(
            f"Unknown approval flow={flow!r} or outcome={outcome!r}. "
            f"Use flow in {sorted({k[0] for k in APPROVAL_NOTIFICATION_TYPES})} "
            f"and outcome in {{'approved', 'rejected'}}."
        )

    notif_type = APPROVAL_NOTIFICATION_TYPES[key]
    title_pair = APPROVAL_TITLES[flow]
    title = title_pair[0] if outcome == "approved" else title_pair[1]

    if outcome == "approved":
        body = "[dev_tools] simulated approval — toast surface check"
    else:
        body = "[dev_tools] simulated rejection"
        if note:
            body = f"{body} — {note}"

    n = notify(
        user, title=title, message=body,
        notification_type=notif_type,
    )
    return {
        "notification_id": n.pk,
        "notification_type": notif_type,
        "title": title,
        "message": body,
    }


def force_quest_progress(user, *, delta: int = 10) -> dict[str, Any]:
    """Ensure an active quest, bump ``current_progress`` by ``delta``, return shape.

    Drives ``QuestProgressToastStack``: the hook polls ``getActiveQuest()``
    and emits a toast on any ``current_progress`` delta.
    """
    from apps.quests.models import Quest, QuestDefinition
    from apps.quests.services import QuestService

    if delta <= 0:
        raise OperationError("delta must be positive.")

    quest = (
        Quest.objects
        .filter(participants__user=user, status=Quest.Status.ACTIVE)
        .select_related("definition")
        .first()
    )

    if quest is None:
        # Pick the first eligible system definition: no required badge,
        # no pre-existing active quest of this user (already true since
        # the user has no active quest), prefer system-curated.
        definition = (
            QuestDefinition.objects
            .filter(required_badge__isnull=True)
            .order_by("-is_system", "name")
            .first()
        )
        if definition is None:
            raise OperationError(
                "No eligible QuestDefinition (one with no required badge) — "
                "seed quests with `loadrpgcontent` first."
            )
        try:
            quest = QuestService.start_quest(user, definition.pk)
        except ValueError as e:
            raise OperationError(str(e)) from e

    target = quest.definition.target_value
    new_progress = min(target, quest.current_progress + delta)
    quest.current_progress = new_progress
    quest.save(update_fields=["current_progress", "updated_at"])

    percent = round((new_progress / target) * 100, 1) if target else 0.0
    return {
        "quest_id": quest.pk,
        "definition_name": quest.definition.name,
        "current_progress": new_progress,
        "target_value": target,
        "progress_percent": percent,
        "delta": delta,
    }


def mark_daily_challenge_ready(user) -> dict[str, Any]:
    """Force today's ``DailyChallenge`` into the ready-to-claim state."""
    from apps.quests.services import DailyChallengeService

    challenge = DailyChallengeService.get_or_create_today(user)
    challenge.current_progress = challenge.target_value
    if challenge.completed_at is None:
        challenge.completed_at = timezone.now()
    challenge.save(update_fields=[
        "current_progress", "completed_at", "updated_at",
    ])
    return {
        "challenge_id": challenge.pk,
        "kind": challenge.challenge_type,
        "current_progress": challenge.current_progress,
        "target_value": challenge.target_value,
        "coin_reward": challenge.coin_reward,
        "xp_reward": challenge.xp_reward,
        "ready": True,
    }


def set_pet_growth(user, *, pet_id: int, growth: int = 99) -> dict[str, Any]:
    """Direct-assign ``UserPet.growth_points`` (bypasses the consumable cap)."""
    from apps.pets.models import UserPet

    if not 0 <= growth <= 99:
        raise OperationError(
            "growth must be between 0 and 99 (use 99 for near-evolution). "
            "Trip 100 by feeding to fire the evolve ceremony."
        )

    try:
        pet = UserPet.objects.get(pk=pet_id, user=user)
    except UserPet.DoesNotExist as e:
        raise OperationError("Pet not found in this user's stable.") from e
    if pet.evolved_to_mount:
        raise OperationError(
            "Pet has already evolved; pick an unevolved one."
        )

    pet.growth_points = growth
    pet.save(update_fields=["growth_points", "updated_at"])
    return {
        "pet_id": pet.pk,
        "species_name": pet.species.name,
        "growth_points": growth,
    }


def grant_hatch_ingredients(
    user, *, species_slug: str, potion_slug: str,
) -> dict[str, Any]:
    """Drop one matching egg + one matching potion into ``UserInventory``."""
    from apps.pets.models import PetSpecies, PotionType
    from apps.rpg.models import ItemDefinition, UserInventory

    try:
        species = PetSpecies.objects.get(slug=species_slug)
    except PetSpecies.DoesNotExist as e:
        raise OperationError(
            f"No PetSpecies with slug={species_slug!r}."
        ) from e
    try:
        potion = PotionType.objects.get(slug=potion_slug)
    except PotionType.DoesNotExist as e:
        raise OperationError(
            f"No PotionType with slug={potion_slug!r}."
        ) from e

    # Verify combo if species has narrowed its potions; an empty
    # available_potions relation = all potions OK.
    available = list(species.available_potions.values_list("pk", flat=True))
    if available and potion.pk not in available:
        raise OperationError(
            f"{species.name} cannot hatch from {potion.name} — "
            "species restricts available potions."
        )

    egg = ItemDefinition.objects.filter(
        item_type=ItemDefinition.ItemType.EGG, pet_species=species,
    ).first()
    if egg is None:
        raise OperationError(
            f"No EGG ItemDefinition wired to species={species_slug!r}. "
            "Run `loadrpgcontent` to author it."
        )
    potion_item = ItemDefinition.objects.filter(
        item_type=ItemDefinition.ItemType.POTION, potion_type=potion,
    ).first()
    if potion_item is None:
        raise OperationError(
            f"No POTION ItemDefinition wired to potion={potion_slug!r}. "
            "Run `loadrpgcontent` to author it."
        )

    for item in (egg, potion_item):
        inv, created = UserInventory.objects.get_or_create(
            user=user, item=item, defaults={"quantity": 1},
        )
        if not created:
            UserInventory.objects.filter(pk=inv.pk).update(
                quantity=F("quantity") + 1,
            )

    return {
        "egg": {"id": egg.pk, "slug": egg.slug, "name": egg.name},
        "potion": {"id": potion_item.pk, "slug": potion_item.slug, "name": potion_item.name},
    }


def clear_mount_breed_cooldowns(
    user, *, mount_id: int | None = None,
) -> dict[str, Any]:
    """Set ``last_bred_at = None`` on one mount or all of the user's mounts."""
    from apps.pets.models import UserMount

    qs = UserMount.objects.filter(user=user)
    if mount_id is not None:
        qs = qs.filter(pk=mount_id)
        if not qs.exists():
            raise OperationError("Mount not found in this user's stable.")

    count = qs.update(last_bred_at=None)
    return {"user": user.username, "mounts_reset": count}


def seed_companion_growth(
    user, *, ticks: int = 3, force_evolve: bool = False,
) -> dict[str, Any]:
    """Append ``ticks`` synthesized growth events to ``pending_companion_growth``."""
    from apps.pets.models import PetSpecies, UserPet
    from apps.rpg.models import CharacterProfile

    if not 1 <= ticks <= 10:
        raise OperationError("ticks must be between 1 and 10.")

    profile, _ = CharacterProfile.objects.get_or_create(user=user)

    # Prefer a real companion pet the user already has; fall back to
    # constructing a plausible entry from the seeded companion species.
    pet = (
        UserPet.objects
        .filter(user=user, species__slug="companion", evolved_to_mount=False)
        .select_related("species", "potion")
        .first()
    )
    species = pet.species if pet else (
        PetSpecies.objects.filter(slug="companion").first()
    )
    if species is None:
        raise OperationError(
            "No companion-species seed found — run `loadrpgcontent` first."
        )

    queue = list(profile.pending_companion_growth or [])
    has_evolve_event = False
    for idx in range(ticks):
        new_growth = (
            min(100, (pet.growth_points if pet else 0) + 5 * (idx + 1))
        )
        is_last = idx == ticks - 1
        evolved = bool(force_evolve and is_last)
        if evolved:
            new_growth = 100
            has_evolve_event = True
        entry = {
            "pet_id": pet.pk if pet else None,
            "growth_added": 5,
            "new_growth": new_growth,
            "evolved": evolved,
            "mount_id": None,
            "species_name": species.name,
            "species_slug": species.slug,
            "sprite_key": species.sprite_key,
            "potion_slug": (pet.potion.slug if pet else None),
            "source": "dev_tools",
        }
        queue.append(entry)

    profile.pending_companion_growth = queue
    profile.save(update_fields=["pending_companion_growth"])

    return {
        "user": user.username,
        "events_seeded": ticks,
        "has_evolve_event": has_evolve_event,
        "queue_length": len(queue),
    }


def mark_expedition_ready(
    user, *, mount_id: int | None = None, tier: str = "standard",
) -> dict[str, Any]:
    """Start an expedition for the user's mount and backdate so it reads ready."""
    from datetime import timedelta as _td

    from apps.pets.expeditions import (
        TIER_CONFIG, ExpeditionError, ExpeditionService,
    )
    from apps.pets.models import MountExpedition, UserMount

    if tier not in TIER_CONFIG:
        raise OperationError(
            f"Unknown tier={tier!r}. Use one of {sorted(TIER_CONFIG)}."
        )

    if mount_id is None:
        mount = (
            UserMount.objects
            .filter(user=user)
            .exclude(
                expeditions__status=MountExpedition.Status.ACTIVE,
            )
            .order_by("-is_active", "pk")
            .first()
        )
        if mount is None:
            raise OperationError(
                "User has no free mount available — evolve a pet first "
                "or pass an explicit mount_id."
            )
        mount_id = mount.pk

    try:
        expedition = ExpeditionService.start(user, mount_id, tier)
    except ExpeditionError as e:
        raise OperationError(str(e)) from e

    config = TIER_CONFIG[tier]
    backdate = timezone.now() - _td(minutes=config["duration_minutes"]) - _td(seconds=1)
    expedition.started_at = backdate
    expedition.returns_at = backdate + _td(minutes=config["duration_minutes"])
    expedition.save(update_fields=["started_at", "returns_at", "updated_at"])

    loot = expedition.loot or {}
    return {
        "expedition_id": expedition.pk,
        "mount_id": expedition.mount_id,
        "species_name": expedition.mount.species.name,
        "tier": tier,
        "ready_at": expedition.returns_at.isoformat(),
        "coins": loot.get("coins"),
        "item_count": len(loot.get("items") or []),
    }
