"""Simulation-only catalog availability; no household reads or reward writers."""

from collections import Counter, defaultdict, deque
from copy import deepcopy
from datetime import date, timedelta
import math

from apps.achievements.services import SkillService


CHALLENGE_GATES_DEFAULTS = {"mode": "current", "start_date": "2026-01-01", "rules": []}
CHALLENGE_RULE_DEFAULTS = {
    "quest_id": None, "prerequisite_quest_id": None, "skill_id": None, "skill_level": 0,
    "min_days": 0, "available_from": None, "available_until": None,
}
CHALLENGE_GATES_LIMITS = {
    "mode": {"choices": ["current", "milestones", "milestone_tenure"]},
    "max_rules": 20, "skill_level": {"min": 0, "max": 6}, "min_days": {"min": 0, "max": 365},
    "date_format": "YYYY-MM-DD",
}
SCOPE = "One-off global catalog challenges compatible with this routine; not all app activities."
ASSUMPTIONS = [
    "Availability gates are anonymous simulation assumptions. No live challenge, saved goal, reward, calendar or child account is changed.",
    "Current mode ignores valid configured gate rules and retains authored challenge, skill and badge requirements. Milestones adds the selected completed-challenge and skill-level requirements using AND. Milestone plus tenure adds elapsed days since the child's first modeled visit.",
    "Day 1 is start_date and the child's first modeled visit. min_days=14 first permits offering on day 15; inactive days advance this elapsed clock. This is neither active-day tenure nor a consecutive-day streak.",
    "Calendar dates govern new offerings inclusively in both gated modes. An offered challenge keeps its full native duration, even after the offering window closes. Requirements are evaluated once before processing each new fact; past facts are never replayed and a predecessor completion cannot unlock its successor on the same fact.",
    "Visit availability is sampled at the start of each active visit, before that visit's activities. It covers only native-reachable one-off global catalog challenges compatible with the configured routine, including unconfigured challenges. It is not a screen impression, all-app availability, engagement or retention measure.",
    "Waiting visits have no currently available unfinished challenge in that subset and at least one structurally reachable challenge locked by a gate or native badge. Visits after exhaustion or expiration are separate. Inactive dates and blocked challenges are not extra playable content.",
    "Unlock and completion day percentiles are conditional on the trials that reached each event; reached counts include every trial. Unlocked means a native challenge window was actually offered by a new fact, not merely that its conditions became true on an inactive date.",
    "Only one-off global challenges can receive new gates; a repeatable challenge may serve as a predecessor after its first completion. Missed direct-predecessor windows and offerings, and definite native completed-challenge badge dead ends, block descendants rather than generating waiting visits. Other native badge paths remain optimistic; a viable alternative or repeatable path prevents a definite dead-end claim.",
    "The native finite target denominator is retained across gate modes. Structural reachability is optimistic and not a completion forecast; permanently unavailable paths, expired offerings and temporary locks are reported separately. Dates after the horizon and tenure beyond the horizon are temporary locks, not permanent losses.",
    "An authored null duration is an untimed one-time reading milestone. It never expires or restarts, and an unfinished accepted milestone remains available across absences. Its routine-capacity subset is bounded by the scenario horizon without creating a deadline.",
]
VISIT_METRICS = ("active_visits", "with_available_challenge", "without_available_challenge", "waiting_for_gate", "exhausted_or_expired")


