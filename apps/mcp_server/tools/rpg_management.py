"""Household challenge controls, frozen expeditions and physical reward delivery."""
from django.utils import timezone

from apps.pets.expeditions import ExpeditionNotFound, ExpeditionService
from apps.pets.models import MountExpedition
from apps.pets.serializers import MountExpeditionSerializer
from apps.quests.controls import RetryCatalogBusy, retry_challenge as retry_saved_challenge, update_schedule
from apps.quests.goal_serializers import GoalScheduleSerializer
from apps.quests.goals import _pin_id, occurrence_payload
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, ChallengePin
from apps.rewards.models import RewardRedemption
from apps.rewards.services import RewardService

from ..context import get_current_user, require_parent, resolve_child_in_family, resolve_target_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..pagination import paginate_created_history
from ..retries import authorized_household, mutation_once
from ..rpg_management_schemas import (
    ChallengeAttemptResult, ClaimExpeditionIn, ClaimExpeditionResult,
    DeliverRewardRedemptionIn, ExpeditionPage, ExpeditionResult, GetExpeditionIn,
    GetRewardRedemptionIn, HouseholdRedemptionResult, ListExpeditionsIn, ListRewardRedemptionsIn,
    RetryChallengeIn, RewardRedemptionPage, StartExpeditionIn,
    UpdateChallengeScheduleIn, UpdateChallengeScheduleResult,
)
from ..server import tool
from ..shapes import redemption_to_dict, to_plain


def _target(user_id, *, allow_inactive_target=False):
    actor = get_current_user()
    if actor.role == "parent":
        if user_id is None:
            raise MCPValidationError(
                "Choose a child in your family with user_id.",
                field_errors={"user_id": ["Choose a child in your family."]},
            )
        target = resolve_child_in_family(actor, user_id)
    elif actor.role == "child":
        target = resolve_target_user(actor, user_id)
    else:
        raise MCPPermissionDenied("A parent or child account is required.")
    if not actor.is_active or (not allow_inactive_target and not target.is_active):
        raise MCPNotFoundError("The selected account is unavailable.")
    return actor, target


def _expeditions(target):
    return MountExpedition.objects.filter(mount__user=target).select_related("mount__species", "mount__potion")


def _expedition(target, expedition_id):
    row = _expeditions(target).filter(pk=expedition_id).first()
    if row is None:
        raise MCPNotFoundError("Expedition not found.")
    return row


def _expedition_payload(row, *, now=None):
    return to_plain(MountExpeditionSerializer(row, context={"expedition_as_of": now or timezone.now()}).data)


def _redemptions(target):
    return RewardRedemption.objects.filter(user=target).select_related(
        "user", "reward", "reward__item_definition", "item_definition_snapshot",
    )


def _redemption(target, redemption_id):
    row = _redemptions(target).filter(pk=redemption_id).first()
    if row is None:
        raise MCPNotFoundError("Redemption not found.")
    return row


@tool()
@safe_tool
def retry_challenge(params: RetryChallengeIn) -> ChallengeAttemptResult:
    """Explicitly retry one expired, unpaid personal catalog challenge.

    The service decides eligibility, freezes a fresh window and accepts only
    new qualifying facts. Repeating the same predecessor reuses its successor.
    This operation never replays sources or grants a reward by itself.
    """
    actor, target = _target(params.user_id)
    occurrence_id = int(params.challenge_id.split(":", 1)[1])
    with authorized_household(actor, target) as (parent_or_child, child):
        original = ChallengeOccurrence.objects.filter(
            pk=occurrence_id, goal__user=child, goal__family_id=parent_or_child.family_id,
        ).first()
        if original is None:
            raise MCPNotFoundError("Challenge not found.")
        try:
            successor, _ = retry_saved_challenge(parent_or_child, original.pk)
        except RetryCatalogBusy as error:
            raise MCPValidationError(str(error), code="retry_conflict", retryable=True) from error
        # Read the saved representation for both the new attempt and a replay;
        # timestamps otherwise retain different in-memory timezone offsets.
        successor.refresh_from_db()
        pin = ChallengePin.objects.filter(user=child).first()
        return to_plain(occurrence_payload(successor, _pin_id(pin) if pin else None))


@tool()
@safe_tool
def update_challenge_schedule(params: UpdateChallengeScheduleIn) -> UpdateChallengeScheduleResult:
    """Parent-only pause/resume or edits to a recurring goal's next weekly setup.

    Supply the saved expected_revision and a stable request_id. Current and
    already accepted future promises retain their snapshots. Metric, units and
    activity identity cannot change. Identical UUID retries return the original
    result; changed details conflict. Read list_challenges for current state.
    """
    require_parent()
    actor, target = _target(params.user_id)
    serializer = GoalScheduleSerializer(data=params.model_dump(
        exclude={"request_id", "goal_definition_id", "user_id"}, exclude_none=True, exclude_unset=True,
    ))
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    def change(fresh_actor, fresh_target):
        goal = ChallengeGoal.objects.filter(pk=params.goal_definition_id, user=fresh_target).first()
        if goal is None:
            raise MCPNotFoundError("Challenge not found.")
        goal._mcp_schedule_response = update_schedule(fresh_actor, goal.pk, data)
        return goal

    return mutation_once(
        actor=actor, target=target, operation="update_challenge_schedule", request_id=params.request_id,
        payload={"goal_definition_id": params.goal_definition_id, "changes": data},
        result_model=ChallengeGoal, create=change, serialize=lambda row: to_plain(row._mcp_schedule_response),
    )


