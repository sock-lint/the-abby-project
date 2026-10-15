"""A parent quotes a fixed print price; only its child can spend Coins."""
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import skipUnless
from unittest import mock

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings

from apps.printing.budget import PrintBudgetService
from apps.printing.matching import find_request
from apps.printing.jobs import PrinterJobTracker
from apps.printing.models import PrintJob, PrintRequest, PrinterProfile
from apps.printing.report import PrinterState
from apps.printing.services import PrintRequestError, PrintRequestService
from apps.printing.serializers import PrintRequestEditSerializer
from apps.printing.tasks import cache_request_thumbnail
from apps.printing.views import PrintRequestViewSet
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService, InsufficientCoinsError
from config.tests.factories import make_family

from .test_services import _Fixture
from .test_views import _ApiFixture
from .test_tasks import FakeResponse, JPEG_BYTES


class PrintCoinQuoteTests(_Fixture):
    def test_priced_approval_waits_for_child_exchange_and_rounds_up(self):
        # Setting the new policy on the object makes this assertion runnable
        # against the original base, where approval ignored Coin pricing.
        budget = PrintBudgetService.get_budget(self.child)
        budget.minutes_per_coin = 10
        request = self.submit()
        with mock.patch.object(PrintBudgetService, "get_budget", return_value=budget):
            quoted = PrintRequestService.approve(
                request, self.parent, estimated_minutes=21,
            )
        self.assertEqual(quoted.status, "quoted")
        self.assertEqual(quoted.coin_cost, 3)
        self.assertEqual(quoted.minutes_per_coin_snapshot, 10)
        self.assertEqual(quoted.coins_paid, 0)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertTrue(quoted.slug)
        self.assertIsNone(find_request(quoted.slug, family=self.household.family))

    def set_rate(self, rate=10):
        budget = PrintBudgetService.get_budget(self.child)
        budget.minutes_per_coin = rate
        budget.save(update_fields=["minutes_per_coin"])

    def quote(self, minutes=21):
        self.set_rate()
        return PrintRequestService.approve(
            self.submit(), self.parent, estimated_minutes=minutes,
        )

    def fund(self, amount=20):
        return CoinService.award_coins(
            self.child, amount, CoinLedger.Reason.ADJUSTMENT,
        )

    def test_pricing_requires_positive_estimate_even_with_force(self):
        self.set_rate()
        for minutes in (None, 0):
            request = self.submit()
            with self.assertRaises(PrintRequestError):
                PrintRequestService.approve(
                    request, self.parent, estimated_minutes=minutes, force=True,
                )
            request.refresh_from_db()
            self.assertEqual(request.status, PrintRequest.Status.PENDING)
            self.assertEqual(request.slug, "")

    def test_fifteen_minutes_per_coin_rounds_sixty_to_four_and_sixty_one_to_five(self):
        self.set_rate(15)
        for minutes, cost in ((60, 4), (61, 5)):
            request = PrintRequestService.approve(
                self.submit(), self.parent, estimated_minutes=minutes,
            )
            self.assertEqual(request.coin_cost, cost)

    def test_exchange_uses_frozen_quote_and_retry_never_charges_again(self):
        request = self.quote()
        self.fund()
        self.set_rate(1)
        paid = PrintRequestService.exchange(request, self.child)
        self.assertEqual(paid.status, PrintRequest.Status.APPROVED)
        self.assertEqual(paid.coins_paid, 3)
        self.assertEqual(paid.debit_entry.amount, -3)
        self.assertEqual(CoinService.get_balance(self.child), 17)
        # The caller may retry a response lost after the printer has started.
        paid.status = PrintRequest.Status.COMPLETED
        paid.save(update_fields=["status"])
        again = PrintRequestService.exchange(request, self.child)
        self.assertEqual(again.status, PrintRequest.Status.COMPLETED)
        self.assertEqual(CoinService.get_balance(self.child), 17)
        self.assertEqual(CoinLedger.objects.filter(amount__lt=0).count(), 1)

    def test_insufficient_coins_leaves_quote_and_ledger_unchanged(self):
        request = self.quote()
        self.fund(2)
        with self.assertRaises(InsufficientCoinsError):
            PrintRequestService.exchange(request, self.child)
        request.refresh_from_db()
        self.assertEqual(request.status, "quoted")
        self.assertEqual(request.coins_paid, 0)
        self.assertIsNone(request.debit_entry_id)
        self.assertEqual(CoinLedger.objects.count(), 1)

    def test_cancel_refunds_paid_price_once_and_rejects_late_exchange(self):
        request = self.quote()
        self.fund()
        paid = PrintRequestService.exchange(request, self.child)
        cancelled = PrintRequestService.cancel(paid, self.child)
        self.assertEqual(cancelled.coins_refunded, 3)
        self.assertEqual(cancelled.refund_entry.amount, 3)
        self.assertEqual(CoinService.get_balance(self.child), 20)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(paid, self.child)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.exchange(request, self.child)
        self.assertEqual(CoinService.get_balance(self.child), 20)

    def test_quote_can_be_cancelled_without_coin_entries(self):
        request = self.quote()
        cancelled = PrintRequestService.cancel(request, self.child)
        self.assertEqual(cancelled.status, PrintRequest.Status.CANCELLED)
        self.assertEqual(cancelled.coins_refunded, 0)
        self.assertFalse(CoinLedger.objects.exists())

    def test_stale_approved_copy_cannot_refund_after_a_job_started(self):
        self.fund()
        request = PrintRequestService.exchange(self.quote(), self.child)
        stale = PrintRequest.objects.get(pk=request.pk)
        request.status = PrintRequest.Status.PRINTING
        request.started_at = self.printer.created_at
        request.save(update_fields=["status", "started_at"])
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(stale, self.parent)
        self.assertEqual(CoinService.get_balance(self.child), 17)

    def test_cancel_after_stopped_print_cannot_refund_consumed_attempt(self):
        self.fund()
        request = PrintRequestService.exchange(self.quote(), self.child)
        self.open_job(request=request)
        # A stopped print returns to approved and may have been unlinked.
        request.started_at = self.printer.created_at
        request.save(update_fields=["started_at"])
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(request, self.parent)
        self.assertEqual(CoinService.get_balance(self.child), 17)

    def test_manual_link_cannot_bypass_unpaid_quote(self):
        request = self.quote()
        job = self.open_job()
        with self.assertRaises(PrintRequestError):
            PrintRequestService.link_job(job, request, self.parent)
        job.refresh_from_db()
        self.assertIsNone(job.request_id)

    def test_linking_then_unlinking_a_finished_job_cannot_enable_refund(self):
        self.fund()
        request = PrintRequestService.exchange(self.quote(), self.child)
        job = self.open_job()
        job.finished_at = self.printer.created_at
        job.state = PrintJob.State.FINISHED
        job.save(update_fields=["finished_at", "state"])
        PrintRequestService.link_job(job, request, self.parent)
        PrintRequestService.unlink_job(job, self.parent)
        request.refresh_from_db()
        self.assertIsNotNone(request.started_at)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(request, self.child)
        self.assertEqual(CoinService.get_balance(self.child), 17)

    def test_failure_and_retry_keep_fixed_price_without_more_spending(self):
        self.fund()
        request = PrintRequestService.exchange(self.quote(), self.child)
        job = self.open_job(request=request)
        job.state = PrintJob.State.FAILED
        job.duration_minutes = 90
        job.save(update_fields=["state", "duration_minutes"])
        PrintRequestService.close_out(job)
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.FAILED)
        self.assertEqual(CoinService.get_balance(self.child), 17)
        self.assertEqual(find_request(request.slug), request)
        self.assertEqual(PrintRequestService.exchange(request, self.child).coins_paid, 3)


