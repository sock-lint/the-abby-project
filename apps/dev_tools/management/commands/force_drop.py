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

import random

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F

from apps.dev_tools._helpers import add_user_arg, resolve_user
from apps.dev_tools.gate import assert_enabled


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

        if not opts["rarity"] and not opts["slug"]:
            raise CommandError("Must pass --rarity or --slug.")

        from apps.rpg.models import DropLog, ItemDefinition, UserInventory

        user = resolve_user(opts["user"])

        if opts["slug"]:
            try:
                item = ItemDefinition.objects.get(slug=opts["slug"])
            except ItemDefinition.DoesNotExist as e:
                raise CommandError(f"No ItemDefinition with slug={opts['slug']!r}") from e
        else:
            pool = list(ItemDefinition.objects.filter(rarity=opts["rarity"]))
            if not pool:
                raise CommandError(
                    f"No ItemDefinition rows at rarity={opts['rarity']!r}. "
                    "Run `loadrpgcontent` first."
                )
            item = random.choice(pool)

        salvaged = bool(opts["salvage"])

        for _ in range(opts["count"]):
            if not salvaged:
                inv, created = UserInventory.objects.get_or_create(
                    user=user, item=item, defaults={"quantity": 1},
                )
                if not created:
                    UserInventory.objects.filter(pk=inv.pk).update(
                        quantity=F("quantity") + 1,
                    )
            elif item.coin_value > 0:
                from apps.rewards.models import CoinLedger
                from apps.rewards.services import CoinService

                CoinService.award_coins(
                    user, item.coin_value, CoinLedger.Reason.ADJUSTMENT,
                    description=f"[dev_tools] Salvaged duplicate: {item.name}",
                )

            DropLog.objects.create(
                user=user, item=item, trigger_type=opts["trigger"],
                quantity=1, was_salvaged=salvaged,
            )

        verb = "Salvaged" if salvaged else "Dropped"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {opts['count']}× {item.name} ({item.rarity}) → {user.username}"
        ))
