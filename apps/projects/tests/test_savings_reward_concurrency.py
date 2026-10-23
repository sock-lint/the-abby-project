"""PostgreSQL verifies the shared user/milestone lock across competing goals."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections, connections
from django.db.models import Sum
from django.test import TransactionTestCase, skipUnlessDBFeature

from apps.payments.models import PaymentLedger
from apps.projects.models import SavingsGoal, SavingsRewardProgress, User
from apps.projects.savings_service import SavingsGoalService
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@skipUnlessDBFeature("has_select_for_update")
class SavingsRewardConcurrencyTests(TransactionTestCase):
    def test_concurrent_completion_pays_overlapping_milestones_only_once(self):
        child = make_family("Concurrent saving", children=[{"username": "saving-race"}]).children[0]
        SavingsGoalService.create_goal(child, title="First target", target_amount=Decimal("50.00"))
        SavingsGoalService.create_goal(child, title="Same target", target_amount=Decimal("50.00"))
        PaymentLedger.objects.create(user=child, amount=50, entry_type="adjustment")
        barrier = Barrier(2)

        def settle():
            close_old_connections()
            try:
                actor = User.objects.get(pk=child.pk)
                barrier.wait(timeout=10)
                return len(SavingsGoalService.check_and_complete(actor))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: settle(), range(2)))
        self.assertEqual(sorted(results), [0, 2])
        self.assertEqual(SavingsGoal.objects.filter(user=child, is_completed=True).count(), 2)
        self.assertEqual(SavingsRewardProgress.objects.get(user=child).recognized_balance, Decimal("50.00"))
        coins = CoinLedger.objects.filter(user=child, description__startswith="Savings goal:").aggregate(
            total=Sum("amount"))["total"]
        self.assertEqual(coins, 100)