class PrintCoinExchangeAPITests(_ApiFixture):
    def setUp(self):
        super().setUp()
        budget = PrintBudgetService.get_budget(self.child)
        budget.minutes_per_coin = 10
        budget.save(update_fields=["minutes_per_coin"])
        self.budget = budget
        self.client.force_authenticate(self.parent)
        response = self.client.post(
            f"/api/print-requests/{self.make_request().pk}/approve/",
            {"estimated_minutes": 21}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.request_id = response.json()["id"]
        CoinService.award_coins(self.child, 20, CoinLedger.Reason.ADJUSTMENT)

    @property
    def exchange_url(self):
        return f"/api/print-requests/{self.request_id}/exchange/"

    def test_child_exchange_returns_frozen_price_and_refund_snapshot(self):
        self.client.force_authenticate(self.child)
        response = self.client.post(self.exchange_url, {}, format="json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["minutes_per_coin_snapshot"], 10)
        self.assertEqual(body["coin_cost"], 3)
        self.assertEqual(body["coins_paid"], 3)
        self.assertEqual(body["coins_refunded"], 0)

    def test_parent_cannot_spend_child_coins(self):
        response = self.client.post(self.exchange_url, {}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CoinService.get_balance(self.child), 20)

    def test_quote_and_paid_receipts_cannot_be_deleted(self):
        url = f"/api/print-requests/{self.request_id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.post(self.exchange_url, {}, format="json").status_code, 200)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertTrue(PrintRequest.objects.filter(pk=self.request_id).exists())

    def test_exchange_does_not_accept_client_price_or_account(self):
        self.client.force_authenticate(self.child)
        response = self.client.post(
            self.exchange_url, {"coin_cost": 1, "user_id": self.sibling.pk}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CoinService.get_balance(self.child), 20)

    def test_sibling_and_other_family_cannot_exchange(self):
        other = make_family(
            "Other", parents=[{"username": "other-parent"}],
            children=[{"username": "other-child"}],
        )
        for actor in (self.sibling, other.parents[0], other.children[0]):
            self.client.force_authenticate(actor)
            response = self.client.post(self.exchange_url, {}, format="json")
            self.assertEqual(response.status_code, 404)
        self.assertEqual(CoinService.get_balance(self.child), 20)

    def test_budget_rate_is_nullable_positive_and_parent_only(self):
        url = f"/api/print-budgets/{self.budget.pk}/"
        self.client.force_authenticate(self.child)
        response = self.client.patch(url, {"minutes_per_coin": 1}, format="json")
        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.parent)
        for rate in (0, -1):
            response = self.client.patch(url, {"minutes_per_coin": rate}, format="json")
            self.assertEqual(response.status_code, 400)
        response = self.client.patch(url, {"minutes_per_coin": None}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["minutes_per_coin"])

    def test_quoted_request_is_not_editable_and_estimate_is_required(self):
        self.client.force_authenticate(self.child)
        response = self.client.patch(
            f"/api/print-requests/{self.request_id}/", {"title": "Different print"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.parent)
        response = self.client.post(
            f"/api/print-requests/{self.make_request().pk}/approve/",
            {}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_insufficient_balance_is_conflict_without_accepting_quote(self):
        CoinService.spend_coins(self.child, 20, CoinLedger.Reason.REDEMPTION)
        self.client.force_authenticate(self.child)
        response = self.client.post(self.exchange_url, {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(PrintRequest.objects.get(pk=self.request_id).status, "quoted")

    def test_edit_rechecks_cancellation_before_saving_a_stale_request(self):
        self.client.force_authenticate(self.child)
        self.client.post(self.exchange_url, {}, format="json")
        original_get_object = PrintRequestViewSet.get_object

        def get_then_cancel(view):
            stale = original_get_object(view)
            PrintRequestService.cancel(stale, self.child)
            return stale

        with mock.patch.object(PrintRequestViewSet, "get_object", get_then_cancel):
            response = self.client.patch(
                f"/api/print-requests/{self.request_id}/", {"title": "Edited"}, format="json",
            )
        self.assertEqual(response.status_code, 400)
        request = PrintRequest.objects.get(pk=self.request_id)
        self.assertEqual(request.status, PrintRequest.Status.CANCELLED)
        self.assertEqual(request.coins_refunded, 3)
        self.assertEqual(CoinService.get_balance(self.child), 20)

    def test_narrow_serializer_save_cannot_overwrite_payment_state(self):
        self.client.force_authenticate(self.child)
        self.client.post(self.exchange_url, {}, format="json")
        stale = PrintRequest.objects.get(pk=self.request_id)
        edit = PrintRequestEditSerializer(stale, data={"title": "Edited"}, partial=True)
        edit.is_valid(raise_exception=True)
        PrintRequestService.cancel(stale, self.child)
        edit.save()
        request = PrintRequest.objects.get(pk=self.request_id)
        self.assertEqual(request.status, PrintRequest.Status.CANCELLED)
        self.assertEqual(request.coins_refunded, 3)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(request, self.child)
        self.assertEqual(CoinService.get_balance(self.child), 20)

    def test_thumbnail_download_cannot_resurrect_cancelled_payment_state(self):
        self.client.force_authenticate(self.child)
        self.client.post(self.exchange_url, {}, format="json")
        PrintRequest.objects.filter(pk=self.request_id).update(
            thumbnail_url="https://example.com/dragon.jpg",
        )

        def cancel_during_download(*args, **kwargs):
            PrintRequestService.cancel(
                PrintRequest.objects.get(pk=self.request_id), self.child,
            )
            return FakeResponse(JPEG_BYTES)

        with TemporaryDirectory(prefix="abby-print-exchange-") as media_dir:
            with override_settings(MEDIA_ROOT=media_dir):
                with mock.patch("config.url_safety.safe_get", side_effect=cancel_during_download):
                    result = cache_request_thumbnail(self.request_id)
                self.assertIn("cached thumbnail", result)
        request = PrintRequest.objects.get(pk=self.request_id)
        self.assertEqual(request.status, PrintRequest.Status.CANCELLED)
        self.assertEqual(request.coins_refunded, 3)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(request, self.child)
        self.assertEqual(CoinService.get_balance(self.child), 20)


@skipUnless(connection.vendor == "postgresql", "Real row locks require PostgreSQL")
class PrintCoinConcurrencyTests(TransactionTestCase):
    def setUp(self):
        household = make_family(
            "Concurrent", parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = household.parents[0]
        self.child = household.children[0]
        self.printer = PrinterProfile.objects.create(
            family=household.family, name="X1", serial="concurrent-printer",
        )
        budget = PrintBudgetService.get_budget(self.child)
        budget.minutes_per_coin = 15
        budget.save(update_fields=["minutes_per_coin"])
        CoinService.award_coins(self.child, 5, CoinLedger.Reason.ADJUSTMENT)

    def quote(self):
        request = PrintRequestService.create_request(
            self.child, title="Test", reason="Test", color="red",
            source_kind=PrintRequest.SourceKind.UPLOAD,
        )
        return PrintRequestService.approve(request, self.parent, estimated_minutes=45)

    def parallel(self, *actions):
        ready = Barrier(len(actions))

        def run(action):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return action()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(run, action) for action in actions]
            return [future.result(timeout=20) for future in futures]

    def exchange(self, request):
        try:
            PrintRequestService.exchange(request, self.child)
            return "paid"
        except InsufficientCoinsError:
            return "insufficient"

    def test_different_requests_cannot_spend_the_same_wallet_balance(self):
        first, second = self.quote(), self.quote()
        result = self.parallel(lambda: self.exchange(first), lambda: self.exchange(second))
        self.assertCountEqual(result, ["paid", "insufficient"])
        self.assertEqual(CoinService.get_balance(self.child), 2)
        self.assertEqual(PrintRequest.objects.filter(coins_paid=3).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(amount=-3).count(), 1)

    def test_duplicate_exchange_charges_once_under_concurrent_retries(self):
        request = self.quote()
        result = self.parallel(lambda: self.exchange(request), lambda: self.exchange(request))
        self.assertEqual(result, ["paid", "paid"])
        self.assertEqual(CoinService.get_balance(self.child), 2)
        self.assertEqual(CoinLedger.objects.filter(amount=-3).count(), 1)

    def test_cancellation_and_printer_binding_cannot_both_refund_and_attach(self):
        request = PrintRequestService.exchange(self.quote(), self.child)
        state = PrinterState(
            seeded=True, subtask_name=request.slug, gcode_state="RUNNING",
            print_type="local", remaining_minutes=45,
        )

        def cancel():
            try:
                PrintRequestService.cancel(request, self.child)
                return "cancelled"
            except PrintRequestError:
                return "started"

        self.parallel(cancel, lambda: PrinterJobTracker(self.printer)._ensure_job(state))
        request.refresh_from_db()
        job = PrintJob.objects.get()
        if request.coins_refunded:
            self.assertEqual(request.status, PrintRequest.Status.CANCELLED)
            self.assertIsNone(job.request_id)
            self.assertEqual(CoinService.get_balance(self.child), 5)
        else:
            self.assertEqual(request.status, PrintRequest.Status.PRINTING)
            self.assertEqual(job.request_id, request.pk)
            self.assertEqual(CoinService.get_balance(self.child), 2)
