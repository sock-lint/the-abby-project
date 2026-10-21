"""Bounded household Voyager observations; reading this report writes nothing.

This is a current new-child snapshot, not an experiment assignment, historical
eligibility reconstruction, or a retention measurement. Accepted automatic
windows are classified from their saved promises, never today's catalog rules.
"""
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import json
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Case, Exists, F, OuterRef, Q, Value, When
from django.utils import timezone

from apps.achievements.models import Skill, SkillProgress, UserBadge
from apps.families.models import LiveTestFamily
from apps.families.queries import children_in
from .activity import household_timezone
from .discovery import _authorized_observer
from .milestone_eligibility import has_milestone_gate, validate_milestone_gate
from .models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestParticipant
from .queries import active_system_definitions, equivalent_definition_ids


COHORT_DAYS = 180
MAX_COHORT_CHILDREN = 100
MAX_ACCEPTED_RECORDS = 10_000
READING_FILTER = {"allowed_triggers": ["reading_logged"]}
STATE_FIELDS = ("locked", "ready", "active", "completed", "expired", "unknown")
GROUP_FIELDS = (
    "accepted_windows", "pending_windows", "mature_completed", "mature_expired",
    "mature_unknown", "unknown_windows", "mature_denominator",
)
POLICIES = (
    ("saved_45_day", "Saved 45-day windows"),
    ("milestone_56_day", "56 days · milestones"),
    ("milestone_84_day", "84 days · selected milestones"),
    ("other_or_unknown", "Other or unknown policy"),
)
NOTES = [
    "This is a current snapshot of active nonstaff children in your family registered within 180 inclusive family-local days. It is not an all-time cohort or a retention measurement; membership and active status are not reconstructed historically.",
    "Locked and ready describe current server rules, not the exact first time a child unlocked Voyager. With native milestone gates, ready waits for the next qualifying new Reading Adventure; an ungated catalog uses automatic tracking instead.",
    "Saved windows are not restricted to the last 30 days. Policy groups use frozen count-20 Reading Adventure rules, elapsed duration and native gate snapshots. They do not certify identical rewards or prove a causal policy effect; older badge-only gates were not frozen.",
    "Only windows whose full saved deadline has passed enter mature outcomes. Early completions remain pending until that deadline. Mature completion rate is completed divided by completed plus expired; pending, unknown timing and unknown outcomes are excluded, never counted as failures.",
    "Completion must be consistent with saved progress and a recorded completion time. That time records processing, not necessarily when the child did the work. Legacy quests have no frozen full policy or completion time, so their policy and mature outcomes remain unknown.",
    "Valid explicit retry attempts retain their saved policies and separate window outcomes; each child appears once, using the latest attempt or a valid lifetime completion. Unlinked duplicates, future-dated, malformed or conflicting evidence is unknown. A saved goal without an occurrence and orphaned same-name catalog history cannot establish a new offer. These reads never materialize, start, expire, backfill or reward a challenge.",
    "Trusted provisioned test families are excluded. Counts expose no child identities, row identifiers, descriptions, reading details or private journal text. Capacity failures withhold totals rather than returning partial counts. Bounded saved rows are not a repeatable-read historical snapshot.",
]


def _groups():
    return [{"policy": policy, "label": label, **dict.fromkeys(GROUP_FIELDS, 0),
             "completion_rate": None} for policy, label in POLICIES]


def _withheld(result, status, *, truncated=False):
    result["status"] = status
    result["cohort"]["truncated"] = truncated
    result["current_states"] = dict.fromkeys(STATE_FIELDS)
    for group in result["policy_groups"]:
        group.update(dict.fromkeys(GROUP_FIELDS), completion_rate=None)
    return result


def _positive_int(value):
    return type(value) is int and value > 0


def _amount(value):
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


