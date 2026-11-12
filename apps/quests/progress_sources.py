"""New campaigns need an activity the saved-work pipeline actually produces.

Accomplishment awards do not replay the game loop. This is new-offer
admission only; accepted campaigns and their rewards remain intact.
"""


def has_progress_source(quest_type, trigger_filter):
    from .goals import FACT_TRIGGERS
    from .services import TRIGGER_DAMAGE

    filters = trigger_filter or {}
    allowed = filters.get("allowed_triggers") or FACT_TRIGGERS
    candidates = {
        trigger for trigger in allowed if trigger in FACT_TRIGGERS
        and (quest_type != "boss" or TRIGGER_DAMAGE.get(trigger, 0) > 0)
    }
    # These fields come from resolve_activity's trusted saved-source context.
    # One source must satisfy every active selector; separate sources that
    # each satisfy only one restriction cannot advance the campaign together.
    # Keep this map inside the fingerprinted admission function. It does not
    # reinterpret accepted facts or add evidence to previously saved work.
    selector_sources = {
        "project_id": {"clock_out", "project_complete", "milestone_complete"},
        "skill_category_id": {
            "clock_out", "chore_complete", "homework_complete", "habit_log",
            "movement_session", "project_complete", "milestone_complete",
        },
        "chore_ids": {"chore_complete"},
        "on_time": {"homework_complete"},
        "savings_goal_id": {"savings_goal_complete"},
    }
    for selector, sources in selector_sources.items():
        if filters.get(selector):
            candidates.intersection_update(sources)
    return bool(candidates)


def require_progress_source(quest_type, trigger_filter):
    if not has_progress_source(quest_type, trigger_filter):
        raise ValueError("Choose a saved-work activity that can advance this challenge.")


def require_current_progress_source(definition):
    """Call under the definition fence, after taxonomy admission.

    A changed filter can contain new taxonomy references. Do not adopt those
    references after their admission step, or take taxonomy locks in reverse
    order. A new request can admit the current offer in the normal order.
    """
    from .models import QuestDefinition

    current = QuestDefinition.objects.filter(pk=definition.pk).values("quest_type", "trigger_filter").first()
    if current is None:
        raise ValueError("This challenge's rules changed. Refresh and choose its current offer.")
    require_progress_source(current["quest_type"], current["trigger_filter"])
    if (current["quest_type"], current["trigger_filter"]) != (definition.quest_type, definition.trigger_filter):
        raise ValueError("This challenge's rules changed. Refresh and choose its current offer.")
