"""ChronicleService — all writers are idempotent.

`record_first` relies on the partial unique index on
(user, event_slug) where kind=first_ever for emit-once semantics.
Other writers use get_or_create keyed on their natural identity.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from django.db import IntegrityError, transaction

from apps.chronicle.models import ChronicleEntry

logger = logging.getLogger(__name__)


def _chapter_year_for(d: date) -> int:
    return d.year if d.month >= 8 else d.year - 1


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