def _saved_policy(row, companion_ids, skill_id, *, valid_retry=False):
    snapshot = row["snapshot"]
    if not isinstance(snapshot, dict):
        return "other_or_unknown"
    if (snapshot.get("metric") != "count" or _amount(snapshot.get("target")) != 20
            or snapshot.get("filter") != READING_FILTER
            or snapshot.get("catalog_name") != "Reading Voyager"
            or snapshot.get("catalog_type") != "collection"
            or row["goal__repeat_weekly"] or row["goal__repeat_days"]
            or row["ends_at"] is None or row["goal__ends_at"] is None
            or (not valid_retry and (row["starts_at"] != row["goal__starts_at"]
                                     or row["ends_at"] != row["goal__ends_at"]))):
        return "other_or_unknown"
    # Native retries preserve the original wall-clock span. After the chain
    # validates that span, retain its original elapsed policy across DST.
    duration = (row["goal__ends_at"] - row["goal__starts_at"] if valid_retry
                else row["ends_at"] - row["starts_at"])
    gate = row["goal__catalog_gate_snapshot"]
    if (duration == timedelta(days=45) and gate == {}
            and "catalog_gate" not in snapshot
            and row["goal__catalog_gate_activity_id"] is None):
        return "saved_45_day"
    milestone_policy = {timedelta(days=56): "milestone_56_day",
                        timedelta(days=84): "milestone_84_day"}.get(duration)
    if not companion_ids or skill_id is None or milestone_policy is None:
        return "other_or_unknown"
    companion_id = gate.get("prerequisite_quest_id") if isinstance(gate, dict) else None
    if not _positive_int(companion_id) or companion_id not in companion_ids:
        return "other_or_unknown"
    expected = {"version": 1, "prerequisite_quest_id": companion_id,
                "required_skill_id": skill_id, "required_skill_level": 1,
                "required_badge_id": None}
    opening_id = row["goal__catalog_gate_activity_id"]
    saved_gate = snapshot.get("catalog_gate")
    expected_saved = {**expected, "opening_activity_id": opening_id}
    # Equality alone would accept Python bools as integers in corrupt JSON.
    if (not isinstance(gate, dict) or set(gate) != set(expected)
            or any(type(gate[key]) is not type(value) or gate[key] != value for key, value in expected.items())
            or not _positive_int(opening_id)
            or not isinstance(saved_gate, dict) or set(saved_gate) != set(expected_saved)
            or any(type(saved_gate[key]) is not type(value) or saved_gate[key] != value
                   for key, value in expected_saved.items())):
        return "other_or_unknown"
    return milestone_policy


def _automatic_state(row, as_of):
    """A deadline may expire a saved active row without writing its status."""
    start, end = row["starts_at"], row["ends_at"]
    if end is None or end <= start or start > as_of or row["created_at"] > as_of:
        return "unknown", "unknown_windows"
    mature = end <= as_of
    unknown = "mature_unknown" if mature else "unknown_windows"
    snapshot = row["snapshot"]
    target = _amount(snapshot.get("target")) if isinstance(snapshot, dict) else None
    progress = _amount(row["progress"])
    if target is None or target <= 0 or progress is None:
        return "unknown", unknown
    status, completed_at = row["status"], row["completed_at"]
    if status == "completed":
        if (progress < target or completed_at is None or completed_at < start
                or completed_at > as_of):
            return "unknown", unknown
        return "completed", "mature_completed" if mature else "pending_windows"
    if status not in {"active", "expired"} or completed_at is not None or progress >= target:
        return "unknown", unknown
    if status == "expired" and not mature:
        return "unknown", unknown
    return ("expired", "mature_expired") if mature else ("active", "pending_windows")


def _retry_chain(rows, as_of):
    """Recognize one complete native retry chain without repairing its evidence."""
    by_id = {row["pk"]: row for row in rows}
    roots = [row for row in rows if row["retry_of_id"] is None]
    if len(roots) != 1:
        return None
    root = roots[0]
    if root["starts_at"] != root["goal__starts_at"] or root["ends_at"] != root["goal__ends_at"]:
        return None
    if len(rows) == 1:
        return rows
    children = {}
    for row in rows:
        previous_id = row["retry_of_id"]
        if previous_id is not None:
            if previous_id not in by_id or previous_id in children:
                return None
            children[previous_id] = row
    try:
        zone = ZoneInfo(root["goal__timezone_name"])

        def duration(row):
            # Untimed or malformed saved attempts cannot establish a timed
            # retry policy. Keep them as unknown evidence without repairing or
            # interpreting today's catalog as their original promise.
            if not all(isinstance(row[field], datetime) for field in ("starts_at", "ends_at")):
                raise ValueError
            return (row["ends_at"].astimezone(zone).replace(tzinfo=None)
                    - row["starts_at"].astimezone(zone).replace(tzinfo=None))

        def promise(row):
            if not isinstance(row["snapshot"], dict):
                raise ValueError
            return json.dumps({key: value for key, value in row["snapshot"].items()
                               if key != "_retry_after_activity_id"}, sort_keys=True, allow_nan=False)
        frozen = promise(root)
        window = duration(root)
        ordered, seen, current, cutoff = [], set(), root, 0
        while current is not None:
            if current["pk"] in seen or promise(current) != frozen or duration(current) != window:
                return None
            seen.add(current["pk"])
            if ordered:
                previous = ordered[-1]
                next_cutoff = current["snapshot"].get("_retry_after_activity_id")
                if (type(next_cutoff) is not int or next_cutoff < cutoff
                        or current["starts_at"] < previous["ends_at"]
                        or current["created_at"] < previous["created_at"]
                        or (previous["status"] == "completed" and previous["completed_at"] is not None
                            and previous["completed_at"] < current["starts_at"])):
                    return None
                cutoff = next_cutoff
            ordered.append(current)
            current = children.get(current["pk"])
    except (KeyError, TypeError, ValueError):
        return None
    if len(ordered) != len(rows):
        return None
    completed = [row for row in rows if _automatic_state(row, as_of)[0] == "completed"]
    if len(completed) > 1:
        return None
    for row in rows:
        if _automatic_state(row, as_of)[0] == "unknown" and not (
            completed and row["status"] == "closed" and row["closed_reason"] == "reward_already_awarded"
            and row["starts_at"] <= as_of and row["created_at"] <= as_of and row["ends_at"] > row["starts_at"]
        ):
            return None
    return ordered