def _date(value, key, *, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"challenge_gates.{key} must be a YYYY-MM-DD date.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"challenge_gates.{key} must be a real YYYY-MM-DD date.") from None
    if parsed.isoformat() != value:
        raise ValueError(f"challenge_gates.{key} must be a YYYY-MM-DD date.")
    return parsed


def normalize_challenge_gates(supplied):
    if not isinstance(supplied, dict) or set(supplied) - set(CHALLENGE_GATES_DEFAULTS):
        raise ValueError("Unknown challenge_gates configuration fields.")
    result = {**deepcopy(CHALLENGE_GATES_DEFAULTS), **supplied}
    if type(result["mode"]) is not str or result["mode"] not in CHALLENGE_GATES_LIMITS["mode"]["choices"]:
        raise ValueError("Invalid challenge_gates.mode.")
    start = _date(result["start_date"], "start_date")
    # A complete maximum scenario must fit the real date range.
    if start > date.max - timedelta(days=365):
        raise ValueError("challenge_gates.start_date must leave room for a complete 365-day scenario.")
    if type(result["rules"]) is not list or len(result["rules"]) > CHALLENGE_GATES_LIMITS["max_rules"]:
        raise ValueError("challenge_gates.rules must contain at most 20 rules.")
    rules, seen = [], set()
    for supplied_rule in result["rules"]:
        if not isinstance(supplied_rule, dict) or set(supplied_rule) - set(CHALLENGE_RULE_DEFAULTS):
            raise ValueError("Unknown challenge_gates rule fields.")
        rule = {**CHALLENGE_RULE_DEFAULTS, **supplied_rule}
        for key in ("quest_id", "prerequisite_quest_id", "skill_id"):
            value = rule[key]
            if value is None and key != "quest_id":
                continue
            if type(value) is not int or value <= 0:
                raise ValueError(f"challenge_gates.{key} must be a positive catalog ID.")
        if rule["quest_id"] in seen:
            raise ValueError("Duplicate challenge_gates quest_id.")
        seen.add(rule["quest_id"])
        for key in ("skill_level", "min_days"):
            limit = CHALLENGE_GATES_LIMITS[key]
            if type(rule[key]) is not int or not limit["min"] <= rule[key] <= limit["max"]:
                raise ValueError(f"Invalid challenge_gates.{key}.")
        if rule["skill_id"] is None and rule["skill_level"] != 0:
            raise ValueError("challenge_gates.skill_level requires skill_id.")
        lower = _date(rule["available_from"], "available_from", nullable=True)
        upper = _date(rule["available_until"], "available_until", nullable=True)
        if lower and upper and lower > upper:
            raise ValueError("challenge_gates.available_until must be on or after available_from.")
        rules.append(rule)
    result["rules"] = rules
    return result


class GateReferenceError(ValueError):
    """An entered gate references unavailable global content or a cyclic path."""


def _direct_predecessors(quest, rules):
    # An experimental prerequisite adds to the authored path; it never replaces it.
    return tuple(dict.fromkeys(pk for pk in (
        getattr(quest, "prerequisite_quest_id", None),
        rules.get(quest.pk, {}).get("prerequisite_quest_id"),
    ) if pk is not None))


def validate_challenge_gate_catalog(config, catalog):
    """Validate IDs and bounded prerequisite graphs against detached values only."""
    quest_ids = {q.pk for q in catalog.quests}
    repeatable_ids = {q.pk for q in catalog.quests if q.is_repeatable}
    rules = {}
    for rule in config["rules"]:
        if rule["quest_id"] not in quest_ids or (rule["prerequisite_quest_id"] is not None
                                                and rule["prerequisite_quest_id"] not in quest_ids):
            raise GateReferenceError("challenge_gates references a challenge outside the global catalog.")
        if rule["quest_id"] in repeatable_ids:
            raise GateReferenceError("challenge_gates can target only one-off global challenges.")
        if rule["skill_id"] is not None and rule["skill_id"] not in catalog.skills:
            raise GateReferenceError("challenge_gates references a skill outside the global catalog.")
        rules[rule["quest_id"]] = rule
    edges = {q.pk: _direct_predecessors(q, rules) for q in catalog.quests}
    dependents, remaining = defaultdict(set), {}
    for quest_id, predecessors in edges.items():
        if any(pk not in quest_ids for pk in predecessors):
            raise GateReferenceError("A prerequisite references a challenge outside the global catalog.")
        remaining[quest_id] = len(predecessors)
        for predecessor in predecessors:
            dependents[predecessor].add(quest_id)
    queue = deque(pk for pk, count in remaining.items() if count == 0)
    visited = 0
    while queue:
        visited += 1
        for dependent in dependents[queue.popleft()]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                queue.append(dependent)
    if visited != len(quest_ids):
        raise GateReferenceError("Authored and challenge_gates prerequisites must not contain a cycle.")


def challenge_gate_choices(catalog):
    return {
        "quests": [{"id": q.pk, "name": q.name, "is_repeatable": q.is_repeatable} for q in catalog.quests],
        "skills": [{"id": s.pk, "name": s.name, "category": s.category.name}
                   for s in catalog.skills.values() if getattr(s, "available_for_new_choices", True)],
    }


class ChallengeGates:
    def __init__(self, config, catalog):
        self.config = deepcopy(config)
        validate_challenge_gate_catalog(config, catalog)
        self.enabled = config["mode"] != "current"
        self.start = date.fromisoformat(config["start_date"])
        self.rules = {row["quest_id"]: row for row in self.config["rules"]} if self.enabled else {}
        self.catalog = catalog
        self.predecessors = {q.pk: _direct_predecessors(q, self.rules) for q in catalog.quests}
        # These depend only on the immutable policy/catalog, never trial state.
        # Shared two-parent DAG paths must not enumerate every traversal.
        self._earliest_days, self._temporal_paths = {}, {}
        self.unlock_days, self.completion_days = {}, {}
        self.visits = Counter()
        self.native_ids, self.reachable_ids = set(), set()
        self.native_finite_total = self.reachable_finite_total = 0

    def earliest_day(self, quest_id):
        if quest_id in self._earliest_days:
            return self._earliest_days[quest_id]
        rule = self.rules.get(quest_id, {})
        earliest = 1
        if rule.get("available_from"):
            earliest = max(earliest, (date.fromisoformat(rule["available_from"]) - self.start).days + 1)
        if self.config["mode"] == "milestone_tenure":
            earliest = max(earliest, rule.get("min_days", 0) + 1)
        for prerequisite in self.predecessors.get(quest_id, ()):
            earliest = max(earliest, self.earliest_day(prerequisite))
        self._earliest_days[quest_id] = earliest
        return earliest

    def last_day(self, quest_id):
        rule = self.rules.get(quest_id, {})
        return ((date.fromisoformat(rule["available_until"]) - self.start).days + 1
                if rule.get("available_until") else None)

    def temporal_possible(self, quest_id):
        if quest_id in self._temporal_paths:
            return self._temporal_paths[quest_id]
        last = self.last_day(quest_id)
        possible = ((last is None or last >= self.earliest_day(quest_id))
                    and all(self.temporal_possible(pk) for pk in self.predecessors.get(quest_id, ())))
        self._temporal_paths[quest_id] = possible
        return possible

    def prerequisites_met(self, quest, trial):
        if quest.required_badge_id and quest.required_badge_id not in trial.badges:
            return False
        if (getattr(quest, "prerequisite_quest_id", None) or getattr(quest, "required_skill_id", None)
                or getattr(quest, "required_skill_level", 0)) and not trial._milestones_met(quest):
            return False
        rule = self.rules.get(quest.pk, {})
        if rule.get("prerequisite_quest_id") and rule["prerequisite_quest_id"] not in trial.completed_quests:
            return False
        skill_id = rule.get("skill_id")
        return skill_id is None or (skill_id in trial.unlocked and SkillService.level_for_xp(trial.xp[skill_id]) >= rule["skill_level"])

    def potential_allows(self, quest, potential):
        return self.temporal_possible(quest.pk) and self.prerequisites_met(quest, potential)

    def can_offer(self, quest, trial):
        # Existing accepted promises are immutable through their complete window.
        window = trial.quest_windows.get(quest.pk)
        if window and (not quest.is_repeatable or trial.day < window["start"] + quest.duration_days):
            return True
        last = self.last_day(quest.pk)
        return (trial.day >= self.earliest_day(quest.pk) and (last is None or trial.day <= last)
                and self.prerequisites_met(quest, trial))

    def _known_expired(self, quest, trial):
        if quest.pk in trial.completed_quests:
            return False
        window = trial.quest_windows.get(quest.pk)
        if window is not None:
            return (not quest.is_repeatable and quest.duration_days is not None
                    and trial.day >= window["start"] + quest.duration_days)
        last = self.last_day(quest.pk)
        return last is not None and trial.day > last

    def _badge_rows(self, badge, trial):
        """Matched quests of a completed-challenge badge, or None for other badges."""
        if badge is None or badge.criteria_type != "quest_completed":
            return None  # Other native criteria retain optimistic reachability.
        criteria = badge.criteria_value or {}
        names = criteria.get("quest_names")
        if names is None:
            names = [criteria["quest_name"]] if criteria.get("quest_name") else []
        names = set(names)
        return [row for row in trial.quests if not names or row.name in names]

    def _badge_dead_end(self, badge, rows, trial, blocked):
        needed = int((badge.criteria_value or {}).get("count", 1))
        possible = sum(trial.counters[f"quest_completed:{row.pk}"] for row in rows)
        expired_evidence = False
        for row in rows:
            expired = self._known_expired(row, trial) or row.pk in blocked
            if expired:
                expired_evidence = True
            elif row.is_repeatable:
                return False  # A viable repeatable path may still satisfy any count.
            elif row.pk not in trial.completed_quests:
                possible += 1
        return expired_evidence and possible < needed

    def _reasons(self, quest, trial, blocked, state):
        # Accepted promises keep their original window independently of later
        # offering locks. Only a definite missing prerequisite can close a new path.
        if quest.pk in trial.quest_windows or quest.pk in trial.completed_quests:
            return []
        for prerequisite in self.predecessors.get(quest.pk, ()):
            if prerequisite in trial.completed_quests:
                continue
            prior = state["quests"][prerequisite]
            if self._known_expired(prior, trial):
                return ["prerequisite_window_expired" if prerequisite in trial.quest_windows else "prerequisite_offering_expired"]
            if prerequisite in blocked:
                return ["prerequisite_path_expired"]
        badge_id = quest.required_badge_id
        if not badge_id or badge_id in trial.badges or state["rows"].get(badge_id) is None:
            return []
        if badge_id not in state["dead_ends"]:
            state["dead_ends"][badge_id] = self._badge_dead_end(
                state["badges"][badge_id], state["rows"][badge_id], trial, blocked)
        return ["native_badge_prerequisite_expired"] if state["dead_ends"][badge_id] else []

    def blocking(self, trial):
        """Blocked reasons for every quest in this trial state.

        A quest is blocked only with a non-circular proof: a missed predecessor
        or a native completed-challenge badge that can no longer be earned.
        Cyclic badge paths therefore stay unproven. The rules only add
        blocked quests as others become blocked, so their least fixed point
        gives exactly that answer. A worklist re-checks only the quests whose
        predecessor or badge rows just became blocked, keeping each visit
        linear in the catalog for chains and shared badges alike. (A per-path
        depth-first search gave the same answer in roughly K! steps for K
        mutually gated chapters.)
        """
        quests = {q.pk: q for q in self.catalog.quests}
        quests.update((q.pk, q) for q in trial.quests)
        badges = {badge.pk: badge for badge in self.catalog.badges}
        rows, dependents, row_badges = {}, defaultdict(set), defaultdict(set)
        for quest in quests.values():
            for prerequisite in self.predecessors.get(quest.pk, ()):
                dependents[prerequisite].add(quest.pk)
            badge_id = quest.required_badge_id
            if not badge_id or badge_id in trial.badges:
                continue
            if badge_id not in rows:
                rows[badge_id] = self._badge_rows(badges.get(badge_id), trial)
            for row in rows[badge_id] or ():
                dependents[row.pk].add(quest.pk)
                row_badges[row.pk].add(badge_id)
        state = {"quests": quests, "badges": badges, "rows": rows, "dead_ends": {}}
        blocked = set()
        queue, queued = deque(quests), set(quests)
        while queue:
            pk = queue.popleft()
            queued.discard(pk)
            if pk in blocked or not self._reasons(quests[pk], trial, blocked, state):
                continue
            blocked.add(pk)
            for badge_id in row_badges.get(pk, ()):
                state["dead_ends"].pop(badge_id, None)
            for dependent in dependents.get(pk, ()):
                if dependent not in blocked and dependent not in queued:
                    queue.append(dependent)
                    queued.add(dependent)
        # Each blocked quest reports its first applicable reason under the final set.
        state["dead_ends"] = {}
        return {pk: self._reasons(quests[pk], trial, blocked, state) for pk in blocked}

    def blocked_reasons(self, quest, trial, blocking=None):
        blocking = self.blocking(trial) if blocking is None else blocking
        return blocking.get(quest.pk, [])

    def visit(self, trial):
        """Sample once before the active visit; this method never materializes goals."""
        self.visits["active_visits"] += 1
        available = waiting = False
        blocking = None
        for quest in trial.quests:
            if quest.is_repeatable or quest.pk not in self.native_ids or quest.pk in trial.completed_quests:
                continue
            window = trial.quest_windows.get(quest.pk)
            if window:
                available |= not window["paid"] and (quest.duration_days is None
                                                     or trial.day < window["start"] + quest.duration_days)
                continue
            if self.can_offer(quest, trial):
                available = True
            elif quest.pk in self.reachable_ids and (self.last_day(quest.pk) is None or trial.day <= self.last_day(quest.pk)):
                blocking = self.blocking(trial) if blocking is None else blocking
                if not self.blocked_reasons(quest, trial, blocking):
                    waiting = True
        self.visits["with_available_challenge"] += int(available)
        self.visits["without_available_challenge"] += int(not available)
        self.visits["waiting_for_gate"] += int(not available and waiting)
        self.visits["exhausted_or_expired"] += int(not available and not waiting)

    def target_report(self, quest, trial, blocking=None):
        window = trial.quest_windows.get(quest.pk)
        last = self.last_day(quest.pk)
        completed = quest.pk in self.completion_days
        expired = not completed and ((window is not None and quest.duration_days is not None
                                     and trial.day >= window["start"] + quest.duration_days)
                                    or (window is None and last is not None and trial.day > last))
        native = quest.pk in self.native_ids
        reachable = quest.pk in self.reachable_ids
        reasons = []
        blocked_reasons = self.blocked_reasons(quest, trial, blocking) if native and not completed else []
        if not native:
            reasons.append("outside_native_routine_subset")
        elif not self.temporal_possible(quest.pk):
            reasons.append("offering_window_cannot_be_reached")
        elif not reachable:
            reasons.append("prerequisite_skill_or_native_badge_path_unreachable")
        return {"quest_id": quest.pk, "name": quest.name, "in_native_subset": native, "reachable": reachable,
                "unreachable_reasons": reasons, "unlock_day": self.unlock_days.get(quest.pk),
                "completion_day": self.completion_days.get(quest.pk), "expired": expired,
                "blocked": bool(blocked_reasons) and not expired, "blocked_reasons": blocked_reasons,
                "temporarily_locked": native and reachable and not completed and window is None and not expired and not blocked_reasons
                                      and not self.can_offer(quest, trial)}

    def report(self, trial):
        blocking = self.blocking(trial)
        return {"targets": [self.target_report(q, trial, blocking) for q in self.catalog.quests if not q.is_repeatable],
                "visits": {key: self.visits[key] for key in VISIT_METRICS},
                "native_finite_total": self.native_finite_total,
                "gate_reachable_finite_total": self.reachable_finite_total,
                "gate_unreachable_finite_total": self.native_finite_total - self.reachable_finite_total}


def _percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def aggregate_challenge_gates(runs, config):
    reports = [run["challenge_gates"] for run in runs]
    targets = []
    for index, first in enumerate(reports[0]["targets"]):
        rows = [report["targets"][index] for report in reports]
        target = {key: first[key] for key in ("quest_id", "name", "in_native_subset", "reachable", "unreachable_reasons")}
        for event, label in (("unlock_day", "unlock"), ("completion_day", "completion")):
            days = [row[event] for row in rows if row[event] is not None]
            target["unlocked_trials" if label == "unlock" else "completed_trials"] = len(days)
            for quantile, fraction in (("p10", .1), ("p50", .5), ("p90", .9)):
                target[f"{quantile}_{label}_days"] = _percentile(days, fraction)
        target["temporarily_locked_trials"] = sum(row["temporarily_locked"] for row in rows)
        target["expired_trials"] = sum(row["expired"] for row in rows)
        target["blocked_trials"] = sum(row["blocked"] for row in rows)
        target["blocked_reasons"] = sorted({reason for row in rows for reason in row["blocked_reasons"]})
        targets.append(target)
    return {"mode": config["mode"], "config": deepcopy(config), "assumptions": list(ASSUMPTIONS), "scope": SCOPE,
            "trials": len(runs), "targets": targets,
            "visits": {f"{key}_p50": _percentile([row["visits"][key] for row in reports], .5) for key in VISIT_METRICS},
            **{key: reports[0][key] for key in ("native_finite_total", "gate_reachable_finite_total", "gate_unreachable_finite_total")}}
