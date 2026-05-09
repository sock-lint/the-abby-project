"""Force a drop into a user's inventory + DropLog without rolling RNG.

Bypasses ``DropService.process_drops`` randomness so manual testing of the
toast/reveal stack is deterministic. Writes to the same shapes the real
service uses — ``UserInventory`` increment + ``DropLog`` row — so the
existing ``/api/drops/recent/`` 20s frontend poller picks it up and renders
``DropToastStack`` (common/uncommon) or ``RareDropReveal`` (rare/epic/legendary).

Examples::

    python manage.py force_drop --user abby --rarity legendary
    python manage.py force_drop --user abby --slug lucky-coin
    python manage.py force_drop --user abby --rarity rare --count 3
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import OperationError, force_drop


class Command(BaseCommand):
    help = "Force a drop (writes DropLog + UserInventory directly)."

    def add_arguments(self, parser):
        add_user_arg(parser)
        parser.add_argument(
            "--rarity",
            choices=["common", "uncommon", "rare", "epic", "legendary"],
            help="Pick a random item of this rarity. Mutually exclusive with --slug.",
        )
        parser.add_argument(
            "--slug",
            help="Drop a specific item by slug. Wins over --rarity.",
        )
        parser.add_argument(
            "--trigger",
            default="dev_tools",
            help="String written to DropLog.trigger_type (informational only).",
        )
        parser.add_argument(
            "--count", type=int, default=1,
            help="Number of drops to fire (default 1; useful for queue testing).",
        )
        parser.add_argument(
            "--salvage", action="store_true",
            help="Mark as salvaged (skips inventory increment, posts coin payout).",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        user = resolve_user(opts["user"])

        try:
            result = force_drop(
                user,
                rarity=opts["rarity"],
                slug=opts["slug"],
                count=opts["count"],
                salvage=bool(opts["salvage"]),
                trigger=opts["trigger"],
            )
        except OperationError as e:
            raise CommandError(str(e)) from e

        verb = "Salvaged" if result["salvaged"] else "Dropped"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {result['count']}× {result['item']['name']} "
            f"({result['item']['rarity']}) → {user.username}"
        ))
