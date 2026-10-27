"""New campaigns need an activity the saved-work pipeline actually produces.

Accomplishment awards do not replay the game loop. This is new-offer
admission only; accepted campaigns and their rewards remain intact.
"""


def has_progress_source(quest_type, trigger_filter):
    from .goals import FACT_TRIGGERS
    from .services import TRIGGER_DAMAGE

    allowed = (trigger_filter or {}).get("allowed_triggers") or FACT_TRIGGERS
    return any(
        trigger in FACT_TRIGGERS
        and (quest_type != "boss" or TRIGGER_DAMAGE.get(trigger, 0) > 0)
        for trigger in allowed
    )


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
