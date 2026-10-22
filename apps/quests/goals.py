"""Automatic, factual goal tracking. Reading or pinning never pays a reward."""
import hashlib
import json
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Prefetch, Q, Sum, prefetch_related_objects
from django.utils import timezone
from apps.rpg.catalog_icons import challenge_catalog_icon

from .models import (
    ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal,
    ChallengeOccurrence, ChallengePin, Quest, QuestDefinition, QuestParticipant, QuestRewardItem,
)
from .queries import active_system_definitions

DISTANCE_FACTORS = {"mi": Decimal("1609.344"), "km": Decimal("1000")}
FACT_TRIGGERS = {
    "clock_out", "chore_complete", "homework_complete", "homework_created",
    "milestone_complete", "project_complete", "habit_log", "journal_entry",
    "creation_logged", "movement_session", "savings_goal_complete",
    "expedition_returned", "reading_logged",
}
# Reading has its own once-daily receipt and explicit reading goals. Existing
# unfiltered promises keep their original qualifying activities and pacing.
EFFORT_TRIGGERS = FACT_TRIGGERS - {"expedition_returned", "reading_logged"}
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
    "reading_logged": ("Read for ten minutes", "/quests?tab=reading"),
}
TRIGGER_LABELS = {
    "clock_out": "tracked project work", "chore_complete": "approved chores",
    "homework_complete": "approved homework", "homework_created": "planned homework",
    "milestone_complete": "completed milestones", "project_complete": "completed projects",
    "habit_log": "positive habit taps", "movement_session": "movement sessions",
    "journal_entry": "journal entries", "creation_logged": "logged creations",
    "savings_goal_complete": "completed savings goals", "badge_earned": "earned badges",
    "perfect_day": "Perfect Days", "expedition_returned": "returned expeditions",
    "reading_logged": "daily Reading Adventures (ten newly logged minutes, once per day)",
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


def _snapshot(goal, item_catalog=None):
    from apps.rpg.models import ItemDefinition
    from apps.rpg.catalog_support import item_is_available
    from .reward_items import reward_item_details
    items = []
    catalog = item_catalog if item_catalog is not None else ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(
        [row["item_id"] for row in goal.reward_items],
    )
    for row in goal.reward_items:
        item = catalog.get(row["item_id"])
        if item and item_is_available(item):
            items.append({**row, **reward_item_details(item)})
    return {
        "name": goal.name, "description": goal.description, "metric": goal.metric,
        "target": str(goal.target), "unit": goal.unit, "filter": goal.trigger_filter,
        "movement_type_id": goal.movement_type_id,
        "movement_type_name": goal.movement_type.name if goal.movement_type_id else None,
        "coins": goal.coin_reward, "xp": goal.xp_reward,
        "skill_tags": goal.skill_tags, "items": items,
        "catalog_name": goal.catalog_definition.name if goal.catalog_definition_id else None,
        "catalog_type": goal.catalog_definition.quest_type if goal.catalog_definition_id else None,
        **({"catalog_gate": {**goal.catalog_gate_snapshot,
                              "opening_activity_id": goal.catalog_gate_activity_id}}
           if goal.catalog_gate_snapshot else {}),
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


def _catalog_goals(user, *, gate_activity=None, gated_only=False):
    offered_at = timezone.now()
    enrollment = ChallengeEnrollment.objects.filter(user=user).first()
    if enrollment is None:
        first_pending = ChallengeActivity.objects.filter(
            user=user, processed_at__isnull=True, voided=False, occurred_at__lte=offered_at,
            trigger_type__in=FACT_TRIGGERS,
        ).order_by("occurred_at", "pk").values_list("occurred_at", flat=True).first()
        enrollment, _ = ChallengeEnrollment.objects.get_or_create(
            user=user, defaults={"starts_at": first_pending or offered_at, "timezone_name": str(family_zone(user)),
                                 "discovery_tracking_started_at": offered_at},
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
    existing_ids.update(QuestDefinition.objects.filter(pk__in=existing_ids).exclude(
        superseded_by__isnull=True,
    ).values_list("superseded_by_id", flat=True))
    queryset = active_system_definitions().filter(is_cooperative=False).exclude(pk__in=existing_ids)
    if gated_only:
        queryset = queryset.filter(Q(prerequisite_quest__isnull=False) | Q(required_skill__isnull=False)
                                   | Q(required_skill_level__gt=0))
    definitions = list(queryset.select_related("prerequisite_quest", "required_skill", "required_badge").prefetch_related(
        "skill_tags__skill", "reward_items__item__pet_species__available_potions", "reward_items__item__potion_type",
    ))
    from .availability import definition_is_available
    from .milestone_eligibility import (
        gate_snapshot, has_milestone_gate, milestone_eligibility, prerequisite_completion,
    )
    from apps.achievements.models import UserBadge
    earned = dict(UserBadge.objects.filter(user=user).values_list("badge_id", "earned_at"))
    # Legacy catalog promises can suppress enrollment on every read. Resolve
    # their status and latest active deadline once for all pending definitions.
    legacy_statuses, active_deadlines = set(), {}
    canonical_ids = {definition.pk for definition in definitions}
    legacy_ids = {pk: pk for pk in canonical_ids}
    legacy_ids.update(QuestDefinition.objects.filter(superseded_by_id__in=canonical_ids).values_list(
        "pk", "superseded_by_id",
    ))
    for definition_id, status, end_date in Quest.objects.filter(
        participants__user=user, definition_id__in=legacy_ids,
    ).values_list("definition_id", "status", "end_date"):
        canonical_id = legacy_ids[definition_id]
        legacy_statuses.add((canonical_id, status))
        if status == "active":
            active_deadlines[canonical_id] = max(active_deadlines.get(canonical_id, end_date), end_date)
    for definition in definitions:
        if not definition_is_available(definition):
            continue
        gated = has_milestone_gate(definition)
        if gated and any(definition_id == definition.pk for definition_id, _ in legacy_statuses):
            continue  # A one-time accepted legacy window is not a fresh offer.
        # Reads and retries cannot accept a milestone offer or start its clock.
        # This boundary was captured under the user lock before the fresh fact
        # could complete a predecessor or earn its completion rewards.
        if gated and (gate_activity is None or not milestone_eligibility(user, definition)["unlocked"]):
            continue
        if definition.required_badge_id and definition.required_badge_id not in earned:
            continue
        allowed = (definition.trigger_filter or {}).get("allowed_triggers")
        if allowed and not any(trigger in FACT_TRIGGERS for trigger in allowed):
            continue
        if not definition.is_repeatable and any(
            (definition.pk, status) in legacy_statuses for status in ("active", "completed")
        ):
            continue
        from .reference_locks import admit_definition_choices, admit_definition_identity
        try:
            admit_definition_choices(definition)
            admit_definition_identity(definition)
        except ValueError:
            # Only a new promise needs fresh choice admission. Saved legacy
            # windows and existing goals retain their reward references.
            continue
        active_deadline = active_deadlines.get(definition.pk)
        cutoff = max(enrollment.starts_at, definition.created_at)
        if active_deadline:
            cutoff = max(cutoff, active_deadline)
        if definition.required_badge_id:
            # Unlocking never retroactively counts facts from before the badge was earned.
            cutoff = max(cutoff, earned[definition.required_badge_id])
        if gated:
            if (gate_activity.voided or (gate_activity.trigger_type in {"homework_created", "creation_logged"}
                    and gate_activity.context.get("catalog_eligible") is not True)):
                continue
            matching = {"metric": "damage" if definition.quest_type == "boss" else "count",
                        "filter": definition.trigger_filter, "unit": "actions"}
            if _amount(matching, gate_activity) <= 0:
                continue
            if definition.prerequisite_quest_id:
                _, completed_at = prerequisite_completion(user, definition.prerequisite_quest_id)
                if completed_at:
                    cutoff = max(cutoff, completed_at)
            first_fact = gate_activity.occurred_at
            if first_fact < cutoff or first_fact > offered_at:
                continue
        else:
            first_fact = _first_pending_catalog_fact(user, definition, cutoff, offered_at)
        starts_at = max(cutoff, first_fact or offered_at)
        goal, created = ChallengeGoal.objects.get_or_create(user=user, catalog_definition=definition, defaults={
            "is_catalog": True, "family": user.family, "name": definition.name, "description": definition.description,
            "metric": "damage" if definition.quest_type == "boss" else "count",
            "target": definition.target_value, "unit": "damage" if definition.quest_type == "boss" else "actions",
            "trigger_filter": definition.trigger_filter, "timezone_name": enrollment.timezone_name,
            "starts_at": starts_at, "ends_at": (starts_at + timedelta(days=definition.duration_days)
                                                  if definition.duration_days is not None else None),
            "repeat_days": definition.duration_days if definition.is_repeatable else 0,
            "coin_reward": definition.coin_reward, "xp_reward": definition.xp_reward,
            "skill_tags": [{"skill_id": tag.skill_id, "xp_weight": tag.xp_weight} for tag in definition.skill_tags.all()],
            "reward_items": [{"item_id": reward.item_id, "quantity": reward.quantity} for reward in definition.reward_items.all()],
            "catalog_gate_snapshot": gate_snapshot(definition) if gated else {},
            "catalog_gate_activity_id": gate_activity.pk if gated else None,
        })
        if gated and created:
            _occurrence(goal, starts_at)


def _occurrence_window(goal, at):
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
    return start, end


def _occurrence(goal, at):
    # Only list_goals supplies these freshly read windows. Other callers still
    # recheck retirement, including goals loaded before catalog maintenance.
    saved = getattr(goal, "_listed_occurrences", None)
    if goal.is_catalog and not goal.repeat_weekly and not goal.repeat_days:
        current = (next((row for row in saved if row.starts_at <= at
                         and (row.ends_at is None or at < row.ends_at)), None)
                   if saved is not None else goal.occurrences.filter(starts_at__lte=at).filter(
                       Q(ends_at__gt=at) | Q(ends_at__isnull=True)).first())
        if current is not None:
            return current
        if (any(row.retry_of_id for row in saved) if saved is not None
                else goal.occurrences.filter(retry_of__isnull=False).exists()):
            return None
    if saved is not None:
        if goal.is_catalog and goal.catalog_definition_id is None:
            return next((row for row in saved if row.starts_at <= at
                         and (row.ends_at is None or at < row.ends_at)), None)
        if at < goal.starts_at:
            return None
        start, _ = _occurrence_window(goal, at)
        existing = next((row for row in saved if row.starts_at == start), None)
        if existing is not None:
            return existing
    retired = goal.is_catalog and (
        goal.catalog_definition_id is None
        or not ChallengeGoal.objects.filter(
            pk=goal.pk, catalog_definition__isnull=False,
            catalog_definition__superseded_by__isnull=True, catalog_definition__is_cooperative=False,
        ).exists()
    )
    if retired:
        # Retirement retains saved promises and history, without new cycles.
        return goal.occurrences.filter(starts_at__lte=at).filter(Q(ends_at__gt=at) | Q(ends_at__isnull=True)).first()
    if at < goal.starts_at:
        return None
    start, end = _occurrence_window(goal, at)
    if goal.repeat_weekly:
        existing = goal.occurrences.filter(starts_at=start).first()
        if existing is not None:
            return existing
        from .controls import effective_setup
        snapshot, paused = effective_setup(goal, start)
        if paused:
            return None
    else:
        existing = goal.occurrences.filter(starts_at=start).first()
        if existing is not None:
            return existing
        snapshot = _snapshot(goal)
    # These references belong to an accepted standing rule or schedule version,
    # not a fresh taxonomy choice. Creation/enrollment and future setup edits
    # admit new references under their write locks. Rechecking here would cancel
    # recurring rewards after retirement (or a historical JSON skill deletion).
    # Payout retains saved IDs and skips missing skills without inventing XP.
    occurrence, _ = ChallengeOccurrence.objects.get_or_create(
        goal=goal, starts_at=start, defaults={"ends_at": end, "snapshot": snapshot or (lambda: _snapshot(goal))},
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
    from .controls import close_unpaid_attempts, lifetime_context, lifetime_paid
    lifetime = lifetime_context(occurrence, user)
    if lifetime is not None and lifetime_paid(occurrence, lifetime):
        close_unpaid_attempts(occurrence, lifetime, include_current=True)
        occurrence.status = "closed"
        occurrence.closed_reason = "reward_already_awarded"
        return None
    from apps.achievements.models import Skill
    from apps.achievements.services import AwardService
    from apps.rpg.models import ItemDefinition
    from apps.rpg.inventory import grant_item
    from apps.rewards.services import CoinService
    from .reward_items import egg_reward_is_duplicate, reward_item_details
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
    catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(
        [row["item_id"] for row in snapshot.get("items", [])],
    )
    for row in snapshot.get("items", []):
        item = catalog.get(row["item_id"])
        # This server-owned snapshot was validated when the window opened.
        if not item:
            continue
        quantity = row["quantity"]
        details = {"item_id": item.pk, **reward_item_details(item, snapshot=row), "quantity": quantity}
        if item.coin_value > 0 and egg_reward_is_duplicate(user, item, catalog.values()):
            salvage = item.coin_value * quantity
            CoinService.award_coins(user, salvage, "adjustment", description=f"Challenge egg salvage: {item.display_name}")
            coins += salvage
            items.append({**details, "salvaged_to_coins": salvage})
        else:
            grant_item(user, item, quantity)
            items.append(details)
    # The occurrence's existing payout marker and account lock cover this
    # bonus too. Keep it separate from the frozen authored item promise and
    # never replay the activity/progression pipeline for a reward event.
    from apps.rpg.constants import TriggerType
    from apps.rpg.services import DropService
    DropService.award_accomplishment(user, TriggerType.QUEST_COMPLETE)
    receipt = {"coins": coins, "xp": actual_xp, "items": items}
    occurrence.awarded_at = timezone.now()
    occurrence.reward_receipt = receipt
    occurrence.save(update_fields=["awarded_at", "reward_receipt", "updated_at"])
    if lifetime is not None:
        close_unpaid_attempts(occurrence, lifetime)
    return receipt


def _process(activity):
    user = activity.user
    _catalog_goals(user)
    receipts = []
    if activity.voided:
        return receipts
    for goal in ChallengeGoal.objects.filter(user=user, family_id=user.family_id).select_related("movement_type", "catalog_definition").order_by("pk"):
        if goal.catalog_gate_activity_id is not None and activity.pk < goal.catalog_gate_activity_id:
            continue
        if (goal.is_catalog and activity.trigger_type in {"homework_created", "creation_logged"}
                and activity.context.get("catalog_eligible") is not True):
            continue
        at = activity.occurred_at
        if goal.repeat_weekly or (not goal.is_catalog and goal.starts_at.astimezone(ZoneInfo(goal.timezone_name)).time() == time.min):
            # A late approval belongs to the recorded work day, not today's week.
            at = datetime.combine(activity.occurred_on, time(12), tzinfo=ZoneInfo(goal.timezone_name))
        occurrence = _occurrence(goal, at)
        if (not occurrence or (occurrence.ends_at is not None and at >= occurrence.ends_at)
                or occurrence.awarded_at or occurrence.status == "closed"):
            continue
        if occurrence.retry_of_id and activity.pk <= occurrence.snapshot.get("_retry_after_activity_id", 0):
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


def ingest_activity(user, source_type, source_id, trigger_type, occurred_at=None, occurred_on=None, context=None,
                    *, fresh_milestone=False):
    """Persist a source fact, then evaluate it. A failed evaluation stays retryable."""
    if str(trigger_type) not in FACT_TRIGGERS:
        return {"activity": None, "goals": []}
    if not source_type or source_id is None or not str(source_id):
        raise ValueError("A durable source identity is required")
    zone = family_zone(user)
    safe_context = {key: value for key, value in (context or {}).items() if key in CONTEXT_KEYS}
    for key in ("duration_minutes", "hours", "distance_meters"):
        if key in safe_context and safe_context[key] is not None:
            safe_context[key] = str(decimal_value(safe_context[key]))
    with transaction.atomic():
        lock_user(user)
        # A source that supplies its accepted timestamp keeps that exact
        # boundary. For a new untimed fact, sample the clock only after the
        # user gate: an initial catalog read may have enrolled while we waited.
        at = occurred_at or (_midnight(occurred_on, zone) if occurred_on else timezone.now())
        if timezone.is_naive(at):
            at = timezone.make_aware(at, zone)
        day = occurred_on or at.astimezone(zone).date()
        # Enrollment must precede the first fact so that fact counts in catalog windows.
        ChallengeEnrollment.objects.get_or_create(user=user, defaults={
            "starts_at": at, "timezone_name": str(zone), "discovery_tracking_started_at": timezone.now(),
        })
        activity, created = ChallengeActivity.objects.get_or_create(
            user=user, source_type=source_type, source_id=str(source_id), trigger_type=str(trigger_type),
            defaults={"occurred_at": at, "occurred_on": day, "context": safe_context},
        )
        # This internal attestation is never inferred from incoming context or
        # a newly observed old source. Normal live capture uses the trusted
        # ReadingRewardService hook, before this retryable evaluator runs.
        if created and fresh_milestone:
            _catalog_goals(user, gate_activity=activity, gated_only=True)
    with transaction.atomic():
        lock_user(user)
        # Keep related user/family reads out of this row lock. The user gate
        # above is NO KEY UPDATE so concurrent inventory grants can still
        # finish their foreign-key checks while we wait for their stack.
        activity = ChallengeActivity.objects.select_related("user__family").select_for_update(of=("self",)).get(pk=activity.pk)
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


def _lock_reward_skills(tags, *, retained_ids=()):
    """Protect new JSON promises against deletion and effective retirement."""
    from apps.achievements.models import Skill
    from apps.rpg.taxonomy_references import admit_references
    ids = {row["skill_id"] for row in tags}
    if Skill.objects.filter(pk__in=ids).count() != len(ids):
        raise ValueError("Choose existing skills.")
    admit_references(Skill, ids, retained_ids=retained_ids)


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
    _lock_reward_skills(data.get("skill_tags", []))
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
    filters = snapshot.get("filter", {})
    for key, detail in (("project_id", "for the selected project"),
                        ("skill_category_id", "in the selected skill category"),
                        ("chore_ids", "from the selected chores"),
                        ("savings_goal_id", "for the selected savings goal")):
        if filters.get(key):
            text += f" {detail}"
    return text


def _reward_preview(snapshot, item_catalog=None, item_details_cache=None):
    """Show the accepted promise; new snapshots apply acquisition policy."""
    from apps.rpg.models import ItemDefinition
    from .reward_items import reward_item_details
    rows = snapshot.get("items", [])
    if item_catalog is None:
        item_catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(
            [row["item_id"] for row in rows],
        )
    available = []
    for row in rows:
        item = item_catalog.get(row["item_id"])
        if item is not None:
            available.append({**row, **reward_item_details(item, snapshot=row, cache=item_details_cache)})
    return available


def qualifying_triggers(snapshot, *, legacy=False):
    from apps.rpg.constants import TriggerType
    from .services import TRIGGER_DAMAGE
    defaults = set(TriggerType.values) if legacy else EFFORT_TRIGGERS
    allowed = set(snapshot.get("filter", {}).get("allowed_triggers") or defaults)
    allowed &= set(TriggerType.values) if legacy else FACT_TRIGGERS
    if snapshot.get("metric") == "damage":
        allowed = {trigger for trigger in allowed if TRIGGER_DAMAGE.get(trigger, 0) > 0}
    return sorted(allowed)


def occurrence_payload(occurrence, pin_id=None, *, item_catalog=None, item_details_cache=None, controls=None):
    from .controls import control_context, retry_state, schedule_payload
    if controls is None:
        controls = control_context(occurrence.goal.user)
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
        elif occurrence.ends_at is not None and timezone.now() >= occurrence.ends_at:
            status = "expired"
    receipt = occurrence.reward_receipt
    return {
        "id": f"goal:{occurrence.pk}", "name": snapshot["name"], "description": snapshot["description"],
        "goal_definition_id": occurrence.goal_id, "qualifying_triggers": qualifying_triggers(snapshot),
        "retry": retry_state(occurrence, controls),
        "retry_of": f"goal:{occurrence.retry_of_id}" if occurrence.retry_of_id else None,
        "closed_reason": occurrence.closed_reason or None,
        "schedule": schedule_payload(occurrence.goal, controls),
        "origin": "catalog" if occurrence.goal.is_catalog else "parent",
        "first_details_opened_at": (occurrence.first_details_opened_at.isoformat()
                                    if occurrence.goal.is_catalog and occurrence.first_details_opened_at else None),
        "catalog_repeatable": bool(occurrence.goal.is_catalog and (
            occurrence.goal.repeat_days or occurrence.goal.repeat_weekly)),
        "catalog_icon": challenge_catalog_icon(occurrence.goal.catalog_definition) if occurrence.goal.is_catalog else None,
        "metric": snapshot["metric"], "target": number(snapshot["target"]), "progress": number(occurrence.progress),
        "unit": snapshot["unit"], "status": status,
        "starts_at": occurrence.starts_at.isoformat(),
        "ends_at": occurrence.ends_at.isoformat() if occurrence.ends_at else None,
        "completed_at": occurrence.completed_at.isoformat() if occurrence.completed_at else None,
        "timezone": occurrence.goal.timezone_name,
        "what_counts": _what_counts(snapshot, catalog=occurrence.goal.is_catalog), "rewards": {"coins": snapshot["coins"], "xp": snapshot["xp"], "items": _reward_preview(snapshot, item_catalog, item_details_cache)},
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


def _legacy_payload(quest, pin_id, *, item_catalog=None, item_details_cache=None):
    definition = quest.definition
    key = f"legacy:{quest.pk}"
    from .serializers import QuestRewardItemSerializer
    from .reward_items import accepted_reward_items
    items = QuestRewardItemSerializer(
        accepted_reward_items(quest, item_catalog=item_catalog), many=True,
        context={"reward_item_details_cache": item_details_cache},
    ).data
    return {
        "id": key, "name": definition.name, "description": definition.description,
        "goal_definition_id": None,
        "qualifying_triggers": qualifying_triggers({"filter": definition.trigger_filter,
            "metric": "damage" if definition.quest_type == "boss" else "count"}, legacy=True),
        "retry": {"allowed": False, "reason": "not_catalog", "latest_attempt_id": None},
        "retry_of": None, "closed_reason": None, "schedule": None,
        "origin": "legacy",
        "first_details_opened_at": None, "catalog_repeatable": False,
        "catalog_icon": challenge_catalog_icon(definition),
        "metric": "damage" if definition.quest_type == "boss" else "count", "target": str(quest.effective_target),
        "progress": str(quest.current_progress), "unit": "damage" if definition.quest_type == "boss" else "actions",
        "status": "expired" if quest.is_expired else quest.status,
        "starts_at": quest.start_date.isoformat(), "ends_at": quest.end_date.isoformat(),
        "completed_at": None,
        # Bosses list only triggers that deal damage, matching qualifying_triggers.
        "what_counts": _what_counts({"filter": definition.trigger_filter,
            "metric": "damage" if definition.quest_type == "boss" else "count"}),
        "rewards": {"coins": definition.coin_reward, "xp": definition.xp_reward, "items": items},
        "action": None, "pinned": pin_id == key, "repeat_weekly": False, "legacy": True,
        "rage_shield": quest.rage_shield, "participants": [
            {"user": participant.user_id, "user_name": participant.user.display_label, "contribution": participant.contribution}
            for participant in sorted(quest.participants.all(), key=lambda row: (-row.contribution, row.user_id, row.pk))
        ],
        "reward_receipt": {"id": key, "status": "legacy", "coins_awarded": 0, "xp_awarded": 0, "awarded_at": None},
    }


@transaction.atomic
def list_goals(user):
    lock_user(user)
    _catalog_goals(user)
    now = timezone.now()
    current = {}
    goals = ChallengeGoal.objects.filter(user=user, family_id=user.family_id).select_related(
        "movement_type", "catalog_definition",
    ).prefetch_related(Prefetch(
        "occurrences",
        queryset=ChallengeOccurrence.objects.filter(
            Q(starts_at__lte=now) & (Q(ends_at__gt=now) | Q(ends_at__isnull=True))
            | Q(goal__repeat_weekly=False, goal__repeat_days=0, starts_at=F("goal__starts_at"))
            | Q(retry_of__isnull=False),
        ),
        to_attr="_listed_occurrences",
    ), Prefetch(
        "occurrences", queryset=ChallengeOccurrence.objects.filter(goal__is_catalog=False, goal__repeat_weekly=True)
        .order_by("-starts_at", "-pk")[:1], to_attr="_listed_latest",
    )).order_by("pk")
    # Ordered so newly materialized occurrences get the same ids on every
    # database and query plan, as in the receipt loop below.
    for goal in goals:
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
    occurrences = ChallengeOccurrence.objects.filter(goal__user=user, goal__family_id=user.family_id).select_related("goal", "goal__catalog_definition")
    active = list(occurrences.filter(starts_at__lte=now).filter(Q(ends_at__gt=now) | Q(ends_at__isnull=True)))
    recent = list(occurrences.filter(awarded_at__isnull=False).order_by("-awarded_at", "-pk")[:20])
    terminal = list(occurrences.filter(ends_at__lte=now).order_by("-ends_at", "-pk")[:20])
    future = list(occurrences.filter(starts_at__gt=now, goal__is_catalog=False))
    unique = {row.pk: row for row in active + recent + terminal + future}
    for goal in goals:
        if not goal.is_catalog and goal.repeat_weekly and goal.pk not in current and goal._listed_latest:
            # Pausing a long-lived rule must not hide its resume controls
            # behind the general twenty-row history limit.
            previous = goal._listed_latest[0]
            unique[previous.pk] = previous
    from .controls import control_context, retry_state
    controls = control_context(user)
    # Every expired one-time offer remains discoverable even beyond the
    # general history limit, so a large catalog cannot strand retry actions.
    for group in controls["groups"].values():
        latest = max(group, key=lambda row: (row.starts_at, row.pk), default=None)
        if latest is not None and retry_state(latest, controls)["allowed"]:
            unique[latest.pk] = latest
    if pin.occurrence_id:
        pinned = occurrences.filter(pk=pin.occurrence_id).first()
        if pinned:
            unique[pinned.pk] = pinned
    legacy = Quest.objects.filter(participants__user=user).select_related("definition")
    legacy_rows = list(legacy.filter(status="active")) + list(legacy.exclude(status="active")[:20])
    prefetch_related_objects(
        legacy_rows,
        Prefetch("participants", queryset=QuestParticipant.objects.select_related("user")),
        Prefetch("definition__reward_items", queryset=QuestRewardItem.objects.select_related(
            "item__pet_species", "item__potion_type",
        )),
    )
    # One catalog read covers accepted promises in results and recent receipts,
    # including legacy snapshots. An empty accepted promise stays empty.
    from apps.rpg.models import ItemDefinition
    item_ids = {item["item_id"] for row in unique.values() for item in row.snapshot.get("items", [])}
    item_ids.update(item["item_id"] for row in legacy_rows for item in (row.reward_items_snapshot or []))
    item_catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(item_ids)
    item_details_cache = {}
    rows = [occurrence_payload(row, pin_id, item_catalog=item_catalog, item_details_cache=item_details_cache, controls=controls)
            for row in unique.values()]
    rows += [_legacy_payload(row, pin_id, item_catalog=item_catalog, item_details_cache=item_details_cache)
             for row in legacy_rows]
    receipts = ChallengeActivity.objects.filter(user=user, voided=False, context__has_key="_receipt").order_by("-created_at", "-pk")[:20]
    from .availability import definition_is_available
    from .milestone_eligibility import gated_definitions, prerequisite_unavailable
    from .serializers import QuestDefinitionSerializer
    accepted_ids = set(goals.values_list("catalog_definition_id", flat=True))
    accepted_ids.update(Quest.objects.filter(participants__user=user).values_list("definition_id", flat=True))
    accepted_ids.update(QuestDefinition.objects.filter(pk__in=accepted_ids).exclude(
        superseded_by__isnull=True,
    ).values_list("superseded_by_id", flat=True))
    locked = gated_definitions().exclude(pk__in=accepted_ids - {None}).prefetch_related(
        "reward_items__item__pet_species__available_potions", "reward_items__item__potion_type", "skill_tags__skill",
    ).order_by("quest_type", "name", "pk") if user.role == "child" else []
    # A retryable ended prerequisite can still unlock this offer. Omit only
    # paths with no accepted completion, current window or eligible retry.
    locked = [definition for definition in locked if definition_is_available(definition) and not (
        definition.prerequisite_quest_id and prerequisite_unavailable(user, definition.prerequisite_quest_id, controls=controls)
    )]
    return {"results": rows, "pin": pin_id, "recent_receipts": [occurrence_payload(row, pin_id, item_catalog=item_catalog, item_details_cache=item_details_cache, controls=controls) for row in recent],
            "challenge_receipts": [activity.context["_receipt"] for activity in receipts],
            "locked_catalog": QuestDefinitionSerializer(locked, many=True, context={"eligibility_user": user}).data}


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