def _legacy_state(row, as_of):
    start, end = row["quest__start_date"], row["quest__end_date"]
    if (end <= start or start > as_of or row["quest__created_at"] > as_of
            or row["quest__updated_at"] > as_of or row["foreign_participant"]):
        return "unknown", "unknown_windows"
    status = row["quest__status"]
    if status == "completed":
        state = "completed"
    elif status == "active":
        state = "expired" if end <= as_of else "active"
    elif status == "expired" and end <= as_of:
        state = "expired"
    else:
        return "unknown", "mature_unknown" if end <= as_of else "unknown_windows"
    # No immutable target, gates or completion time: don't fabricate a known
    # outcome from the current definition or general updated_at timestamp.
    return state, "mature_unknown" if end <= as_of else "pending_windows"


def _current_eligibility(definition, child_ids, family_id, as_of):
    """Bulk current gate facts, bounded by child identities rather than history."""
    try:
        validate_milestone_gate(definition)
    except ValidationError:
        return {}, set(child_ids)
    met = {child_id: True for child_id in child_ids}
    unknown = set()
    if definition.prerequisite_quest_id:
        prerequisite_ids = equivalent_definition_ids(definition.prerequisite_quest)
        prior = ChallengeOccurrence.objects.filter(
            goal__user_id__in=child_ids, goal__family_id=family_id, goal__is_catalog=True,
            goal__user__family_id=family_id, goal__user__is_active=True,
            goal__user__is_staff=False, goal__user__role="child",
            goal__catalog_definition_id__in=prerequisite_ids, status="completed",
        ).order_by()
        any_completed = set(prior.values_list("goal__user_id", flat=True).distinct())
        completed = set(prior.filter(
            completed_at__gte=F("starts_at"), completed_at__lte=as_of,
            created_at__lte=as_of, starts_at__lte=as_of,
        ).values_list("goal__user_id", flat=True).distinct())
        foreign = QuestParticipant.objects.filter(quest_id=OuterRef("quest_id")).exclude(user__family_id=family_id)
        legacy = QuestParticipant.objects.filter(
            user_id__in=child_ids, user__family_id=family_id, user__is_active=True,
            user__is_staff=False, user__role="child",
            quest__definition_id__in=prerequisite_ids, quest__status="completed",
        ).annotate(foreign_participant=Exists(foreign), valid_timing=Case(
            When(quest__start_date__lte=as_of, quest__created_at__lte=as_of,
                 quest__updated_at__lte=as_of, then=Value(True)),
            default=Value(False), output_field=BooleanField(),
        )).order_by().values_list("user_id", "foreign_participant", "valid_timing").distinct()
        unsafe = any_completed - completed
        for child_id, foreign_participant, valid_timing in legacy:
            (unsafe if foreign_participant or not valid_timing else completed).add(child_id)
        unknown.update(unsafe - completed)
        for child_id in child_ids:
            met[child_id] &= child_id in completed
    if definition.required_skill_id:
        progressed = set(SkillProgress.objects.filter(
            user_id__in=child_ids, user__family_id=family_id, user__is_active=True,
            user__is_staff=False, user__role="child", skill_id=definition.required_skill_id,
            unlocked=True, level__gte=definition.required_skill_level,
        ).values_list("user_id", flat=True))
        for child_id in child_ids:
            met[child_id] &= child_id in progressed
    if definition.required_badge_id:
        earned = set(UserBadge.objects.filter(
            user_id__in=child_ids, user__family_id=family_id, user__is_active=True,
            user__is_staff=False, user__role="child", badge_id=definition.required_badge_id,
        ).values_list("user_id", flat=True))
        for child_id in child_ids:
            met[child_id] &= child_id in earned
    return met, unknown


