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


def validate_trigger_filter(value):
    """Raise ValidationError if ``value`` isn't a valid ``trigger_filter`` dict.

    Accepts: missing, ``None``, or ``{}`` (no filter — match every trigger).
    Rejects: unknown keys, ``allowed_triggers`` values outside ``TriggerType``.
    """
    if not value:
        return
    if not isinstance(value, dict):
        raise ValidationError("trigger_filter must be an object.")

    unknown = set(value.keys()) - _KNOWN_FILTER_KEYS
    if unknown:
        raise ValidationError(
            f"Unknown trigger_filter keys: {sorted(unknown)}. "
            f"Valid keys: {sorted(_KNOWN_FILTER_KEYS)}",
        )

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
