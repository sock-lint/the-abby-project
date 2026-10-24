"""Validators for quest configuration.

Centralized here so the model's ``clean()``, the DRF serializer, and the MCP
tool all share one implementation — a typo like ``allowed_trigger`` (missing
``s``) would otherwise silently accept every trigger.
"""

from django.core.exceptions import ValidationError

from apps.rpg.constants import TriggerType

# Keys the code actually reads today. Authorable-but-dead keys (like the
# previously-accepted ``streak_target`` and ``perfect_day_target``) were
# removed in the 2026-04-23 review — they let parents author quests that
# silently never made progress. If a future feature adds new filter keys,
# wire the reader in QuestService.record_progress AND add the key here in
# the same change so the validator and the runtime stay in lockstep.
_KNOWN_FILTER_KEYS = frozenset(
    {
        "allowed_triggers",
        "project_id",
        "skill_category_id",
        "chore_ids",
        "on_time",
        "savings_goal_id",
    }
)
_CATALOG_POLICY_KEYS = frozenset({"distinct_active_days", "reward_policy_version"})


def validate_untimed_reading(definition):
    """No deadline is a native promise, scoped to supported one-time reading."""
    if definition.duration_days is not None:
        return
    # Shared family challenges are parent-assigned timed campaigns and never
    # enroll automatically, so they cannot carry an open-ended promise.
    if (not definition.is_system or definition.created_by_id is not None or definition.is_repeatable
            or getattr(definition, "is_cooperative", False) or definition.quest_type != "collection"
            or definition.trigger_filter != {"allowed_triggers": ["reading_logged"]}):
        raise ValidationError({"duration_days": (
            "No deadline is supported only for one-time global Reading Adventure collections."
        )})


def validate_trigger_filter(value, *, allow_catalog_policy=False):
    """Raise ValidationError if ``value`` isn't a valid ``trigger_filter`` dict.

    Accepts: missing, ``None``, or ``{}`` (no filter — match every trigger).
    Rejects: unknown keys, ``allowed_triggers`` values outside ``TriggerType``.
    """
    if not value:
        return
    if not isinstance(value, dict):
        raise ValidationError("trigger_filter must be an object.")

    known = _KNOWN_FILTER_KEYS | (_CATALOG_POLICY_KEYS if allow_catalog_policy else frozenset())
    unknown = set(value.keys()) - known
    if unknown:
        raise ValidationError(
            f"Unknown trigger_filter keys: {sorted(unknown)}. "
            f"Valid keys: {sorted(known)}",
        )

    if "distinct_active_days" in value and type(value["distinct_active_days"]) is not bool:
        raise ValidationError("trigger_filter.distinct_active_days must be a boolean.")
    if "reward_policy_version" in value and (
        type(value["reward_policy_version"]) is not int or value["reward_policy_version"] != 2
    ):
        raise ValidationError("trigger_filter.reward_policy_version must be 2.")
    if value.get("distinct_active_days") is True and value.get("reward_policy_version") != 2:
        raise ValidationError("Distinct active days require reward_policy_version 2.")

    allowed_triggers = value.get("allowed_triggers")
    if allowed_triggers is not None:
        if not isinstance(allowed_triggers, list):
            raise ValidationError(
                "trigger_filter.allowed_triggers must be a list of trigger strings.",
            )
        valid = {t.value for t in TriggerType}
        bad = [t for t in allowed_triggers if t not in valid]
        if bad:
            raise ValidationError(
                f"Unknown trigger_filter.allowed_triggers values: {bad}. "
                f"Valid triggers: {sorted(valid)}",
            )


def validate_reward_policy(definition):
    """The opt-in v2 snapshot policy belongs to timed individual catalog collections."""
    filters = definition.trigger_filter or {}
    if filters.get("reward_policy_version") != 2:
        return
    if (not definition.is_system or definition.created_by_id is not None
            or definition.is_cooperative or definition.quest_type != "collection"
            or definition.duration_days is None):
        raise ValidationError({"trigger_filter": "Reward policy v2 requires a timed individual global collection."})
    if filters.get("distinct_active_days") is True and definition.target_value > definition.duration_days:
        raise ValidationError({"target_value": "Distinct active-day targets cannot exceed the window's days."})
