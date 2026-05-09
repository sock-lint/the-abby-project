"""Drop a journal entry into yesterday so the lock UI engages on open.

Goal: trigger the read-only lock state in
``frontend/src/pages/yearbook/JournalEntryFormModal.jsx`` without waiting
for midnight to roll over. Two paths:

1. If the user has TODAY's journal entry, backdate its ``occurred_on`` to
   yesterday — preserves the body so you can read what's locked.
2. If they don't, mint a synthetic yesterday entry.

Either way, opening the modal for that entry should switch into read-only
mode (entry.occurred_on !== today's local date), and the 403-on-PATCH
fallback path is exercised if you keep the modal open at midnight rollover.

Examples::

    python manage.py expire_journal --user abby
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled


class Command(BaseCommand):
    help = "Backdate (or mint) a journal entry on yesterday's date for lock-state testing."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--days-back", type=int, default=1,
            help="How many days before today to backdate the entry (default 1).",
        )

    def handle(self, *args, **opts):
        assert_enabled()

        from apps.chronicle.models import ChronicleEntry

        user = resolve_user(opts["user"])
        today = timezone.localdate()
        target_day = today - timedelta(days=opts["days_back"])
        chapter_year = target_day.year if target_day.month >= 8 else target_day.year - 1

        # Path 1: backdate today's journal entry if it exists.
        existing_today = ChronicleEntry.objects.filter(
            user=user, kind=ChronicleEntry.Kind.JOURNAL, occurred_on=today,
        ).first()
        if existing_today is not None:
            existing_today.occurred_on = target_day
            existing_today.chapter_year = chapter_year
            existing_today.save(update_fields=["occurred_on", "chapter_year"])
            self.stdout.write(self.style.SUCCESS(
                f"Backdated journal entry id={existing_today.pk} → {target_day} "
                f"(was today)"
            ))
            return

        # Path 1b: backdate today's hand off to a different existing
        # past-day entry already there — done by --days-back deltas, no-op.
        existing_target = ChronicleEntry.objects.filter(
            user=user, kind=ChronicleEntry.Kind.JOURNAL, occurred_on=target_day,
        ).first()
        if existing_target is not None:
            self.stdout.write(self.style.WARNING(
                f"Journal entry already exists at {target_day} (id={existing_target.pk}); "
                "no change."
            ))
            return

        # Path 2: synthesize a yesterday entry.
        entry = ChronicleEntry.objects.create(
            user=user,
            kind=ChronicleEntry.Kind.JOURNAL,
            occurred_on=target_day,
            chapter_year=chapter_year,
            title=f"{target_day.strftime('%B')} {target_day.day} entry",
            summary="Synthesized by dev_tools.expire_journal for lock-state testing.",
            is_private=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Created journal entry id={entry.pk} on {target_day} for {user.username}"
        ))
