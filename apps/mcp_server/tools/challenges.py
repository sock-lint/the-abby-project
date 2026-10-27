"""Modern challenge authoring and saved reward evidence, without synthetic progress."""
from types import SimpleNamespace
from typing import Any

from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError

from apps.quests.controls import control_context
from apps.quests.daily_bonus import get_daily_bonus_payload
from apps.quests.goal_serializers import GoalWriteSerializer
from apps.quests.goals import (
    _legacy_payload,
    _pin_id,
    create_goal,
    family_zone,
    occurrence_payload,
    set_pin,
)
from apps.quests.models import ChallengeActivity, ChallengeOccurrence, ChallengePin, Quest

from ..challenge_schemas import (
    ChallengeDetailResult,
    ChallengeListResult,
    CreateChallengeGoalIn,
    GetChallengeIn,
    GetVoyagerFeedbackIn,
    ListChallengesIn,
    PinChallengeIn,
    PreviewChallengeGoalIn,
)
from ..context import get_current_user, require_parent, require_staff_parent, resolve_child_in_family, resolve_target_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..pagination import paginate_created_history
from ..retries import authorized_household
from ..server import tool
from ..shapes import to_plain
from .rpg_management import _target as _household_target


def _validated_goal(params, parent, *, defer_current_eligibility=False):
    serializer = GoalWriteSerializer(
        data=params.model_dump(mode="json", exclude_none=True),
        context={"request": SimpleNamespace(user=parent), "defer_current_eligibility": defer_current_eligibility},
    )
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        raise MCPValidationError(str(exc.detail)) from None
    return serializer.validated_data


def _challenge_target(actor, requested_id):
    target = resolve_target_user(actor, requested_id)
    if target.pk != actor.pk and target.role != "child":
        raise MCPNotFoundError(f"User {requested_id} not found.")
    return target


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
        with authorized_household(actor, actor) as (fresh_actor, _):
            return to_plain(voyager_feedback(fresh_actor))
    except DRFPermissionDenied as exc:
        raise MCPPermissionDenied(str(exc.detail)) from None


def _saved_challenge_page(actor, target, params):
    controls = control_context(target)
    pin = ChallengePin.objects.filter(user=target).first()
    pin_id = _pin_id(pin) if pin else None
    occurrences = ChallengeOccurrence.objects.filter(
        goal__user=target, goal__family_id=target.family_id,
    ).select_related("goal", "goal__catalog_definition")
    pages, results = {}, []
    if params.source in {"all", "modern"}:
        selected, pages["modern"] = paginate_created_history(
            occurrences, actor=actor, tool="list_challenges", filters={"user_id": target.pk, "source": "modern"},
            limit=params.limit, cursor=params.cursor, order_field="starts_at",
        )
        results.extend(occurrence_payload(row, pin_id, controls=controls) for row in selected)
    if params.include_legacy and params.source in {"all", "legacy"}:
        legacy = Quest.objects.filter(participants__user=target).select_related("definition").distinct()
        selected, pages["legacy"] = paginate_created_history(
            legacy, actor=actor, tool="list_challenges", filters={"user_id": target.pk, "source": "legacy"},
            limit=params.limit, cursor=params.cursor, order_field="start_date",
        )
        results.extend(_legacy_payload(row, pin_id, observer_family_id=target.family_id) for row in selected)
    receipts = occurrences.filter(awarded_at__isnull=False).order_by("-awarded_at", "-pk")[:params.limit]
    activities = ChallengeActivity.objects.filter(
        user=target, voided=False, context__has_key="_receipt",
    ).order_by("-created_at", "-pk").values_list("context", flat=True)[:params.limit]
    return to_plain({
        "user_id": target.pk,
        "source": params.source,
        "pages": pages,
        "results": results,
        "pin": pin_id,
        # MCP keeps its established household-audit projection. Parent personal
        # bonuses remain available through the explicitly selected REST space.
        "daily_bonus": get_daily_bonus_payload(target) if target.role == "child" else None,
        "recent_receipts": [occurrence_payload(row, pin_id, controls=controls) for row in receipts],
        "challenge_receipts": [context["_receipt"] for context in activities],
        "saved_state_only": True,
    })


