"""Drop a journal entry into yesterday so the lock UI engages on open.

Goal: trigger the read-only lock state in
``frontend/src/pages/yearbook/JournalEntryFormModal.jsx`` without waiting
for midnight to roll over. Two paths:

1. If the user has TODAY's journal entry, backdate its ``occurred_on`` to
   yesterday — preserves the body so you can read what's locked.
2. If they don't, mint a synthetic yesterday entry.

Examples::

    python manage.py expire_journal --user abby
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import expire_journal


class Command(BaseCommand):
    help = "Backdate (or mint) a journal entry on yesterday's date."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--days-back", type=int, default=1, dest="days_back",
            help="How many days before today to backdate the entry (default 1).",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])
        result = expire_journal(user, days_back=opts["days_back"])

        if result["action"] == "backdated":
            self.stdout.write(self.style.SUCCESS(
                f"Backdated journal entry id={result['entry_id']} "
                f"→ {result['occurred_on']} (was today)"
            ))
        elif result["action"] == "noop_already_present":
            self.stdout.write(self.style.WARNING(
                f"Journal entry already exists at {result['occurred_on']} "
                f"(id={result['entry_id']}); no change."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Created journal entry id={result['entry_id']} on "
                f"{result['occurred_on']} for {user.username}"
            ))
