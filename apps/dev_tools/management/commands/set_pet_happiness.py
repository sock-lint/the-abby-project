"""Backdate ``UserPet.last_fed_at`` so the happiness state changes.

Drives the dim filter + whisper text in
``frontend/src/pages/bestiary/party/Companions.jsx``. Levels:

* ``happy``  — fed today (no dim, no whisper)
* ``bored``  — last_fed_at 4 days ago  → grayscale 25% + whisper "a little bored — feed me?"
* ``stale``  — last_fed_at 8 days ago  → grayscale 50% + whisper "getting hungry — needs a snack"
* ``away``   — last_fed_at 15 days ago → grayscale 75%, NO whisper (sprite carries the signal)

Thresholds match ``apps.pets.services.HAPPINESS_THRESHOLDS``. Evolved
mounts are always rendered ``happy`` regardless of ``last_fed_at`` —
this command will mutate their field but the UI clamps.

Examples::

    python manage.py set_pet_happiness --user abby --level stale
    python manage.py set_pet_happiness --user abby --level bored --pet 7
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled


# Days-back values picked to fall safely INSIDE each band defined by
# apps.pets.services.HAPPINESS_THRESHOLDS = {happy:3, bored:7, stale:14}.
_DAYS_BACK = {
    "happy": 0,
    "bored": 4,
    "stale": 8,
    "away": 15,
}


class Command(BaseCommand):
    help = "Set a user's pet's happiness level (backdates last_fed_at)."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--level", choices=list(_DAYS_BACK), required=True,
            help="Target happiness band.",
        )
        parser.add_argument(
            "--pet", type=int, default=None,
            help="UserPet pk. Omit to apply to ALL non-evolved pets the user owns.",
        )

    def handle(self, *args, **opts):
        assert_enabled()

        from apps.pets.models import UserPet

        user = resolve_user(opts["user"])
        days_back = _DAYS_BACK[opts["level"]]
        target = timezone.now() - timedelta(days=days_back)

        qs = UserPet.objects.filter(user=user, evolved_to_mount=False)
        if opts["pet"] is not None:
            qs = qs.filter(pk=opts["pet"])

        count = qs.count()
        if count == 0:
            raise CommandError(
                f"No matching unevolved UserPet rows for user={user.username}"
                + (f", pet={opts['pet']}" if opts['pet'] else "")
                + ". Hatch one first."
            )

        qs.update(last_fed_at=target)
        self.stdout.write(self.style.SUCCESS(
            f"Set {count} pet(s) for {user.username} to level={opts['level']} "
            f"(last_fed_at={target.date()})"
        ))