@tool()
@safe_tool
def list_challenges(params: ListChallengesIn) -> ChallengeListResult:
    """Read saved challenges and receipts; follow per-source pages for older rows.

    The default source=all returns recent modern and legacy rows as before.
    Each pages entry has its own signed next_cursor; continue using that cursor
    with source=modern or source=legacy. Recent receipts remain bounded summaries.
    Every page rechecks the same actor, family and target. This audit never
    enrolls, advances periods, repairs facts, changes pins, opens details or
    awards anything, and exposes no private journal text or source contexts.
    """
    actor = get_current_user()
    target = _challenge_target(actor, params.user_id)
    with authorized_household(actor, target, allow_inactive_target=True) as (fresh_actor, fresh_target):
        return _saved_challenge_page(fresh_actor, fresh_target, params)


@tool()
@safe_tool
def get_challenge(params: GetChallengeIn) -> ChallengeDetailResult:
    """Read one exact saved challenge, including attempts beyond recent history.

    Parents explicitly choose their same-family child; children read themselves.
    Returns frozen modern promises, actual saved receipts and current retry or
    schedule controls. It never enrolls, advances a period, repairs a fact, opens
    details, changes a pin or awards anything. Missing and foreign IDs match.
    """
    actor, target = _household_target(params.user_id, allow_inactive_target=True)
    kind, object_id = params.challenge_id.split(":", 1)
    with authorized_household(actor, target, allow_inactive_target=True) as (_actor, child):
        pin = ChallengePin.objects.filter(user=child).first()
        pin_id = _pin_id(pin) if pin else None
        if kind == "goal":
            row = ChallengeOccurrence.objects.filter(
                pk=int(object_id), goal__user=child, goal__family_id=child.family_id,
            ).select_related("goal", "goal__catalog_definition").first()
            if row is None:
                raise MCPNotFoundError("Challenge not found.")
            payload = occurrence_payload(row, pin_id, controls=control_context(child))
        else:
            row = Quest.objects.filter(pk=int(object_id), participants__user=child).select_related("definition").first()
            if row is None:
                raise MCPNotFoundError("Challenge not found.")
            payload = _legacy_payload(row, pin_id, observer_family_id=child.family_id)
        return to_plain({"user_id": child.pk, **payload, "saved_state_only": True})


@tool()
@safe_tool
def preview_challenge_goal(params: PreviewChallengeGoalIn) -> dict[str, Any]:
    """Validate a parent goal without creating records or computing an award.

    Existing activities in this week or a custom period may count immediately
    when the parent later creates the goal. Preview does not backfill, enroll,
    process activities or reserve a reward. Copy the reviewed fields and supply
    a stable request_id to create_challenge_goal after user confirmation.
    """
    parent = require_parent()
    child = resolve_child_in_family(parent, params.user_id)
    with authorized_household(parent, child) as (fresh_parent, fresh_child):
        data = _validated_goal(params, fresh_parent)
        return {"valid": True, "goal": to_plain(data), "timezone": str(family_zone(fresh_child)),
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
    parent = require_parent()
    child = resolve_child_in_family(parent, params.user_id)
    with authorized_household(parent, child) as (fresh_parent, fresh_child):
        data = _validated_goal(params, fresh_parent, defer_current_eligibility=True)
        try:
            occurrence = create_goal(fresh_parent, fresh_child, data, validate_current=True)
        except ValidationError as exc:
            raise MCPValidationError(str(exc.detail)) from None
        return to_plain(occurrence_payload(occurrence))


@tool()
@safe_tool
def pin_challenge(params: PinChallengeIn) -> dict[str, Any]:
    """Pin a saved challenge for self or a parent's same-family child. Awards nothing."""
    actor = get_current_user()
    target = _challenge_target(actor, params.user_id)
    with authorized_household(actor, target) as (_actor, fresh_target):
        return set_pin(fresh_target, params.challenge_id)


@tool()
@safe_tool
def unpin_challenge(params: PinChallengeIn) -> dict[str, Any]:
    """Clear a matching saved pin; progress, periods and reward promises stay intact."""
    actor = get_current_user()
    target = _challenge_target(actor, params.user_id)
    with authorized_household(actor, target) as (_actor, fresh_target):
        return set_pin(fresh_target, params.challenge_id, clear=True)
