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
