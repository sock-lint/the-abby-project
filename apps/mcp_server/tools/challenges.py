"""Modern challenge authoring and saved reward evidence, without synthetic progress."""
from types import SimpleNamespace
from typing import Any

from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError

from apps.quests.daily_bonus import get_daily_bonus_payload
from apps.quests.goal_serializers import GoalWriteSerializer
from apps.quests.goals import (
    _legacy_payload,
    create_goal,
    family_zone,
    occurrence_payload,
    set_pin,
)
from apps.quests.models import ChallengeActivity, ChallengeOccurrence, ChallengePin, Quest

from ..challenge_schemas import (
    CreateChallengeGoalIn,
    GetVoyagerFeedbackIn,
    ListChallengesIn,
    PinChallengeIn,
    PreviewChallengeGoalIn,
)
from ..context import get_current_user, require_parent, require_staff_parent, resolve_child_in_family, resolve_target_user
from ..errors import MCPPermissionDenied, MCPValidationError, safe_tool
from ..server import tool
from ..shapes import to_plain


def _validated_goal(params):
    parent = require_parent()
    child = resolve_child_in_family(parent, params.user_id)
    serializer = GoalWriteSerializer(
        data=params.model_dump(mode="json", exclude_none=True),
        context={"request": SimpleNamespace(user=parent)},
    )
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        raise MCPValidationError(str(exc.detail)) from None
    return parent, child, serializer.validated_data


@tool()
@safe_tool
def get_voyager_feedback(params: GetVoyagerFeedbackIn) -> dict[str, Any]:
    """Read the current family's bounded Voyager feedback aggregate as a staff parent.

    Requires the separate household mcp:read grant. This returns the same saved
    policy, current readiness and mature-outcome counts as the web report, with
    no child identities or reading details. It accepts no selectors and never
    starts, repairs, publishes, expires or rewards a challenge.
    """
    from apps.quests.voyager_feedback import voyager_feedback

    actor = require_staff_parent()
    try:
        return to_plain(voyager_feedback(actor))
    except DRFPermissionDenied as exc:
        raise MCPPermissionDenied(str(exc.detail)) from None


@tool()
@safe_tool
def list_challenges(params: ListChallengesIn) -> dict[str, Any]:
    """Read saved modern goals, legacy history and actual reward receipts.

    This audit never enrolls goals, advances periods, repairs facts, changes a
    pin or awards a reward. A child may read self; parents may select a child
    in their family. No private journal text or source contexts are returned.
    """
    target = resolve_target_user(get_current_user(), params.user_id)
    pin = ChallengePin.objects.filter(user=target).first()
    pin_id = None
    if pin:
        pin_id = (f"goal:{pin.occurrence_id}" if pin.occurrence_id else
                  f"legacy:{pin.legacy_quest_id}" if pin.legacy_quest_id else None)
    occurrences = ChallengeOccurrence.objects.filter(
        goal__user=target, goal__family_id=target.family_id,
    ).select_related("goal", "goal__catalog_definition").order_by("-starts_at", "-pk")
    selected = list(occurrences[:params.limit])
    results = [occurrence_payload(row, pin_id) for row in selected]
    if params.include_legacy:
        legacy = Quest.objects.filter(participants__user=target).select_related("definition").distinct()
        results.extend(_legacy_payload(row, pin_id) for row in legacy.order_by("-start_date", "-pk")[:params.limit])
    receipts = occurrences.filter(awarded_at__isnull=False).order_by("-awarded_at", "-pk")[:params.limit]
    activities = ChallengeActivity.objects.filter(
        user=target, voided=False, context__has_key="_receipt",
    ).order_by("-created_at", "-pk").values_list("context", flat=True)[:params.limit]
    return to_plain({
        "user_id": target.pk,
        "results": results,
        "pin": pin_id,
        "daily_bonus": get_daily_bonus_payload(target),
        "recent_receipts": [occurrence_payload(row, pin_id) for row in receipts],
        "challenge_receipts": [context["_receipt"] for context in activities],
        "saved_state_only": True,
    })


@tool()
@safe_tool
def preview_challenge_goal(params: PreviewChallengeGoalIn) -> dict[str, Any]:
    """Validate a parent goal without creating records or computing an award.

    Existing activities in this week or a custom period may count immediately
    when the parent later creates the goal. Preview does not backfill, enroll,
    process activities or reserve a reward. Copy the reviewed fields and supply
    a stable request_id to create_challenge_goal after user confirmation.
    """
    _, child, data = _validated_goal(params)
    return {"valid": True, "goal": to_plain(data), "timezone": str(family_zone(child)),
            "may_award_on_create": data["period"] in {"this_week", "custom"}, "saved": False}


@tool()
@safe_tool
def create_challenge_goal(params: CreateChallengeGoalIn) -> dict[str, Any]:
    """Create the reviewed same-family parent goal once, using a stable UUID.

    This can immediately count prior qualifying activities and award its
    promised rewards. The transport requires explicit user confirmation.
    Retries with the same request_id and details reuse the original goal;
    different details with that UUID are rejected. All progression and award
    receipts come from the existing challenge service.
    """
    parent, child, data = _validated_goal(params)
    occurrence = create_goal(parent, child, data)
    return to_plain(occurrence_payload(occurrence))


@tool()
@safe_tool
def pin_challenge(params: PinChallengeIn) -> dict[str, Any]:
    """Pin a saved challenge for self or a parent's same-family child. Awards nothing."""
    target = resolve_target_user(get_current_user(), params.user_id)
    return set_pin(target, params.challenge_id)


@tool()
@safe_tool
def unpin_challenge(params: PinChallengeIn) -> dict[str, Any]:
    """Clear a matching saved pin; progress, periods and reward promises stay intact."""
    target = resolve_target_user(get_current_user(), params.user_id)
    return set_pin(target, params.challenge_id, clear=True)
