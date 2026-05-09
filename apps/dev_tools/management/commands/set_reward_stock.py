"""Set ``Reward.stock`` to a specific value (drives sold-out + last-one chips).

Surfaces tested:
  * ``stock=0``  → "sold out" chip + redeem-button disabled + 409 OOS
                    fallback path with ``similar`` suggestion sheet
  * ``stock=1``  → "last one" chip in ember tone
  * ``stock=N+`` → restock; if a ``RewardWishlist`` row exists for this
                    reward, the underlying view layer fans out
                    ``REWARD_RESTOCKED`` notifications. This command writes
                    the field directly so it WON'T fan out — use the
                    Manage UI to test the restock signal end-to-end.

Examples::

    python manage.py set_reward_stock --reward 12 --stock 0
    python manage.py set_reward_stock --reward "Movie night" --stock 1
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.dev_tools.gate import assert_enabled


class Command(BaseCommand):
    help = "Set Reward.stock (drives sold-out + last-one chips)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reward", required=True,
            help="Reward id (numeric) OR a substring of the reward name (case-insensitive).",
        )
        parser.add_argument(
            "--stock", type=int, required=True,
            help="New stock value. 0 = sold out, 1 = last one, N+ = restock.",
        )

    def handle(self, *args, **opts):
        assert_enabled()

        from apps.rewards.models import Reward

        ref = opts["reward"]
        if ref.isdigit():
            reward = Reward.objects.filter(pk=int(ref)).first()
        else:
            qs = Reward.objects.filter(name__icontains=ref)
            count = qs.count()
            if count > 1:
                raise CommandError(
                    f"--reward={ref!r} matched {count} rewards: "
                    f"{', '.join(qs.values_list('name', flat=True)[:5])}. Be more specific."
                )
            reward = qs.first()

        if reward is None:
            raise CommandError(f"No Reward found for --reward={ref!r}.")

        prev = reward.stock
        reward.stock = opts["stock"]
        reward.save(update_fields=["stock"])

        self.stdout.write(self.style.SUCCESS(
            f"Reward[{reward.pk}] {reward.name!r}: stock {prev} → {opts['stock']}"
        ))
