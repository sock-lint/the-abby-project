"""MovementSessionService — self-reported physical-activity logging.

Pipeline per ``log_session`` call:

1. Bump the per-user per-day counter (read-modify-write under
   ``select_for_update``). Returns the PRE-increment count so callers can
   gate on the old value (first log returns 0, second returns 1, etc.).
2. Write the ``MovementSession`` row.
3. If the prior count was below ``DAILY_REWARD_LIMIT``: distribute the
   XP pool via the MovementType's parent-authored skill tags, then call
   ``GameLoopService.on_task_completed`` so streak / drops / quest
   progress all count.

The counter survives ``MovementSession.delete()`` so a log → delete → log
cycle on the same day cannot re-arm the reward window — matches the
soft-farm doctrine used by ``CreationService``.
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.movement.models import (
    MovementDailyCounter,
    MovementSession,
    MovementType,
    MovementTypeSkillTag,
)
from config.services import bump_daily_counter

logger = logging.getLogger(__name__)

PHYSICAL_CATEGORY_NAME = "Physical"


class MovementSessionError(Exception):
    """Raised when a session cannot be logged (bad type, bad inputs, etc.)."""


class MovementTypeError(Exception):
    """Raised when a user-authored MovementType cannot be created or removed."""


class MovementSessionService:
    DAILY_REWARD_LIMIT = 3
    INTENSITY_MULTIPLIER = {
        MovementSession.Intensity.LOW: 0.5,
        MovementSession.Intensity.MEDIUM: 1.0,
        MovementSession.Intensity.HIGH: 1.5,
    }
    XP_PER_10_MIN = 5
    # Hard cap to bound any single-session XP regardless of input. 4h covers
    # every realistic continuous activity (a marathon, a tournament game).
    MAX_DURATION_MINUTES = 240
    MIN_DURATION_MINUTES = 1

    @classmethod
    def compute_xp_pool(cls, duration_minutes: int, intensity: str) -> int:
        """Return the XP pool for a given duration + intensity.

        Pool = ``floor(duration_minutes / 10) × XP_PER_10_MIN × intensity_mult``.
        Anything under 10 minutes earns zero XP — the floor is deliberate so
        a 5-minute warm-up isn't equivalent to a real session.
        """
        clamped = max(0, min(int(duration_minutes), cls.MAX_DURATION_MINUTES))
        ten_minute_blocks = clamped // 10
        mult = cls.INTENSITY_MULTIPLIER.get(intensity, 1.0)
        return int(ten_minute_blocks * cls.XP_PER_10_MIN * mult)

    @classmethod
    @transaction.atomic
    def log_session(
        cls,
        user,
        *,
        movement_type: MovementType,
        duration_minutes: int,
        intensity: str = MovementSession.Intensity.MEDIUM,
        occurred_at=None,
        notes: str = "",
        distance=None,
        distance_unit="mi",
        client_request_id=None,
    ) -> MovementSession:
        """Log a session, conditionally distribute XP + drop + quest progress.

        Raises ``MovementSessionError`` for invalid inputs. Always writes
        the session row — only the reward path is gated by the daily cap.
        """
        if not movement_type.is_active:
            raise MovementSessionError(
                f"Movement type '{movement_type.name}' is no longer active.",
            )
        if duration_minutes < cls.MIN_DURATION_MINUTES:
            raise MovementSessionError(
                f"Duration must be at least {cls.MIN_DURATION_MINUTES} minute.",
            )
        if intensity not in cls.INTENSITY_MULTIPLIER:
            raise MovementSessionError(
                f"Unknown intensity '{intensity}'. Use low / medium / high.",
            )

        clamped_minutes = min(int(duration_minutes), cls.MAX_DURATION_MINUTES)
        from decimal import Decimal, InvalidOperation
        from django.contrib.auth import get_user_model
        # Serialize requests and all downstream goal/XP writes for this child.
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        if distance_unit not in ("mi", "km"):
            raise MovementSessionError("Distance unit must be mi or km.")
        distance_meters = None
        if distance is not None:
            try:
                value = Decimal(str(distance))
                if not value.is_finite() or value <= 0 or value > 1000 or value.as_tuple().exponent < -3:
                    raise InvalidOperation
                distance_meters = (value * Decimal("1609.344" if distance_unit == "mi" else "1000")).quantize(Decimal("0.001"))
            except (InvalidOperation, ValueError):
                raise MovementSessionError("Distance must be positive, finite, and have at most 3 decimal places.")
        clean_notes = (notes or "")[:200]
        if client_request_id is not None:
            existing = MovementSession.objects.filter(user=user, client_request_id=client_request_id).first()
            if existing is not None:
                if (existing.movement_type_id != movement_type.pk or existing.duration_minutes != clamped_minutes
                        or existing.intensity != intensity or existing.distance_meters != distance_meters
                        or existing.distance_unit != distance_unit or existing.notes != clean_notes):
                    raise MovementSessionError("This request was already saved with different session details.")
                from apps.quests.models import ChallengeActivity
                fact = ChallengeActivity.objects.filter(user=user, source_type="movement_session", source_id=str(existing.pk)).first()
                existing._challenge_receipts = [fact.context["_receipt"]] if fact and fact.context.get("_receipt") else []
                return existing
        from apps.quests.activity import household_timezone
        day = timezone.localdate(occurred_at or timezone.now(), timezone=household_timezone(user))

        prior_count = bump_daily_counter(MovementDailyCounter, user, day)
        is_xp_eligible = prior_count < cls.DAILY_REWARD_LIMIT

        session = MovementSession.objects.create(
            user=user,
            movement_type=movement_type,
            duration_minutes=clamped_minutes,
            distance_meters=distance_meters,
            distance_unit=distance_unit,
            client_request_id=client_request_id,
            intensity=intensity,
            occurred_on=day,
            notes=clean_notes,
        )

        if is_xp_eligible:
            cls._award_session(user, session)

        from apps.rpg.services import GameLoopService
        activity_result = GameLoopService.record_challenge_activity(user, "movement_session", {"session_id": session.pk})
        session._challenge_receipts = activity_result.get("challenge_receipts", [])

        return session

    @classmethod
    def _award_session(cls, user, session: MovementSession) -> None:
        """Distribute XP + fire game loop for a within-cap session."""
        from apps.achievements.services import AwardService
        from apps.rpg.constants import TriggerType
        from apps.rpg.services import safe_game_loop_call

        xp_pool = cls.compute_xp_pool(session.duration_minutes, session.intensity)
        if xp_pool > 0:
            tags = session.movement_type.skill_tags.select_related("skill")
            try:
                AwardService.grant(
                    user,
                    xp_tags=tags,
                    xp=xp_pool,
                    xp_source_label=f"Movement: {session.movement_type.name}",
                )
            except Exception:
                logger.exception(
                    "Movement XP award failed for user %s, session %s",
                    user.pk, session.pk,
                )
            session.xp_awarded = xp_pool
            session.save(update_fields=["xp_awarded"])

        safe_game_loop_call(
            user,
            TriggerType.MOVEMENT_SESSION,
            {
                "session_id": session.id,
                "movement_type_id": session.movement_type_id,
                "duration_minutes": session.duration_minutes,
                **({"distance_meters": str(session.distance_meters)} if session.distance_meters is not None else {}),
                "intensity": session.intensity,
            },
            log=logger,
        )


class MovementTypeService:
    """User-authored ``MovementType`` rows.

    Child-serve: a child picks a name + icon + primary Physical skill (and
    optionally a secondary). The row becomes globally visible in the type
    picker and is tagged against the Physical skill tree via
    ``MovementTypeSkillTag`` at 70/30 weight when both skills are set, or
    100% to primary when solo. No approval step — matches the self-reported
    doctrine that already governs ``MovementSession``.

    Anti-spam: ``DAILY_CREATE_LIMIT`` caps how many types a single user can
    author per local day. The unique ``name`` constraint naturally blocks
    cheap re-submissions of the same activity.
    """

    DAILY_CREATE_LIMIT = 5
    MAX_NAME_LEN = 64
    MAX_ICON_LEN = 10

    PRIMARY_WEIGHT_WITH_SECONDARY = 7
    SECONDARY_WEIGHT = 3
    PRIMARY_WEIGHT_SOLO = 1

    @classmethod
    def _validate_physical_skill(cls, skill_id, label):
        """Return the Skill row if it lives in the Physical category.

        Imported here to avoid a module-load cycle with achievements.
        """
        from apps.achievements.models import Skill

        try:
            skill = Skill.objects.select_related("category").get(pk=skill_id)
        except Skill.DoesNotExist as exc:
            raise MovementTypeError(f"{label} skill not found.") from exc
        if skill.category.name != PHYSICAL_CATEGORY_NAME:
            raise MovementTypeError(
                f"{label} skill must belong to the Physical category.",
            )
        return skill

    @classmethod
    def _unique_slug(cls, base: str) -> str:
        """Slugify and auto-suffix until unique."""
        root = slugify(base)[: MovementType._meta.get_field("slug").max_length - 6]
        if not root:
            root = "activity"
        candidate = root
        suffix = 2
        while MovementType.objects.filter(slug=candidate).exists():
            candidate = f"{root}-{suffix}"
            suffix += 1
        return candidate

    @classmethod
    @transaction.atomic
    def create_type(
        cls,
        user,
        *,
        name: str,
        icon: str = "",
        default_intensity: str = MovementType.Intensity.MEDIUM,
        primary_skill_id: int,
        secondary_skill_id: int | None = None,
    ) -> MovementType:
        """Create a user-authored MovementType + its skill tags.

        Raises ``MovementTypeError`` on bad inputs (empty name, non-Physical
        skill, duplicate primary/secondary, daily limit reached, duplicate
        name).
        """
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise MovementTypeError("Name is required.")
        if len(cleaned_name) > cls.MAX_NAME_LEN:
            raise MovementTypeError(
                f"Name must be {cls.MAX_NAME_LEN} characters or fewer.",
            )

        if default_intensity not in {i.value for i in MovementType.Intensity}:
            raise MovementTypeError(
                f"Unknown intensity '{default_intensity}'. Use low / medium / high.",
            )

        if not primary_skill_id:
            raise MovementTypeError("Primary skill is required.")
        if secondary_skill_id and secondary_skill_id == primary_skill_id:
            raise MovementTypeError(
                "Primary and secondary skills must be different.",
            )

        from django.contrib.auth import get_user_model
        from apps.achievements.models import Skill
        from apps.rpg.taxonomy_references import admit_references
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        admit_references(Skill, [primary_skill_id] + ([secondary_skill_id] if secondary_skill_id else []),
                         error_type=MovementTypeError)
        primary = cls._validate_physical_skill(primary_skill_id, "Primary")
        secondary = None
        if secondary_skill_id:
            secondary = cls._validate_physical_skill(secondary_skill_id, "Secondary")

        today = timezone.localdate()
        daily_count = MovementType.objects.filter(
            created_by=user, created_at__date=today,
        ).count()
        if daily_count >= cls.DAILY_CREATE_LIMIT:
            raise MovementTypeError(
                f"Daily limit reached ({cls.DAILY_CREATE_LIMIT} new activities per day).",
            )

        if MovementType.objects.filter(name__iexact=cleaned_name).exists():
            raise MovementTypeError(
                f"An activity called '{cleaned_name}' already exists.",
            )

        slug = cls._unique_slug(cleaned_name)
        cleaned_icon = (icon or "")[: cls.MAX_ICON_LEN]

        try:
            movement_type = MovementType.objects.create(
                name=cleaned_name,
                slug=slug,
                icon=cleaned_icon,
                default_intensity=default_intensity,
                created_by=user,
            )
        except IntegrityError as exc:
            # Race against the name-uniqueness check above — surface the
            # same user-facing message.
            raise MovementTypeError(
                f"An activity called '{cleaned_name}' already exists.",
            ) from exc

        if secondary is not None:
            MovementTypeSkillTag.objects.create(
                movement_type=movement_type,
                skill=primary,
                xp_weight=cls.PRIMARY_WEIGHT_WITH_SECONDARY,
            )
            MovementTypeSkillTag.objects.create(
                movement_type=movement_type,
                skill=secondary,
                xp_weight=cls.SECONDARY_WEIGHT,
            )
        else:
            MovementTypeSkillTag.objects.create(
                movement_type=movement_type,
                skill=primary,
                xp_weight=cls.PRIMARY_WEIGHT_SOLO,
            )

        return movement_type
