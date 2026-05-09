"""Backdate ``UserPet.last_fed_at`` so the happiness state changes.

Drives the dim filter + whisper text in
``frontend/src/pages/bestiary/party/Companions.jsx``. Levels:

* ``happy``  — fed today (no dim, no whisper)
* ``bored``  — last_fed_at 4 days ago  → grayscale 25% + whisper
* ``stale``  — last_fed_at 8 days ago  → grayscale 50% + whisper
* ``away``   — last_fed_at 15 days ago → grayscale 75%, NO whisper

Thresholds match ``apps.pets.services.HAPPINESS_THRESHOLDS``.

Examples::

    python manage.py set_pet_happiness --user abby --level stale
    python manage.py set_pet_happiness --user abby --level bored --pet 7
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import (
    PET_HAPPINESS_DAYS_BACK, OperationError, set_pet_happiness,
)


class Command(BaseCommand):
    help = "Set a user's pet's happiness level (backdates last_fed_at)."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--level", choices=list(PET_HAPPINESS_DAYS_BACK), required=True,
            help="Target happiness band.",
        )
        parser.add_argument(
            "--pet", type=int, default=None, dest="pet_id",
            help="UserPet pk. Omit to apply to ALL non-evolved pets the user owns.",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])
        try:
            result = set_pet_happiness(
                user, level=opts["level"], pet_id=opts["pet_id"],
            )
        except OperationError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(self.style.SUCCESS(
            f"Set {result['pets_updated']} pet(s) for {user.username} "
            f"to level={result['level']} (last_fed_at={result['last_fed_at']})"
        ))
