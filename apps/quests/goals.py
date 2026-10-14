"""Automatic, factual goal tracking. Reading or pinning never pays a reward."""
import hashlib
import json
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal,
    ChallengeOccurrence, ChallengePin, Quest, QuestDefinition,
)

DISTANCE_FACTORS = {"mi": Decimal("1609.344"), "km": Decimal("1000")}
FACT_TRIGGERS = {
    "clock_out", "chore_complete", "homework_complete", "homework_created",
    "milestone_complete", "project_complete", "habit_log", "journal_entry",
    "creation_logged", "movement_session", "savings_goal_complete",
    "expedition_returned",
}
EFFORT_TRIGGERS = FACT_TRIGGERS - {"expedition_returned"}
CONTEXT_KEYS = {
    "project_id", "skill_category_id", "chore_id", "savings_goal_id", "on_time",
    "movement_type_id", "duration_minutes", "hours", "distance_meters", "skill_tags",
}
ACTION_PATHS = {
    "clock_out": ("Track project work", "/quests?tab=ventures"),
    "chore_complete": ("View chores", "/quests?tab=duties"),
    "homework_complete": ("View homework", "/quests?tab=study"),
    "homework_created": ("Plan homework", "/quests?tab=study"),
    "habit_log": ("View habits", "/quests?tab=rituals"),
    "movement_session": ("Log movement", "/quests?tab=movement"),
    "journal_entry": ("Write in your journal", "/yearbook"),
    "creation_logged": ("Log a creation", "/quests?tab=creations"),
}
TRIGGER_LABELS = {
    "clock_out": "tracked project work", "chore_complete": "approved chores",
    "homework_complete": "approved homework", "homework_created": "planned homework",
    "milestone_complete": "completed milestones", "project_complete": "completed projects",
    "habit_log": "positive ritual taps", "movement_session": "movement sessions",
    "journal_entry": "journal entries", "creation_logged": "logged creations",
    "savings_goal_complete": "completed savings goals", "badge_earned": "earned badges",
    "perfect_day": "Perfect Days", "expedition_returned": "returned expeditions",
}


def lock_user(user):
    # Same first lock as AwardService; PostgreSQL FK key-share inserts remain safe.
    qs = get_user_model().objects.select_for_update(no_key=True)
    return qs.get(pk=user.pk)


def family_zone(user):
    name = user.family.timezone or "America/Phoenix"
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        return ZoneInfo("America/Phoenix")


