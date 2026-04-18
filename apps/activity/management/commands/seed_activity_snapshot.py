from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.activity.services import ActivityLogService


class Command(BaseCommand):
    """Emit one ``system.backfill_snapshot`` ActivityEvent per child.

    Rather than fabricating historical calculation breakdowns (the old
    ledger rows never stored intermediate math), we anchor the feed with a
    single snapshot of current balances, level, and streak per child.
    Run once after the 0001_initial activity migration applies.
    """

    help = "Seed an activity snapshot per child user."

    def handle(self, *args, **options):
        User = get_user_model()
        children = User.objects.filter(role="child")
        if not children.exists():
            self.stdout.write("No child users found — nothing to snapshot.")
            return

        from apps.payments.services import PaymentService
        from apps.rewards.services import CoinService
        from apps.rpg.models import CharacterProfile

        total = 0
        for child in children:
            coins = CoinService.get_balance(child)
            money = PaymentService.get_balance(child)
            profile = CharacterProfile.objects.filter(user=child).first()
            streak = profile.login_streak if profile else 0
            level = profile.level if profile else 0

            ActivityLogService.record(
                category="system",
                event_type="system.backfill_snapshot",
                summary=f"Starting snapshot for {child.username}",
                subject=child,
                coins_delta=None,
                money_delta=None,
                xp_delta=None,
                breakdown=[
                    {"label": "coins", "value": int(coins), "op": "note"},
                    {"label": "money", "value": str(money), "op": "note"},
                    {"label": "streak", "value": streak, "op": "note"},
                    {"label": "level", "value": level, "op": "note"},
                ],
                extras={
                    "coins": int(coins),
                    "money": str(money),
                    "streak": streak,
                    "level": level,
                },
            )
            total += 1

        self.stdout.write(self.style.SUCCESS(f"Snapshotted {total} child(ren)."))
