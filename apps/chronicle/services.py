"""ChronicleService — all writers are idempotent.

`record_first` relies on the partial unique index on
(user, event_slug) where kind=first_ever for emit-once semantics.
Other writers use get_or_create keyed on their natural identity.

``write_journal`` / ``update_journal`` are the child-facing writers for the
journal kind — not idempotent (multiple entries per day are fine), but the
first-of-local-day call fires the RPG game loop for streak + XP credit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.chronicle.models import ChronicleEntry

# Hoisted so ``mock.patch("apps.chronicle.services.GameLoopService")`` in
# journal tests patches the name the service actually reads. Lazy-imported
# it before we can still reach via apps.rpg.services, but module-level makes
# the mock targetable without contortions.
from apps.rpg.services import GameLoopService  # noqa: E402
from apps.rpg.constants import TriggerType  # noqa: E402

logger = logging.getLogger(__name__)

JOURNAL_XP_POOL = 15
# Order matters — the weights split the pool 2:1. Creative Writing gets
# the bulk (10 XP) because it's the primary skill being exercised;
# Vocabulary (5 XP) gets the leftover because any writing practice
# reinforces word use. Both skills are authored in ``skill_tree.yaml``
# under the Language Arts category.
JOURNAL_SKILL_WEIGHTS = [
    ("Creative Writing", 2),
    ("Vocabulary", 1),
]

JOURNAL_TITLE_MAX_BODY_CHARS = 60


@dataclass
class _JournalTag:
    """Shim matching the ``.skill`` + ``.xp_weight`` duck-type expected by
    ``SkillService.distribute_tagged_xp``. Lets the journal service reuse the
    weighted-XP distribution without a real ``JournalSkillTag`` model.
    """

    skill: object
    xp_weight: int


def _chapter_year_for(d: date) -> int:
    return d.year if d.month >= 8 else d.year - 1


def _autofill_journal_title(title: str, body: str, occurred_on: date) -> str:
    """Fallback rule for journal titles.

    - If the child provided a title, use it unchanged.
    - Otherwise use the first ~60 characters of the body with an ellipsis.
    - If the body is also empty, fall back to a human-readable date stamp.
    """
    clean_title = (title or "").strip()
    if clean_title:
        return clean_title[:160]
    clean_body = (body or "").strip()
    if clean_body:
        if len(clean_body) <= JOURNAL_TITLE_MAX_BODY_CHARS:
            return clean_body
        return clean_body[:JOURNAL_TITLE_MAX_BODY_CHARS].rstrip() + "…"
    if hasattr(occurred_on, "strftime"):
        # Platform-safe: build the label manually because %-d (Linux) /
        # %#d (Windows) aren't portable.
        return f"{occurred_on.strftime('%B')} {occurred_on.day} entry"
    return f"{occurred_on} entry"


def _journal_xp_tags():
    """Resolve the two hardcoded Language Arts skills by name.

    Returns an empty list on a fresh DB that hasn't loaded the skill catalog
    yet — ``AwardService.grant`` then no-ops on the XP branch, which is the
    correct fallback (no XP awarded, but the rest of the flow continues).
    """
    from apps.achievements.models import Skill

    tags = []
    for name, weight in JOURNAL_SKILL_WEIGHTS:
        skill = Skill.objects.filter(
            category__name="Language Arts", name=name,
        ).first()
        if skill is not None:
            tags.append(_JournalTag(skill=skill, xp_weight=weight))
    return tags


class ChronicleService:
    @staticmethod
    def record_first(
        user,
        event_slug: str,
        *,
        title: str,
        summary: str = "",
        icon_slug: str = "",
        related: Optional[tuple[str, int]] = None,
        occurred_on: Optional[date] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[ChronicleEntry]:
        """Write a FIRST_EVER entry. Returns None if already exists for this (user, event_slug)."""
        if not event_slug:
            raise ValueError("event_slug is required for record_first")
        day = occurred_on or date.today()
        related_type, related_id = (related or ("", None))
        try:
            with transaction.atomic():
                return ChronicleEntry.objects.create(
                    user=user,
                    kind=ChronicleEntry.Kind.FIRST_EVER,
                    occurred_on=day,
                    chapter_year=_chapter_year_for(day),
                    title=title,
                    summary=summary,
                    icon_slug=icon_slug,
                    event_slug=event_slug,
                    related_object_type=related_type,
                    related_object_id=related_id,
                    metadata=metadata or {},
                )
        except IntegrityError:
            return None

    @staticmethod
    def record_birthday(user, *, on_date: Optional[date] = None) -> ChronicleEntry:
        """Idempotent. Keyed on (user, kind=BIRTHDAY, occurred_on)."""
        day = on_date or date.today()
        age = None
        if user.date_of_birth:
            age = day.year - user.date_of_birth.year
            if (day.month, day.day) < (user.date_of_birth.month, user.date_of_birth.day):
                age -= 1
        title = f"Turned {age}" if age is not None else "Birthday"
        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.BIRTHDAY,
            occurred_on=day,
            defaults={
                "chapter_year": _chapter_year_for(day),
                "title": title,
                "icon_slug": "birthday-candle",
            },
        )
        return entry

    @staticmethod
    def record_chapter_start(user, chapter_year: int) -> ChronicleEntry:
        day = date(chapter_year, 8, 1)
        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.CHAPTER_START,
            chapter_year=chapter_year,
            defaults={
                "occurred_on": day,
                "title": "New chapter begins",
            },
        )
        return entry

    @staticmethod
    def record_chapter_end(user, chapter_year: int) -> ChronicleEntry:
        day = date(chapter_year + 1, 6, 1)
        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.CHAPTER_END,
            chapter_year=chapter_year,
            defaults={
                "occurred_on": day,
                "title": "Chapter closes",
            },
        )
        return entry

    @staticmethod
    @transaction.atomic
    def write_journal(
        user,
        *,
        title: str,
        summary: str,
        occurred_on: Optional[date] = None,
    ) -> ChronicleEntry:
        """Create a child-authored journal entry for the given user.

        Always sets ``kind=JOURNAL`` and ``is_private=True``. Multiple entries
        per local day are allowed. When the entry is the first journal entry
        of the user's local day, awards XP to Creative Writing + Vocabulary
        (hardcoded 10/5 split) and fires the RPG game loop so the child earns
        streak credit, a drop roll, and quest progress.
        """
        day = occurred_on or timezone.localdate()
        resolved_title = _autofill_journal_title(title, summary, day)
        entry = ChronicleEntry.objects.create(
            user=user,
            kind=ChronicleEntry.Kind.JOURNAL,
            is_private=True,
            occurred_on=day,
            chapter_year=_chapter_year_for(day),
            title=resolved_title,
            summary=summary or "",
        )

        # First-of-local-day gate — prevents farming streak/drops/quest
        # progress by writing many short entries in one sitting. Mirrors the
        # ``homework_created`` anti-farm pattern.
        is_first_today = not ChronicleEntry.objects.filter(
            user=user, kind=ChronicleEntry.Kind.JOURNAL, occurred_on=day,
        ).exclude(pk=entry.pk).exists()

        if is_first_today:
            # Award paired XP + badge re-eval via the unified pipeline.
            try:
                from apps.achievements.services import AwardService

                tags = _journal_xp_tags()
                if tags:
                    AwardService.grant(
                        user,
                        xp_tags=tags,
                        xp=JOURNAL_XP_POOL,
                        xp_source_label="Journal entry",
                    )
                else:
                    # No Language Arts skills seeded yet — still run badge
                    # evaluation so the entries_written / streak badges can
                    # fire on an unseeded test DB.
                    from apps.achievements.services import BadgeService

                    BadgeService.evaluate_badges(user)
            except Exception:
                # An award failure must not block the write — the entry is
                # the canonical record; rewards are a bonus.
                logger.exception("Journal XP award hook failed for user %s", user.pk)

            try:
                GameLoopService.on_task_completed(
                    user,
                    TriggerType.JOURNAL_ENTRY,
                    {"entry_id": entry.pk},
                )
            except Exception:
                # Same defensive stance — the write succeeded; streak/drops
                # are best-effort downstream effects.
                logger.exception("Journal game-loop hook failed for user %s", user.pk)

        return entry

    @staticmethod
    @transaction.atomic
    def update_journal(
        user,
        entry: ChronicleEntry,
        *,
        title: str,
        summary: str,
    ) -> ChronicleEntry:
        """Edit a journal entry owned by ``user`` on the same local day.

        Raises ``PermissionDenied`` when the caller is not the owner, the
        entry isn't a journal entry, or the entry was written on a prior day
        (entries lock at local midnight).
        """
        if entry.user_id != user.id:
            raise PermissionDenied("You can only edit your own journal entries.")
        if entry.kind != ChronicleEntry.Kind.JOURNAL:
            raise PermissionDenied("Only journal entries are editable here.")
        if entry.occurred_on != timezone.localdate():
            raise PermissionDenied(
                "Journal entries lock after the day ends — this one is part of the chronicle now."
            )
        entry.title = _autofill_journal_title(title, summary, entry.occurred_on)
        entry.summary = summary or ""
        entry.save(update_fields=["title", "summary"])
        return entry

    @staticmethod
    def freeze_recap(user, chapter_year: int) -> ChronicleEntry:
        """Aggregates stats for the chapter and writes a RECAP entry. Idempotent."""
        from django.db.models import Sum

        from apps.projects.models import Project
        from apps.rewards.models import CoinLedger

        start = date(chapter_year, 8, 1)
        end = date(chapter_year + 1, 7, 31)

        stats = {}

        # Project.completed_at is a DateTimeField — use __date__range to compare
        # the date portion so plain date boundaries work correctly.
        stats["projects_completed"] = Project.objects.filter(
            assigned_to=user,
            status="completed",
            completed_at__date__range=(start, end),
        ).count()

        # CoinLedger.amount is IntegerField; Sum returns int (or None when empty).
        coins_earned = (
            CoinLedger.objects.filter(
                user=user,
                created_at__date__range=(start, end),
                amount__gt=0,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        stats["coins_earned"] = coins_earned

        # Optional additive aggregations — wrap each so a missing app
        # doesn't break recap writes. Each block short-circuits on import
        # failure without failing the overall freeze.
        try:
            from apps.homework.models import HomeworkSubmission

            # HomeworkSubmission.decided_at is a DateTimeField (from ApprovalWorkflowModel).
            stats["homework_approved"] = HomeworkSubmission.objects.filter(
                assignment__assigned_to=user,
                status="approved",
                decided_at__date__range=(start, end),
            ).count()
        except Exception as exc:  # pragma: no cover
            logger.debug("homework recap skipped: %s", exc)

        try:
            from apps.chores.models import ChoreCompletion

            # ChoreCompletion.completed_date is a DateField — plain __range works.
            stats["chores_approved"] = ChoreCompletion.objects.filter(
                user=user,
                status="approved",
                completed_date__range=(start, end),
            ).count()
        except Exception as exc:  # pragma: no cover
            logger.debug("chores recap skipped: %s", exc)

        entry, _ = ChronicleEntry.objects.get_or_create(
            user=user,
            kind=ChronicleEntry.Kind.RECAP,
            chapter_year=chapter_year,
            defaults={
                "occurred_on": date(chapter_year + 1, 6, 1),
                "title": f"Chapter {chapter_year}-{str(chapter_year + 1)[-2:]} recap",
                "metadata": stats,
            },
        )
        return entry