@tool()
@safe_tool
def list_expeditions(params: ListExpeditionsIn) -> ExpeditionPage:
    """Read saved trips and frozen loot through a caller-bound history cursor.

    ready_only selects active trips whose saved return time has passed. Reads
    never start a trip, claim loot, advance a challenge, or award anything.
    """
    actor, target = _target(params.user_id, allow_inactive_target=True)
    with authorized_household(actor, target, allow_inactive_target=True) as (fresh_actor, child):
        now = timezone.now()
        queryset = _expeditions(child)
        if params.status:
            queryset = queryset.filter(status=params.status)
        if params.ready_only:
            queryset = queryset.filter(status=MountExpedition.Status.ACTIVE, returns_at__lte=now)
        rows, page = paginate_created_history(
            queryset, actor=fresh_actor, tool="list_expeditions",
            filters={"user_id": child.pk, "status": params.status, "ready_only": params.ready_only},
            limit=params.limit, cursor=params.cursor,
        )
        return {"user_id": child.pk, **page, "expeditions": [_expedition_payload(row, now=now) for row in rows]}


@tool()
@safe_tool
def get_expedition(params: GetExpeditionIn) -> ExpeditionResult:
    """Read a saved trip's current readiness and frozen loot, without claiming."""
    actor, target = _target(params.user_id, allow_inactive_target=True)
    with authorized_household(actor, target, allow_inactive_target=True) as (_actor, child):
        return _expedition_payload(_expedition(child, params.expedition_id))


@tool()
@safe_tool
def start_expedition(params: StartExpeditionIn) -> ExpeditionResult:
    """Launch a mount once, retaining the service-owned allowance and frozen loot.

    A stable request_id prevents launch retries from rerolling loot or creating
    another trip after a later day. The saved initial response is replayed;
    get_expedition reads current readiness/status. No early claim is possible.
    """
    actor, target = _target(params.user_id)

    def launch(_actor, child):
        try:
            return ExpeditionService.start(child, params.mount_id, params.tier)
        except ExpeditionNotFound as exc:
            raise MCPNotFoundError(str(exc)) from None

    return mutation_once(
        actor=actor, target=target, operation="start_expedition", request_id=params.request_id,
        payload={"mount_id": params.mount_id, "tier": params.tier},
        result_model=MountExpedition, target_field="mount__user_id",
        create=launch,
        serialize=_expedition_payload,
    )


@tool()
@safe_tool
def claim_expedition(params: ClaimExpeditionIn) -> ClaimExpeditionResult:
    """Explicitly claim a ready saved expedition through its server-owned receipt.

    Early claims fail without awards. Repeating the exact expedition ID awards
    nothing again and returns freshly_claimed=false with coins_awarded=0.
    Frozen loot is never rerolled by this tool.
    """
    actor, target = _target(params.user_id)
    with authorized_household(actor, target) as (_actor, child):
        _expedition(child, params.expedition_id)
        try:
            return to_plain(ExpeditionService.claim(child, params.expedition_id))
        except ExpeditionNotFound as exc:
            raise MCPNotFoundError(str(exc)) from None


@tool()
@safe_tool
def list_reward_redemptions(params: ListRewardRedemptionsIn) -> RewardRedemptionPage:
    """Read saved shop requests and their accepted promises, without approving."""
    actor, target = _target(params.user_id, allow_inactive_target=True)
    with authorized_household(actor, target, allow_inactive_target=True) as (fresh_actor, child):
        queryset = _redemptions(child)
        if params.status:
            queryset = queryset.filter(status=params.status)
        rows, page = paginate_created_history(
            queryset, actor=fresh_actor, tool="list_reward_redemptions",
            filters={"user_id": child.pk, "status": params.status}, limit=params.limit, cursor=params.cursor,
        )
        return {"user_id": child.pk, **page, "redemptions": [redemption_to_dict(row) for row in rows]}


@tool()
@safe_tool
def get_reward_redemption(params: GetRewardRedemptionIn) -> HouseholdRedemptionResult:
    """Read one child's saved reward promise, approval and physical-delivery state."""
    actor, target = _target(params.user_id, allow_inactive_target=True)
    with authorized_household(actor, target, allow_inactive_target=True) as (_actor, child):
        return redemption_to_dict(_redemption(child, params.redemption_id))


@tool()
@safe_tool
def deliver_reward_redemption(params: DeliverRewardRedemptionIn) -> HouseholdRedemptionResult:
    """Parent confirms an approved real-world reward was physically handed over.

    This records delivery only. Coin spending and any digital inventory grant
    remain the original request/approval's responsibility and never repeat.
    Repeating delivery of the same saved redemption changes nothing.
    """
    require_parent()
    actor, target = _target(params.user_id)
    with authorized_household(actor, target) as (parent, child):
        redemption = _redemption(child, params.redemption_id)
        return redemption_to_dict(RewardService.deliver(redemption, parent))