def voyager_feedback(actor):
    actor = _authorized_observer(actor)
    as_of = timezone.now()
    zone = household_timezone(actor)
    until = timezone.localdate(as_of, timezone=zone)
    since = until - timedelta(days=COHORT_DAYS - 1)
    starts_at = datetime.combine(since, time.min, tzinfo=zone)
    ends_before = datetime.combine(until + timedelta(days=1), time.min, tzinfo=zone)
    excluded = LiveTestFamily.objects.filter(family_id=actor.family_id).exists()
    child_ids = [] if excluded else list(children_in(actor.family).filter(
        is_staff=False, date_joined__gte=starts_at, date_joined__lt=ends_before,
        date_joined__lte=as_of,
    ).order_by("pk").values_list("pk", flat=True)[:MAX_COHORT_CHILDREN + 1])
    result = {
        "schema_version": 1, "status": "insufficient_evidence",
        "period": {"since": since.isoformat(), "until": until.isoformat(), "timezone": str(zone),
                   "starts_at": starts_at.isoformat(), "ends_before": ends_before.isoformat(),
                   "as_of": as_of.isoformat()},
        "catalog": {"status": "missing", "name": "Reading Voyager", "acceptance_mode": None},
        "cohort": {"registered_within_days": COHORT_DAYS, "eligible_children": len(child_ids),
                   "max_children": MAX_COHORT_CHILDREN, "truncated": False,
                   "observer_family_excluded": excluded},
        "current_states": dict.fromkeys(STATE_FIELDS, 0),
        "policy_groups": _groups(), "notes": list(NOTES),
    }
    if len(child_ids) > MAX_COHORT_CHILDREN:
        result["cohort"]["eligible_children"] = None
        return _withheld(result, "cohort_limit_exceeded", truncated=True)
    definitions = list(active_system_definitions().filter(
        name="Reading Voyager", created_by__isnull=True,
    ).select_related("prerequisite_quest", "required_skill", "required_badge").order_by("pk")[:2])
    if len(definitions) != 1:
        ambiguous = QuestDefinition.objects.filter(
            name="Reading Voyager", is_system=True, created_by__isnull=True, superseded_by__isnull=True,
        ).count() > 1
        result["catalog"]["status"] = "ambiguous" if ambiguous else "missing"
        return _withheld(result, "catalog_ambiguous" if ambiguous else "catalog_unavailable")
    definition = definitions[0]
    definition_ids = equivalent_definition_ids(definition)
    result["catalog"].update(status="available", acceptance_mode=(
        "next_qualifying_reading" if has_milestone_gate(definition) else "automatic_tracking"))
    if not child_ids:
        return result
    companions = list(active_system_definitions().filter(
        name="Reading Companion", created_by__isnull=True,
    ).order_by("pk")[:2])
    companion_ids = equivalent_definition_ids(companions[0]) if len(companions) == 1 else []
    skill_ids = list(Skill.objects.filter(
        category__name="Language Arts", name="Reading Comprehension",
    ).order_by("pk").values_list("pk", flat=True)[:2])
    skill_id = skill_ids[0] if len(skill_ids) == 1 else None
    scope = dict(user_id__in=child_ids, family_id=actor.family_id, is_catalog=True,
                 user__family_id=actor.family_id, user__is_active=True,
                 user__is_staff=False, user__role="child")
    goals = list(ChallengeGoal.objects.filter(**scope).filter(
        Q(catalog_definition_id__in=definition_ids)
        | Q(catalog_definition__isnull=True, name="Reading Voyager"),
    ).order_by("pk").values("pk", "user_id", "catalog_definition_id")[:MAX_ACCEPTED_RECORDS + 1])
    goal_ids = [row["pk"] for row in goals if row["catalog_definition_id"] in definition_ids]
    rows = list(ChallengeOccurrence.objects.filter(
        goal_id__in=goal_ids, **{f"goal__{key}": value for key, value in scope.items()},
    ).order_by("pk").values(
        "pk", "goal_id", "goal__user_id", "starts_at", "ends_at", "created_at", "snapshot",
        "progress", "status", "completed_at", "retry_of_id", "closed_reason", "goal__starts_at", "goal__ends_at", "goal__timezone_name",
        "goal__repeat_weekly", "goal__repeat_days", "goal__catalog_gate_snapshot",
        "goal__catalog_gate_activity_id",
    )[:MAX_ACCEPTED_RECORDS + 1])
    foreign = QuestParticipant.objects.filter(quest_id=OuterRef("quest_id")).exclude(user__family_id=actor.family_id)
    legacy = list(QuestParticipant.objects.filter(
        user_id__in=child_ids, user__family_id=actor.family_id, user__is_active=True,
        user__is_staff=False, user__role="child", quest__definition_id__in=definition_ids,
    ).annotate(foreign_participant=Exists(foreign)).order_by("pk").values(
        "user_id", "quest__start_date", "quest__end_date", "quest__created_at",
        "quest__updated_at", "quest__status", "foreign_participant",
    )[:MAX_ACCEPTED_RECORDS + 1])
    if len(goals) + len(rows) + len(legacy) > MAX_ACCEPTED_RECORDS:
        return _withheld(result, "record_limit_exceeded", truncated=True)
    # A concurrent membership/role change after freezing IDs must not expose
    # that child's newly foreign saved outcomes in the aggregate groups.
    current_ids = set(children_in(actor.family).filter(is_staff=False, pk__in=child_ids).values_list("pk", flat=True))
    inconsistent_goal_ids = set(ChallengeGoal.objects.filter(
        user_id__in=current_ids, user__family_id=actor.family_id,
        catalog_definition_id__in=definition_ids, is_catalog=True,
    ).exclude(family_id=actor.family_id).values_list("user_id", flat=True))
    goals = [row for row in goals if row["user_id"] in current_ids]
    rows = [row for row in rows if row["goal__user_id"] in current_ids]
    legacy = [row for row in legacy if row["user_id"] in current_ids]
    goal_counts = Counter(row["user_id"] for row in goals)
    legacy_counts = Counter(row["user_id"] for row in legacy)
    ambiguous_users = {child_id for child_id in child_ids if goal_counts[child_id] + legacy_counts[child_id] > 1}
    states = defaultdict(list)
    occurrences_by_goal = defaultdict(list)
    for row in rows:
        occurrences_by_goal[row["goal_id"]].append(row)
    group_map = {row["policy"]: row for row in result["policy_groups"]}
    for attempts in occurrences_by_goal.values():
        chain = None if attempts[0]["goal__user_id"] in ambiguous_users else _retry_chain(attempts, as_of)
        attempt_states = []
        for row in attempts:
            state, outcome = _automatic_state(row, as_of)
            if chain is None:
                state = "unknown"
                outcome = ("mature_unknown" if row["ends_at"] is not None
                           and row["starts_at"] < row["ends_at"] <= as_of else "unknown_windows")
            attempt_states.append(state)
            group = group_map[_saved_policy(row, companion_ids, skill_id,
                                           valid_retry=chain is not None and row["retry_of_id"] is not None)]
            group["accepted_windows"] += 1
            group[outcome] += 1
        current = "unknown" if chain is None else (
            "completed" if "completed" in attempt_states else _automatic_state(chain[-1], as_of)[0])
        states[attempts[0]["goal__user_id"]].append(current)
    for row in legacy:
        state, outcome = _legacy_state(row, as_of)
        states[row["user_id"]].append(state)
        group_map["other_or_unknown"]["accepted_windows"] += 1
        group_map["other_or_unknown"][outcome] += 1
    for goal in goals:
        if goal["catalog_definition_id"] is None or not occurrences_by_goal[goal["pk"]]:
            states[goal["user_id"]].append("unknown")
    eligible, unknown = _current_eligibility(definition, child_ids, actor.family_id, as_of)
    for child_id in child_ids:
        accepted = states[child_id]
        if child_id not in current_ids or child_id in inconsistent_goal_ids or len(accepted) > 1:
            state = "unknown"
        elif accepted:
            state = accepted[0]
        elif child_id in unknown:
            state = "unknown"
        else:
            state = "ready" if eligible.get(child_id) else "locked"
        result["current_states"][state] += 1
    for group in result["policy_groups"]:
        denominator = group["mature_completed"] + group["mature_expired"]
        group["mature_denominator"] = denominator
        group["completion_rate"] = group["mature_completed"] / denominator if denominator else None
    result["status"] = "observations_available"
    return result
