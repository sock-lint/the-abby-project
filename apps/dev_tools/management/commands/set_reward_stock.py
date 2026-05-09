"""Set ``Reward.stock`` to a specific value (drives sold-out + last-one chips).

Surfaces tested:
  * ``stock=0``  → "sold out" chip + redeem-button disabled + 409 OOS
                    fallback path with ``similar`` suggestion sheet
  * ``stock=1``  → "last one" chip in ember tone
  * ``stock=N+`` → restock; the ``REWARD_RESTOCKED`` notification only
                    fires through the Manage UI write path, not via this
                    direct mutation.

Examples::

    python manage.py set_reward_stock --reward 12 --stock 0
    python manage.py set_reward_stock --reward "Movie night" --stock 1
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.dev_tools.gate import assert_enabled
from apps.dev_tools.operations import OperationError, set_reward_stock


class Command(BaseCommand):
    help = "Set Reward.stock (drives sold-out + last-one chips)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reward", required=True,
            help="Reward id (numeric) OR a substring of the reward name.",
        )
        parser.add_argument(
            "--stock", type=int, required=True,
            help="New stock value. 0 = sold out, 1 = last one, N+ = restock.",
        )

    def handle(self, *args, **opts):
        assert_enabled()
        try:
            result = set_reward_stock(reward_ref=opts["reward"], stock=opts["stock"])
        except OperationError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(self.style.SUCCESS(
            f"Reward[{result['reward_id']}] {result['name']!r}: "
            f"stock {result['prev_stock']} → {result['new_stock']}"
        ))