def decimal_value(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("A valid numeric measurement is required")
    if not result.is_finite() or result < 0 or result > Decimal("9999999999999"):
        raise ValueError("Measurement must be finite and nonnegative")
    return result


def number(value):
    return format(Decimal(value).normalize(), "f")


def _progress_value(value):
    """Use the saved three-decimal precision before reward comparisons."""
    return Decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _contribution_total(occurrence):
    total = occurrence.contributions.filter(activity__voided=False).aggregate(total=Sum("amount"))["total"] or 0
    return _progress_value(total)


def _midnight(day, zone):
    return datetime.combine(day, time.min, tzinfo=zone)


def _snapshot(goal):
    from apps.rpg.models import ItemDefinition
    from apps.rpg.catalog_support import item_is_available
    items = []
    for row in goal.reward_items:
        item = ItemDefinition.objects.filter(pk=row["item_id"]).first()
        if item and item_is_available(item):
            items.append({**row, "item_name": item.name, "item_icon": item.icon, "item_sprite_key": item.sprite_key})
    return {
        "name": goal.name, "description": goal.description, "metric": goal.metric,
        "target": str(goal.target), "unit": goal.unit, "filter": goal.trigger_filter,
        "movement_type_id": goal.movement_type_id,
        "movement_type_name": goal.movement_type.name if goal.movement_type_id else None,
        "coins": goal.coin_reward, "xp": goal.xp_reward,
        "skill_tags": goal.skill_tags, "items": items,
        "catalog_name": goal.catalog_definition.name if goal.catalog_definition_id else None,
        "catalog_type": goal.catalog_definition.quest_type if goal.catalog_definition_id else None,
    }


def _first_pending_catalog_fact(user, definition, cutoff, offered_at):
    """Keep a saved initial action eligible even if evaluation or a GET wins later."""
    filters = definition.trigger_filter or {}
    allowed = set(filters.get("allowed_triggers") or EFFORT_TRIGGERS) & FACT_TRIGGERS
    query = ChallengeActivity.objects.filter(
        user=user, processed_at__isnull=True, voided=False, trigger_type__in=allowed,
        occurred_at__gte=cutoff, occurred_at__lte=offered_at,
    ).filter(~Q(trigger_type__in=["homework_created", "creation_logged"]) | Q(context__catalog_eligible=True))
    for key in ("project_id", "skill_category_id", "savings_goal_id"):
        if filters.get(key):
            query = query.filter(**{f"context__{key}": filters[key]})
    if filters.get("chore_ids"):
        query = query.filter(context__chore_id__in=filters["chore_ids"])
    if filters.get("on_time"):
        query = query.filter(context__on_time=True)
    snapshot = {"metric": "damage" if definition.quest_type == "boss" else "count",
                "filter": filters, "unit": "actions"}
    for activity in query.order_by("occurred_at", "pk").iterator(chunk_size=100):
        if _amount(snapshot, activity) > 0:
            return activity.occurred_at
    return None


def _catalog_goals(user):
    offered_at = timezone.now()
    enrollment = ChallengeEnrollment.objects.filter(user=user).first()
    if enrollment is None:
        first_pending = ChallengeActivity.objects.filter(
            user=user, processed_at__isnull=True, voided=False, occurred_at__lte=offered_at,
            trigger_type__in=FACT_TRIGGERS,
        ).order_by("occurred_at", "pk").values_list("occurred_at", flat=True).first()
        enrollment, _ = ChallengeEnrollment.objects.get_or_create(
            user=user, defaults={"starts_at": first_pending or offered_at, "timezone_name": str(family_zone(user))},
        )
    # A historical active quest remains the pinned legacy instance through its deadline.
    pin, new_pin = ChallengePin.objects.get_or_create(user=user)
    if new_pin:
        legacy = Quest.objects.filter(participants__user=user, status="active").first()
        if legacy:
            pin.legacy_quest = legacy
            pin.save(update_fields=["legacy_quest", "updated_at"])
    if user.role != "child":
        return
    existing_ids = set(ChallengeGoal.objects.filter(user=user).values_list("catalog_definition_id", flat=True))
    definitions = QuestDefinition.objects.filter(is_system=True).prefetch_related(
        "skill_tags__skill", "reward_items__item",
    )
    from apps.achievements.models import UserBadge
    earned = set(UserBadge.objects.filter(user=user).values_list("badge_id", flat=True))
    for definition in definitions:
        if definition.pk in existing_ids or (definition.required_badge_id and definition.required_badge_id not in earned):
            continue
        allowed = (definition.trigger_filter or {}).get("allowed_triggers")
        if allowed and not any(trigger in FACT_TRIGGERS for trigger in allowed):
            continue
        legacy = Quest.objects.filter(definition=definition, participants__user=user)
        if not definition.is_repeatable and legacy.filter(status__in=["active", "completed"]).exists():
            continue
        active = legacy.filter(status="active").first()
        cutoff = max(enrollment.starts_at, definition.created_at)
        if active:
            cutoff = max(cutoff, active.end_date)
        if definition.required_badge_id:
            # Unlocking never retroactively counts facts from before the badge was earned.
            cutoff = max(cutoff, UserBadge.objects.get(user=user, badge_id=definition.required_badge_id).earned_at)
        first_fact = _first_pending_catalog_fact(user, definition, cutoff, offered_at)
        starts_at = max(cutoff, first_fact or offered_at)
        ChallengeGoal.objects.get_or_create(user=user, catalog_definition=definition, defaults={
            "is_catalog": True, "family": user.family, "name": definition.name, "description": definition.description,
            "metric": "damage" if definition.quest_type == "boss" else "count",
            "target": definition.target_value, "unit": "damage" if definition.quest_type == "boss" else "actions",
            "trigger_filter": definition.trigger_filter, "timezone_name": enrollment.timezone_name,
            "starts_at": starts_at, "ends_at": starts_at + timedelta(days=definition.duration_days),
            "repeat_days": definition.duration_days if definition.is_repeatable else 0,
            "coin_reward": definition.coin_reward, "xp_reward": definition.xp_reward,
            "skill_tags": [{"skill_id": tag.skill_id, "xp_weight": tag.xp_weight} for tag in definition.skill_tags.all()],
            "reward_items": [{"item_id": reward.item_id, "quantity": reward.quantity} for reward in definition.reward_items.all()],
        })


def _occurrence(goal, at):
    retired = goal.is_catalog and (
        goal.catalog_definition_id is None
        or not ChallengeGoal.objects.filter(pk=goal.pk, catalog_definition__isnull=False).exists()
    )
    if retired:
        # Retirement retains saved promises and history, without new cycles.
        return goal.occurrences.filter(starts_at__lte=at, ends_at__gt=at).first()
    if at < goal.starts_at:
        return None
    start, end = goal.starts_at, goal.ends_at
    if goal.repeat_weekly:
        zone = ZoneInfo(goal.timezone_name)
        day = at.astimezone(zone).date()
        monday = day - timedelta(days=day.weekday())
        start, end = _midnight(monday, zone), _midnight(monday + timedelta(days=7), zone)
    elif goal.repeat_days:
        zone = ZoneInfo(goal.timezone_name)
        # Calendar-day arithmetic retains the household clock across DST changes.
        local_start, local_at = start.astimezone(zone), at.astimezone(zone)
        elapsed = (local_at.replace(tzinfo=None) - local_start.replace(tzinfo=None)).total_seconds()
        cycle = int(elapsed // (goal.repeat_days * 86400))
        start = local_start + timedelta(days=cycle * goal.repeat_days)
        end = start + timedelta(days=goal.repeat_days)
    occurrence, _ = ChallengeOccurrence.objects.get_or_create(
        goal=goal, starts_at=start, defaults={"ends_at": end, "snapshot": _snapshot(goal)},
    )
    return occurrence


def _amount(snapshot, activity):
    context, trigger = activity.context, activity.trigger_type
    filters = snapshot.get("filter", {})
    allowed = filters.get("allowed_triggers")
    if allowed and trigger not in allowed:
        return Decimal(0)
    if not allowed and trigger not in EFFORT_TRIGGERS:
        return Decimal(0)
    for key in ("project_id", "skill_category_id", "savings_goal_id"):
        if filters.get(key) and filters[key] != context.get(key):
            return Decimal(0)
    if filters.get("chore_ids") and context.get("chore_id") not in filters["chore_ids"]:
        return Decimal(0)
    if filters.get("on_time") and not context.get("on_time"):
        return Decimal(0)
    if snapshot.get("movement_type_id") and context.get("movement_type_id") != snapshot["movement_type_id"]:
        return Decimal(0)
    metric = snapshot["metric"]
    if metric == "count":
        amount = Decimal(1)
    elif metric == "minutes":
        amount = decimal_value(context.get("duration_minutes", 0))
    elif metric == "distance":
        amount = decimal_value(context.get("distance_meters") or 0) / DISTANCE_FACTORS[snapshot["unit"]]
    else:
        from .services import TRIGGER_DAMAGE
        amount = Decimal(TRIGGER_DAMAGE.get(trigger, 0))
        if trigger == "clock_out":
            amount = (amount * decimal_value(context.get("duration_minutes", 0)) / 60).to_integral_value(rounding="ROUND_FLOOR")
    return _progress_value(amount)


def _award(occurrence, user):
    if occurrence.awarded_at:
        return occurrence.reward_receipt
    from apps.achievements.models import Skill
    from apps.achievements.services import AwardService
    from apps.rpg.catalog_support import item_is_available
    from apps.rpg.models import ItemDefinition, UserInventory
    from apps.pets.models import UserMount
    from apps.rewards.services import CoinService
    snapshot = occurrence.snapshot
    rows = snapshot.get("skill_tags", [])
    skills = Skill.objects.in_bulk([row["skill_id"] for row in rows])
    tags = [SimpleNamespace(skill=skills[row["skill_id"]], xp_weight=row["xp_weight"])
            for row in rows if row["skill_id"] in skills]
    xp = snapshot["xp"] if tags else 0
    # Completed status is visible to badge criteria inside the same transaction.
    occurrence.status = "completed"
    occurrence.completed_at = timezone.now()
    occurrence.save(update_fields=["status", "completed_at", "updated_at"])
    grant = AwardService.grant(
        user, xp_tags=tags, xp=xp, coins=snapshot["coins"], coin_reason="adjustment",
        coin_description=f"Challenge complete: {snapshot['name']}",
        xp_source_label=f"Challenge: {snapshot['name']}", badge_scopes={"quest", "coin", "skill_xp", "badges"},
    )
    actual_xp = grant["xp_awarded"]
    coins, items = snapshot["coins"], []
    for row in snapshot.get("items", []):
        item = ItemDefinition.objects.filter(pk=row["item_id"]).first()
        if not item or not item_is_available(item):
            continue
        quantity = row["quantity"]
        if item.item_type == "egg" and item.pet_species_id and UserMount.objects.filter(user=user, species_id=item.pet_species_id).exists() and item.coin_value > 0:
            salvage = item.coin_value * quantity
            CoinService.award_coins(user, salvage, "adjustment", description=f"Challenge egg salvage: {item.name}")
            coins += salvage
            items.append({"item_name": item.name, "quantity": quantity, "salvaged_to_coins": salvage})
        else:
            inv, _ = UserInventory.objects.get_or_create(user=user, item=item, defaults={"quantity": 0})
            inv.quantity += quantity
            inv.save(update_fields=["quantity", "updated_at"])
            items.append({"item_name": item.name, "quantity": quantity})
    receipt = {"coins": coins, "xp": actual_xp, "items": items}
    occurrence.awarded_at = timezone.now()
    occurrence.reward_receipt = receipt
    occurrence.save(update_fields=["awarded_at", "reward_receipt", "updated_at"])
    return receipt


def _process(activity):
    user = activity.user
    _catalog_goals(user)
    receipts = []
    if activity.voided:
        return receipts
    for goal in ChallengeGoal.objects.filter(user=user, family_id=user.family_id).select_related("movement_type", "catalog_definition").order_by("pk"):
        if (goal.is_catalog and activity.trigger_type in {"homework_created", "creation_logged"}
                and activity.context.get("catalog_eligible") is not True):
            continue
        at = activity.occurred_at
        if goal.repeat_weekly or (not goal.is_catalog and goal.starts_at.astimezone(ZoneInfo(goal.timezone_name)).time() == time.min):
            # A late approval belongs to the recorded work day, not today's week.
            at = datetime.combine(activity.occurred_on, time(12), tzinfo=ZoneInfo(goal.timezone_name))
        occurrence = _occurrence(goal, at)
        if not occurrence or at >= occurrence.ends_at or occurrence.awarded_at:
            continue
        amount = _amount(occurrence.snapshot, activity)
        if amount <= 0:
            continue
        _, created = ChallengeContribution.objects.get_or_create(
            occurrence=occurrence, activity=activity, defaults={"amount": amount},
        )
        if not created:
            continue
        occurrence.progress = _contribution_total(occurrence)
        rewards = None
        if occurrence.progress >= Decimal(occurrence.snapshot["target"]):
            rewards = _award(occurrence, user)
        occurrence.save(update_fields=["progress", "updated_at"])
        receipts.append({
            "id": f"goal:{occurrence.pk}", "name": occurrence.snapshot["name"],
            "progress": number(occurrence.progress), "target": number(occurrence.snapshot["target"]),
            "unit": occurrence.snapshot["unit"], "completed": occurrence.status == "completed", "rewards": rewards,
        })
    activity.processed_at = timezone.now()
    activity.save(update_fields=["processed_at", "updated_at"])
    return receipts


def ingest_activity(user, source_type, source_id, trigger_type, occurred_at=None, occurred_on=None, context=None):
    """Persist a source fact, then evaluate it. A failed evaluation stays retryable."""
    if str(trigger_type) not in FACT_TRIGGERS:
        return {"activity": None, "goals": []}
    if not source_type or source_id is None or not str(source_id):
        raise ValueError("A durable source identity is required")
    zone = family_zone(user)
    at = occurred_at or (_midnight(occurred_on, zone) if occurred_on else timezone.now())
    if timezone.is_naive(at):
        at = timezone.make_aware(at, zone)
    day = occurred_on or at.astimezone(zone).date()
    safe_context = {key: value for key, value in (context or {}).items() if key in CONTEXT_KEYS}
    for key in ("duration_minutes", "hours", "distance_meters"):
        if key in safe_context and safe_context[key] is not None:
            safe_context[key] = str(decimal_value(safe_context[key]))
    with transaction.atomic():
        lock_user(user)
        # Enrollment must precede the first fact so that fact counts in catalog windows.
        ChallengeEnrollment.objects.get_or_create(user=user, defaults={"starts_at": at, "timezone_name": str(zone)})
        activity, _ = ChallengeActivity.objects.get_or_create(
            user=user, source_type=source_type, source_id=str(source_id), trigger_type=str(trigger_type),
            defaults={"occurred_at": at, "occurred_on": day, "context": safe_context},
        )
    with transaction.atomic():
        lock_user(user)
        activity = ChallengeActivity.objects.select_related("user__family").select_for_update().get(pk=activity.pk)
        if activity.processed_at or activity.voided:
            return {"activity": activity, "goals": []}
        return {"activity": activity, "goals": _process(activity)}


@transaction.atomic
def void_activity(user, source_type, source_id):
    """Remove unpaid factual contributions; a settled occurrence never pays again."""
    lock_user(user)
    facts = ChallengeActivity.objects.filter(user=user, source_type=source_type, source_id=str(source_id))
    occurrences = ChallengeOccurrence.objects.filter(contributions__activity__in=facts).distinct()
    facts.update(voided=True)
    for occurrence in occurrences:
        if occurrence.awarded_at:
            continue
        occurrence.progress = _contribution_total(occurrence)
        occurrence.save(update_fields=["progress", "updated_at"])


@transaction.atomic
def create_goal(parent, child, data):
    if parent.role != "parent" or child.role != "child" or child.family_id != parent.family_id:
        raise ValueError("Child not found")
    # Parent serializes request UUIDs; deterministic order also covers two targets.
    for member in sorted([parent, child], key=lambda member: member.pk):
        lock_user(member)
    fingerprint = hashlib.sha256(json.dumps(
        {key: value for key, value in data.items() if key != "request_id"}, sort_keys=True, default=str,
    ).encode()).hexdigest()
    request_id = data.get("request_id")
    if request_id:
        previous = ChallengeGoal.objects.filter(created_by=parent, request_id=request_id).first()
        if previous:
            if previous.request_fingerprint != fingerprint:
                raise ValueError("request_id was already used for different goal details")
            return previous.occurrences.order_by("starts_at").first()
    zone, today = family_zone(child), timezone.localtime(timezone.now(), family_zone(child)).date()
    if data["period"] == "this_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    elif data["period"] == "from_today":
        start, end = today, today + timedelta(days=7)
    else:
        start, end = data["start_date"], data["end_date"] + timedelta(days=1)
    starts_at = _midnight(start, zone)
    ends_at = _midnight(end, zone)
    if data["period"] == "from_today":
        starts_at = timezone.localtime(timezone.now(), zone)
        ends_at = starts_at + timedelta(days=7)
    goal = ChallengeGoal.objects.create(
        user=child, family=parent.family, created_by=parent, name=data["name"],
        description=data.get("description", ""), metric=data["metric"], target=data["target"],
        unit=data["unit"], trigger_filter={"allowed_triggers": [data["trigger_type"]]},
        movement_type_id=data.get("movement_type_id"), timezone_name=str(zone),
        starts_at=starts_at, ends_at=ends_at,
        repeat_weekly=data.get("repeat_weekly", False), coin_reward=data.get("coin_reward", 0),
        xp_reward=data.get("xp_reward", 0), skill_tags=data.get("skill_tags", []),
        request_id=request_id, request_fingerprint=fingerprint if request_id else "",
    )
    occurrence = _occurrence(goal, goal.starts_at)
    if data["period"] == "this_week":
        from .activity import backfill_goal_activity
        backfill_goal_activity(goal)
    # Explicit midweek assignment includes earlier facts from that same window.
    # Migration/catalog enrollment never backfills historical facts or awards.
    facts = ChallengeActivity.objects.filter(user=child, voided=False)
    if data["period"] in {"this_week", "custom"}:
        facts = facts.filter(occurred_on__gte=start, occurred_on__lt=end)
    else:
        facts = facts.filter(occurred_at__gte=goal.starts_at, occurred_at__lt=goal.ends_at)
    for activity in facts:
        amount = _amount(occurrence.snapshot, activity)
        if amount > 0:
            ChallengeContribution.objects.get_or_create(occurrence=occurrence, activity=activity, defaults={"amount": amount})
    occurrence.progress = _contribution_total(occurrence)
    if occurrence.progress >= goal.target:
        _award(occurrence, child)
    occurrence.save(update_fields=["progress", "updated_at"])
    return occurrence


def _what_counts(snapshot, *, catalog=False):
    allowed = snapshot.get("filter", {}).get("allowed_triggers") or sorted(EFFORT_TRIGGERS)
    if snapshot.get("metric") == "damage":
        from .services import TRIGGER_DAMAGE
        allowed = [trigger for trigger in allowed if TRIGGER_DAMAGE.get(trigger, 0) > 0]
    labels = {**TRIGGER_LABELS}
    if catalog:
        labels.update({"homework_created": "planned homework (first per day)",
                       "creation_logged": "logged creations (first two per day)"})
    text = ", ".join(labels.get(trigger, trigger.replace("_", " ")) for trigger in allowed)
    if snapshot.get("movement_type_name"):
        text = f"{snapshot['movement_type_name']} sessions"
    if snapshot.get("filter", {}).get("on_time"):
        text += " submitted on time"
    return text


def _reward_preview(snapshot):
    """Current acquisition policy controls previews without rewriting saved IDs."""
    from apps.rpg.catalog_support import item_is_available
    from apps.rpg.models import ItemDefinition
    rows = snapshot.get("items", [])
    catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(
        [row["item_id"] for row in rows],
    )
    available = []
    for row in rows:
        item = catalog.get(row["item_id"])
        if item is not None and item_is_available(item):
            available.append({**row, "item_name": item.name, "item_icon": item.icon, "item_sprite_key": item.sprite_key})
    return available


def occurrence_payload(occurrence, pin_id=None):
    snapshot = occurrence.snapshot
    allowed = snapshot.get("filter", {}).get("allowed_triggers") or []
    action = None
    if len(allowed) == 1 and allowed[0] in ACTION_PATHS:
        label, path = ACTION_PATHS[allowed[0]]
        action = {"label": label, "path": path}
        if snapshot.get("movement_type_id"):
            action["movement_type_id"] = snapshot["movement_type_id"]
            if allowed[0] == "movement_session":
                action["path"] = f"{path}&log=1&movement_type={snapshot['movement_type_id']}"
    status = occurrence.status
    if status == "active":
        if timezone.now() < occurrence.starts_at:
            status = "upcoming"
        elif timezone.now() >= occurrence.ends_at:
            status = "expired"
    receipt = occurrence.reward_receipt
    return {
        "id": f"goal:{occurrence.pk}", "name": snapshot["name"], "description": snapshot["description"],
        "metric": snapshot["metric"], "target": number(snapshot["target"]), "progress": number(occurrence.progress),
        "unit": snapshot["unit"], "status": status,
        "starts_at": occurrence.starts_at.isoformat(), "ends_at": occurrence.ends_at.isoformat(),
        "timezone": occurrence.goal.timezone_name,
        "what_counts": _what_counts(snapshot, catalog=occurrence.goal.is_catalog), "rewards": {"coins": snapshot["coins"], "xp": snapshot["xp"], "items": _reward_preview(snapshot)},
        "action": action, "pinned": pin_id == f"goal:{occurrence.pk}", "repeat_weekly": occurrence.goal.repeat_weekly,
        "legacy": False, "reward_receipt": {"id": f"goal:{occurrence.pk}", "status": "awarded" if occurrence.awarded_at else "pending",
            "coins_awarded": receipt.get("coins", 0), "xp_awarded": receipt.get("xp", 0),
            "awarded_at": occurrence.awarded_at.isoformat() if occurrence.awarded_at else None,
            **({"items": receipt.get("items", [])} if occurrence.awarded_at else {})},
    }


def _pin_id(pin):
    if pin.occurrence_id:
        return f"goal:{pin.occurrence_id}"
    if pin.legacy_quest_id:
        return f"legacy:{pin.legacy_quest_id}"
    return None


def _legacy_payload(quest, pin_id):
    definition = quest.definition
    key = f"legacy:{quest.pk}"
    from .serializers import QuestRewardItemSerializer
    from apps.rpg.catalog_support import item_is_available
    items = QuestRewardItemSerializer([row for row in definition.reward_items.select_related("item") if item_is_available(row.item)], many=True).data
    return {
        "id": key, "name": definition.name, "description": definition.description,
        "metric": "damage" if definition.quest_type == "boss" else "count", "target": str(quest.effective_target),
        "progress": str(quest.current_progress), "unit": "damage" if definition.quest_type == "boss" else "actions",
        "status": "expired" if quest.is_expired else quest.status,
        "starts_at": quest.start_date.isoformat(), "ends_at": quest.end_date.isoformat(),
        "what_counts": _what_counts({"filter": definition.trigger_filter}),
        "rewards": {"coins": definition.coin_reward, "xp": definition.xp_reward, "items": items},
        "action": None, "pinned": pin_id == key, "repeat_weekly": False, "legacy": True,
        "rage_shield": quest.rage_shield, "participants": [
            {"user": participant.user_id, "user_name": participant.user.display_label, "contribution": participant.contribution}
            for participant in quest.participants.select_related("user")
        ],
        "reward_receipt": {"id": key, "status": "legacy", "coins_awarded": 0, "xp_awarded": 0, "awarded_at": None},
    }


@transaction.atomic
def list_goals(user):
    lock_user(user)
    _catalog_goals(user)
    now = timezone.now()
    current = {}
    for goal in ChallengeGoal.objects.filter(user=user, family_id=user.family_id).select_related("movement_type", "catalog_definition"):
        occurrence = _occurrence(goal, now)
        if occurrence is not None:
            current[goal.pk] = occurrence
    pin = ChallengePin.objects.get(user=user)
    if pin.occurrence_id:
        previous = pin.occurrence
        if previous.goal.repeat_weekly or previous.goal.repeat_days:
            successor = current.get(previous.goal_id)
            if successor is not None and successor.pk != previous.pk:
                # The preference follows the same goal, independently of its window.
                pin.occurrence = successor
                pin.save(update_fields=["occurrence", "updated_at"])
    pin_id = _pin_id(pin)
    occurrences = ChallengeOccurrence.objects.filter(goal__user=user, goal__family_id=user.family_id).select_related("goal")
    active = list(occurrences.filter(starts_at__lte=now, ends_at__gt=now))
    recent = list(occurrences.filter(awarded_at__isnull=False).order_by("-awarded_at", "-pk")[:20])
    terminal = list(occurrences.filter(ends_at__lte=now).order_by("-ends_at", "-pk")[:20])
    future = list(occurrences.filter(starts_at__gt=now, goal__is_catalog=False))
    unique = {row.pk: row for row in active + recent + terminal + future}
    if pin.occurrence_id:
        pinned = occurrences.filter(pk=pin.occurrence_id).first()
        if pinned:
            unique[pinned.pk] = pinned
    legacy = Quest.objects.filter(participants__user=user).select_related("definition")
    rows = [occurrence_payload(row, pin_id) for row in unique.values()]
    rows += [_legacy_payload(row, pin_id) for row in legacy.filter(status="active")]
    rows += [_legacy_payload(row, pin_id) for row in legacy.exclude(status="active")[:20]]
    receipts = ChallengeActivity.objects.filter(user=user, voided=False, context__has_key="_receipt").order_by("-created_at", "-pk")[:20]
    return {"results": rows, "pin": pin_id, "recent_receipts": [occurrence_payload(row, pin_id) for row in recent],
            "challenge_receipts": [activity.context["_receipt"] for activity in receipts]}


@transaction.atomic
def set_pin(user, goal_id, clear=False):
    lock_user(user)
    try:
        kind, raw_id = goal_id.split(":", 1)
        pk = int(raw_id)
    except (ValueError, AttributeError):
        raise ValueError("Challenge not found")
    occurrence, legacy = None, None
    if kind == "goal":
        occurrence = ChallengeOccurrence.objects.filter(pk=pk, goal__user=user, goal__family_id=user.family_id).first()
    elif kind == "legacy":
        legacy = Quest.objects.filter(pk=pk, participants__user=user).first()
    if occurrence is None and legacy is None:
        raise ValueError("Challenge not found")
    pin, _ = ChallengePin.objects.get_or_create(user=user)
    if clear:
        same_recurring_goal = (
            occurrence is not None and pin.occurrence_id is not None
            and occurrence.goal_id == pin.occurrence.goal_id
            and (occurrence.goal.repeat_weekly or occurrence.goal.repeat_days)
        )
        if _pin_id(pin) == goal_id or same_recurring_goal:
            pin.occurrence = pin.legacy_quest = None
    else:
        pin.occurrence, pin.legacy_quest = occurrence, legacy
    pin.save(update_fields=["occurrence", "legacy_quest", "updated_at"])
    return {"pin": _pin_id(pin)}
