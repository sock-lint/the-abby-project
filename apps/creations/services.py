"""CreationService — child-authored "I made a thing" business logic.

The flow:

1. ``log_creation`` writes the Creation row, gates XP + game loop to the
   first 2 per user per local day (anti-farm), and emits a ChronicleEntry.
2. ``submit_for_bonus`` flips status to PENDING and notifies parents.
3. ``approve_bonus`` distributes the parent-granted bonus XP pool across
   either parent-authored tags or a fallback to the child's primary skill.
4. ``reject_bonus`` stamps REJECTED without reversing baseline XP.

The baseline XP pool is fixed at 10 — 100% to primary when solo, 70/30
split when a secondary is set. The parent bonus defaults to 15.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.creations.constants import CREATIVE_CATEGORY_NAMES
from apps.creations.models import Creation, CreationBonusSkillTag, CreationDailyCounter
from config.services import bump_daily_counter

logger = logging.getLogger(__name__)


class CreationError(Exception):
    """Raised when a Creation cannot be logged (non-creative skill, etc.)."""


@dataclass
class _CreationTag:
    """Shim matching the ``.skill`` + ``.xp_weight`` duck-type expected by
    ``SkillService.distribute_tagged_xp``. Lets the service reuse the
    weighted-XP distribution for the baseline pool without a DB fan-out
    table (the primary + secondary skill FKs on the Creation row ARE the
    baseline tag set).
    """

    skill: object
    xp_weight: int


class CreationService:
    BASELINE_XP = 10
    # Weights for the baseline pool split when both primary and secondary
    # skills are set — 7 + 3 over 10 gives 70/30.
    PRIMARY_WEIGHT = 7
    SECONDARY_WEIGHT = 3
    DAILY_XP_LIMIT = 2
    DEFAULT_BONUS_XP = 15

    @classmethod
    def _assert_creative_skill(cls, skill) -> None:
        if skill.category.name not in CREATIVE_CATEGORY_NAMES:
            raise CreationError(
                f"Skill '{skill.name}' is not in a creative category "
                f"(got '{skill.category.name}'). Allowed: "
                f"{', '.join(CREATIVE_CATEGORY_NAMES)}"
            )

    @classmethod
    def _load_and_validate_skills(cls, primary_skill_id: int, secondary_skill_id: Optional[int]):
        from apps.achievements.models import Skill

        if secondary_skill_id and secondary_skill_id == primary_skill_id:
            raise CreationError("Primary and secondary skill must differ.")

        try:
            primary = Skill.objects.select_related("category").get(pk=primary_skill_id)
        except Skill.DoesNotExist as exc:
            raise CreationError(f"Primary skill {primary_skill_id} not found.") from exc
        cls._assert_creative_skill(primary)

        secondary = None
        if secondary_skill_id:
            try:
                secondary = Skill.objects.select_related("category").get(pk=secondary_skill_id)
            except Skill.DoesNotExist as exc:
                raise CreationError(
                    f"Secondary skill {secondary_skill_id} not found."
                ) from exc
            cls._assert_creative_skill(secondary)

        return primary, secondary

    @classmethod
    def _build_baseline_tags(cls, primary, secondary):
        if secondary is None:
            return [_CreationTag(skill=primary, xp_weight=cls.PRIMARY_WEIGHT + cls.SECONDARY_WEIGHT)]
        return [
            _CreationTag(skill=primary, xp_weight=cls.PRIMARY_WEIGHT),
            _CreationTag(skill=secondary, xp_weight=cls.SECONDARY_WEIGHT),
        ]

    @classmethod
    @transaction.atomic
    def log_creation(
        cls,
        user,
        *,
        image,
        audio=None,
        caption: str = "",
        primary_skill_id: int,
        secondary_skill_id: Optional[int] = None,
    ) -> Creation:
        """Create a Creation + (conditionally) award XP, drop, quest progress.

        Gate: only the first ``DAILY_XP_LIMIT`` per user per local day
        award XP and fire the game loop. Rows beyond the cap still write
        (for the Sketchbook/Yearbook surfaces) but silently skip the reward
        path. See docstring of ``_count_today`` for the soft-farm caveat.
        """
        primary, secondary = cls._load_and_validate_skills(
            primary_skill_id, secondary_skill_id
        )

        day = timezone.localdate()
        prior_count = bump_daily_counter(CreationDailyCounter, user, day)
        is_xp_eligible = prior_count < cls.DAILY_XP_LIMIT

        creation = Creation.objects.create(
            user=user,
            image=image,
            audio=audio,
            caption=(caption or "")[:200],
            occurred_on=day,
            primary_skill=primary,
            secondary_skill=secondary,
        )

        if is_xp_eligible:
            cls._award_baseline(user, creation, primary, secondary)

        # Emit Chronicle entry regardless of XP eligibility — the proud-display
        # track isn't gated by the anti-farm cap.
        cls._emit_chronicle(user, creation, primary, day)

        return creation

    @classmethod
    def _award_baseline(cls, user, creation: Creation, primary, secondary) -> None:
        """Distribute baseline XP + fire game loop for a first-of-day creation."""
        from apps.achievements.services import AwardService
        from apps.rpg.constants import TriggerType
        from apps.rpg.services import GameLoopService

        tags = cls._build_baseline_tags(primary, secondary)
        try:
            AwardService.grant(
                user,
                xp_tags=tags,
                xp=cls.BASELINE_XP,
                xp_source_label="Creation",
            )
        except Exception:
            logger.exception(
                "Creation baseline XP award failed for user %s, creation %s",
                user.pk, creation.pk,
            )
        creation.xp_awarded = cls.BASELINE_XP
        creation.save(update_fields=["xp_awarded"])

        try:
            GameLoopService.on_task_completed(
                user,
                TriggerType.CREATION_LOGGED,
                {"creation_id": creation.id},
            )
        except Exception:
            logger.exception(
                "Creation game loop failed for user %s, creation %s",
                user.pk, creation.pk,
            )

    @classmethod
    def _emit_chronicle(cls, user, creation: Creation, primary, day: date) -> None:
        from apps.chronicle.services import ChronicleService

        title = (creation.caption or f"{primary.name} creation").strip()
        try:
            entry = ChronicleService.record_creation(
                user,
                creation_id=creation.id,
                title=title,
                caption=creation.caption or "",
                occurred_on=day,
            )
            creation.chronicle_entry = entry
            creation.save(update_fields=["chronicle_entry"])
        except Exception:
            logger.exception(
                "Chronicle emit failed for creation %s", creation.pk,
            )

    @classmethod
    @transaction.atomic
    def submit_for_bonus(cls, creation: Creation) -> Creation:
        """Flip status to PENDING and notify parents."""
        if creation.status in {Creation.Status.PENDING, Creation.Status.APPROVED}:
            return creation
        creation.status = Creation.Status.PENDING
        creation.save(update_fields=["status", "updated_at"])

        from apps.notifications.models import NotificationType
        from apps.notifications.services import notify_parents

        display = (
            creation.user.get_full_name()
            or getattr(creation.user, "display_name", "")
            or creation.user.username
        )
        notify_parents(
            title=f"{display} submitted a creation",
            message=(
                creation.caption
                or f"{display} submitted a {creation.primary_skill.name} creation for bonus review."
            )[:250],
            notification_type=NotificationType.CREATION_SUBMITTED,
            link="/sketchbook",
            about_user=creation.user,
        )
        return creation

    @classmethod
    @transaction.atomic
    def approve_bonus(
        cls,
        creation: Creation,
        parent,
        *,
        bonus_xp: int = DEFAULT_BONUS_XP,
        extra_skill_tags: Optional[list[dict]] = None,
        notes: str = "",
    ) -> Creation:
        """Grant a parent-authored bonus XP pool and mark APPROVED.

        ``extra_skill_tags`` is a list of dicts like
        ``[{"skill_id": 1, "xp_weight": 2}, ...]``. When omitted or empty,
        the pool falls back to the child's primary skill at weight 1.
        """
        from apps.achievements.models import Skill
        from apps.achievements.services import AwardService

        # Resolve tags — write CreationBonusSkillTag rows for audit/ledger visibility.
        tags_payload = extra_skill_tags or []
        if tags_payload:
            tag_objects = []
            for row in tags_payload:
                skill = Skill.objects.get(pk=row["skill_id"])
                cls._assert_creative_skill(skill)
                tag, _ = CreationBonusSkillTag.objects.get_or_create(
                    creation=creation,
                    skill=skill,
                    defaults={"xp_weight": int(row.get("xp_weight") or 1)},
                )
                tag_objects.append(_CreationTag(skill=skill, xp_weight=tag.xp_weight))
        else:
            # Fallback: award the whole bonus pool to the child's primary skill.
            tag_objects = [
                _CreationTag(skill=creation.primary_skill, xp_weight=1),
            ]

        try:
            AwardService.grant(
                creation.user,
                xp_tags=tag_objects,
                xp=bonus_xp,
                xp_source_label="Creation bonus",
            )
        except Exception:
            logger.exception(
                "Creation bonus award failed for creation %s", creation.pk,
            )

        creation.status = Creation.Status.APPROVED
        creation.bonus_xp_awarded = bonus_xp
        creation.decided_at = timezone.now()
        creation.decided_by = parent
        creation.save(
            update_fields=[
                "status", "bonus_xp_awarded", "decided_at", "decided_by", "updated_at",
            ]
        )

        from apps.notifications.models import NotificationType
        from apps.notifications.services import notify

        notify(
            creation.user,
            title="Bonus approved on your creation!",
            message=(notes or f"+{bonus_xp} XP for your {creation.primary_skill.name} creation."),
            notification_type=NotificationType.CREATION_APPROVED,
            link="/sketchbook",
        )
        return creation

    @classmethod
    @transaction.atomic
    def reject_bonus(cls, creation: Creation, parent, notes: str = "") -> Creation:
        """Mark REJECTED. Baseline XP stays — matches every other flow."""
        creation.status = Creation.Status.REJECTED
        creation.decided_at = timezone.now()
        creation.decided_by = parent
        creation.save(
            update_fields=["status", "decided_at", "decided_by", "updated_at"]
        )

        from apps.notifications.models import NotificationType
        from apps.notifications.services import notify

        notify(
            creation.user,
            title="Creation reviewed",
            message=notes or "Your creation was reviewed — no bonus this time.",
            notification_type=NotificationType.CREATION_REJECTED,
            link="/sketchbook",
        )
        return creation
