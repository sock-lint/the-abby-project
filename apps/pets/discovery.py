"""Read-only acquisition paths for the exact supported Hatchery appearances.

Current definitions describe offers. Saved occurrences describe accepted
promises, even when that definition's name, target or rewards later change.
Nothing in this projection enrolls, repairs, pins, retries or awards a goal.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.achievements.models import SkillProgress, UserBadge
from apps.quests.controls import control_context, identity, retry_state
from apps.quests.goals import FACT_TRIGGERS, number
from apps.quests.milestone_eligibility import has_milestone_gate, milestone_eligibility
from apps.quests.models import ChallengeOccurrence, ChallengePin, Quest, QuestDefinition, QuestRewardItem
from apps.quests.queries import active_system_definitions
from apps.rpg.catalog_support import available_pet_pairs, egg_species, item_is_available, potion_type_for_item
from apps.rpg.models import ItemDefinition


TRIALS_PATH = "/quests?tab=trials"


def _pairs(rewards, available_pairs, *, saved=False):
    """Require the complete positive bundle and canonical typed ingredients."""
    eggs, potions = set(), set()
    for reward in rewards:
        item, quantity = reward.item, reward.quantity
        if type(quantity) is not int or quantity <= 0:
            return set()
        if not saved and not item_is_available(item):
            return set()
        if item.item_type == "egg":
            species = egg_species(item) if item.pet_species_id else None
            if species is None:
                return set()
            eggs.add(species.pk)
        elif item.item_type == "potion":
            potion = potion_type_for_item(item) if item.potion_type_id else None
            if potion is None or not item_is_available(item):
                return set()
            potions.add(potion.pk)
    pairs = {(species, potion) for species in eggs for potion in potions}
    # A partially supported multi-ingredient bundle is not a guaranteed offer.
    return pairs if pairs and pairs <= available_pairs else set()


def _saved_pairs(snapshot, catalog, available_pairs):
    from types import SimpleNamespace

    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list):
        return set()
    rows = []
    for row in snapshot["items"]:
        if not isinstance(row, dict) or not _item_id(row.get("item_id")):
            return set()
        item = catalog.get(row["item_id"])
        if item is None:
            return set()
        # Frozen item IDs, rather than today's definition reward links, own the
        # promise. Malformed/rebound ingredients cannot identify another form.
        if "item_type" in row and row["item_type"] != item.item_type:
            return set()
        if item.item_type in {"egg", "potion"} and "item_metadata" in row:
            key = "species" if item.item_type == "egg" else "variant"
            frozen = row["item_metadata"]
            if (not isinstance(frozen, dict) or not isinstance(item.metadata, dict)
                    or frozen.get(key) != item.metadata.get(key)):
                return set()
        rows.append(SimpleNamespace(item=item, quantity=row.get("quantity")))
    return _pairs(rows, available_pairs, saved=True)


def _item_id(value):
    return type(value) is int and 0 < value <= 9223372036854775807


def _snapshot_items(snapshot):
    rows = snapshot.get("items") if isinstance(snapshot, dict) else None
    return rows if isinstance(rows, list) else []


def _presentable_snapshot(snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("name"), str) or not snapshot["name"].strip():
        return False
    try:
        target = Decimal(str(snapshot.get("target")))
        return target.is_finite() and target > 0
    except InvalidOperation:
        return False


def _status(occurrence, now):
    if occurrence.status != "active":
        return occurrence.status
    if occurrence.starts_at > now:
        return "upcoming"
    if occurrence.ends_at is not None and occurrence.ends_at <= now:
        return "expired"
    return "active"


def _visible_history_ids(user, now):
    """Only link to rows the existing Trials list can actually return."""
    rows = ChallengeOccurrence.objects.filter(goal__user=user, goal__family_id=user.family_id)
    visible = set(rows.filter(starts_at__lte=now).filter(
        Q(ends_at__gt=now) | Q(ends_at__isnull=True),
    ).values_list("pk", flat=True))
    visible.update(rows.filter(awarded_at__isnull=False).order_by("-awarded_at", "-pk")
                   .values_list("pk", flat=True)[:20])
    visible.update(rows.filter(ends_at__lte=now).order_by("-ends_at", "-pk")
                   .values_list("pk", flat=True)[:20])
    pinned = ChallengePin.objects.filter(user=user).values_list("occurrence_id", flat=True).first()
    if pinned:
        visible.add(pinned)
    return visible


def acquisition_challenges(user):
    """One batched projection keyed by (species ID, potion ID), never a write."""
    now = timezone.now()
    pairs = available_pet_pairs()
    controls = control_context(user)
    definitions = list(active_system_definitions().select_related(
        "prerequisite_quest", "required_skill", "required_badge",
    ).prefetch_related(
        Prefetch("reward_items", queryset=QuestRewardItem.objects.select_related(
            "item__pet_species", "item__potion_type",
        )), "skill_tags",
    ))
    current = {row.pk: row for row in definitions}
    current_pairs = {row.pk: _pairs(row.reward_items.all(), pairs)
                     for row in definitions if not row.is_cooperative}
    goals = [goal for goal in controls["goals"].values() if goal.is_catalog and goal.catalog_definition_id]
    # Control context intentionally loads only the newest attempt per goal.
    # Discovery also needs older frozen pairs when a later promise differs.
    occurrences = list(ChallengeOccurrence.objects.filter(goal_id__in=[goal.pk for goal in goals]))
    for occurrence in occurrences:
        occurrence.goal = controls["goals"][occurrence.goal_id]
    item_ids = {row.get("item_id") for occurrence in occurrences
                for row in _snapshot_items(occurrence.snapshot) if isinstance(row, dict) and _item_id(row.get("item_id"))}
    item_ids.update(row.get("item_id") for goal in goals for row in _snapshot_items({"items": goal.reward_items})
                    if isinstance(row, dict) and _item_id(row.get("item_id")))
    catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(
        item_ids,
    )
    candidates = defaultdict(list)
    for occurrence in occurrences:
        if _presentable_snapshot(occurrence.snapshot):
            canonical = identity(occurrence.goal, controls)
            for pair in _saved_pairs(occurrence.snapshot, catalog, pairs):
                candidates[pair, canonical].append(occurrence)
    # Legacy saved system campaigns retain their original reward snapshot.
    # Private parent quests are never global guaranteed acquisition hints.
    legacy = list(Quest.objects.filter(
        participants__user=user, definition__is_system=True, definition__is_cooperative=False,
    ).select_related("definition").prefetch_related(Prefetch(
        "definition__reward_items", queryset=QuestRewardItem.objects.select_related("item__pet_species", "item__potion_type"),
    )).order_by("-start_date", "-pk"))
    legacy_item_ids = {row.get("item_id") for quest in legacy
                       for row in _snapshot_items({"items": quest.reward_items_snapshot})
                       if isinstance(row, dict) and _item_id(row.get("item_id"))}
    legacy_catalog = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(
        legacy_item_ids,
    )
    legacy_candidates = defaultdict(list)
    for quest in legacy:
        canonical = quest.definition.superseded_by_id or quest.definition_id
        saved_pairs = (_pairs(quest.definition.reward_items.all(), pairs, saved=True)
                       if quest.reward_items_snapshot is None else
                       _saved_pairs({"items": quest.reward_items_snapshot}, legacy_catalog, pairs))
        for pair in saved_pairs:
            legacy_candidates[pair, canonical].append(quest)

    # A retained alias supplies a frozen attempt, never today's outer metadata.
    known = dict(current)
    canonical_ids = {identity(goal, controls) for goal in goals}
    canonical_ids.update(quest.definition.superseded_by_id or quest.definition_id for quest in legacy)
    accepted_ids = {goal.catalog_definition_id for goal in goals}
    accepted_ids.update(quest.definition_id for quest in legacy)
    # A missing creator preserves a directly accepted promise; it cannot make
    # a different orphan-private definition visible through an alias.
    known.update(QuestDefinition.objects.filter(
        Q(is_system=True) | Q(created_by__family_id=user.family_id)
        | Q(created_by__isnull=True, pk__in=accepted_ids),
    ).in_bulk(canonical_ids - known.keys()))
    completed = set(controls["paid"])
    completed.update(identity(row.goal, controls) for row in occurrences if row.status == "completed")
    completed.update(key for key, statuses in controls["legacy"].items() if "completed" in statuses)
    facts = {
        "completed": completed,
        "skill_levels": dict(SkillProgress.objects.filter(user=user, unlocked=True).values_list("skill_id", "level")),
        "badges": set(UserBadge.objects.filter(user=user).values_list("badge_id", flat=True)),
    }
    available = {}
    for definition_id, pair_set in current_pairs.items():
        definition = current[definition_id]
        allowed = (definition.trigger_filter or {}).get("allowed_triggers")
        available[definition_id] = bool(
            pair_set and user.role == "child" and definition_id in controls["offered"]
            and (definition.is_repeatable or definition_id not in completed)
            and (not allowed or FACT_TRIGGERS.intersection(allowed))
            and milestone_eligibility(user, definition, new_enrollment=False,
                                     facts=facts, active_definitions=current)["unlocked"]
        )
    # Automatic enrollment never opens a second goal for an accepted identity:
    # that goal keeps its enrollment-time reward and retries copy the saved
    # promise. Nonrepeatable legacy windows that are active or completed, and
    # any legacy window of a milestone-gated offer, likewise block enrollment
    # (goals._catalog_goals). Once enrollment is blocked, only a saved promise
    # that can still pay makes today's pair reachable, so a child is never told
    # that an edited or older pair is a guaranteed reward they cannot earn.
    accepted_goals = defaultdict(list)
    for goal in goals:
        accepted_goals[identity(goal, controls)].append(goal)

    def can_still_pay(occurrence):
        return _status(occurrence, now) in {"active", "upcoming"} or retry_state(occurrence, controls)["allowed"]

    def reachable(pair, definition_id):
        definition = current[definition_id]
        accepted = accepted_goals.get(definition_id, [])
        legacy_statuses = controls["legacy"].get(definition_id, [])
        if not (accepted or (legacy_statuses and has_milestone_gate(definition))
                or (not definition.is_repeatable and {"active", "completed"}.intersection(legacy_statuses))):
            return True  # A new automatic window would freeze today's reward.
        # ``get`` avoids the empty rows the result loop adds to these defaultdicts.
        if any(can_still_pay(row) for row in candidates.get((pair, definition_id), ())):
            return True
        if any(quest.status == "active" and not quest.is_expired
               for quest in legacy_candidates.get((pair, definition_id), ())):
            return True
        # The goal's own reward opens repeat windows and a first window that
        # has not been created yet, and froze its live attempt (including an
        # attempt whose saved snapshot is not presentable).
        return any(pair in _saved_pairs({"items": goal.reward_items}, catalog, pairs) and (
            definition.is_repeatable
            or (not goal.control_occurrences and (goal.ends_at is None or goal.ends_at > now))
            or any(can_still_pay(row) for row in goal.control_occurrences))
            for goal in accepted)

    keys = set(candidates) | set(legacy_candidates)
    keys.update((pair, pk) for pk, offered_pairs in current_pairs.items() for pair in offered_pairs)
    visible = _visible_history_ids(user, now) if occurrences else set()
    legacy_visible = set(Quest.objects.filter(participants__user=user).exclude(status="active")
                         .values_list("pk", flat=True)[:20]) if legacy else set()
    result = defaultdict(list)
    for pair, definition_id in keys:
        definition = known.get(definition_id)
        if definition is None:
            continue
        attempt, path = None, TRIALS_PATH
        saved = candidates[pair, definition_id]
        if saved:
            chosen = max(saved, key=lambda row: (row.awarded_at is not None or row.status == "completed",
                                                 _status(row, now) == "active", row.starts_at, row.pk))
            retry = retry_state(chosen, controls)
            attempt = {"id": f"goal:{chosen.pk}", "name": chosen.snapshot["name"], "status": _status(chosen, now),
                       "progress": number(chosen.progress), "target": str(chosen.snapshot["target"]),
                       "ends_at": chosen.ends_at.isoformat() if chosen.ends_at else None,
                       "retry_available": retry["allowed"]}
            if chosen.pk in visible or retry["allowed"]:
                path += "&" + urlencode({"goal": attempt["id"]})
        elif legacy_candidates[pair, definition_id]:
            chosen = max(legacy_candidates[pair, definition_id], key=lambda row: (
                row.status == "completed", row.status == "active", row.start_date, row.pk,
            ))
            status = "expired" if chosen.is_expired else chosen.status
            attempt = {"id": f"legacy:{chosen.pk}", "name": chosen.definition.name, "status": status,
                       "progress": str(chosen.current_progress), "target": str(chosen.effective_target),
                       "ends_at": chosen.end_date.isoformat(), "retry_available": False}
            if chosen.status == "active" or chosen.pk in legacy_visible:
                path += "&" + urlencode({"goal": attempt["id"]})
        result[pair].append({
            "definition_id": definition_id, "name": definition.name,
            "offer_available": (available.get(definition_id, False) and pair in current_pairs.get(definition_id, set())
                                and reachable(pair, definition_id)),
            "target": str(definition.target_value), "duration_days": definition.duration_days,
            "attempt": attempt, "path": path,
        })
    return {pair: sorted(rows, key=lambda row: (row["name"], row["definition_id"])) for pair, rows in result.items()}
