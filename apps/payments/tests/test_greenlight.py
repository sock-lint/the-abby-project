"""Payment authorization, retry/reconciliation safety and observed balances."""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.payments.greenlight import confirm_transfer
from apps.payments.models import (
    GreenlightBalanceSnapshot, GreenlightStatementTransfer, GreenlightTransfer, PaymentLedger,
)
from apps.payments.services import PaymentService
from apps.timecards.models import Timecard
from config.tests.factories import make_family


class GreenlightTests(TestCase):
    base = "/api/payments/greenlight/"

    def setUp(self):
        family = make_family("Greenlight", parents=[{"username": "gl-parent"}], children=[{"username": "gl-child"}, {"username": "gl-sibling"}])
        foreign = make_family("Foreign", parents=[{"username": "foreign-parent"}], children=[{"username": "foreign-child"}])
        self.parent, self.child, self.sibling = family.parents[0], family.children[0], family.children[1]
        self.foreign_parent, self.foreign_child = foreign.parents[0], foreign.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.today = timezone.localdate().isoformat()
        PaymentService.record_entry(self.child, Decimal("30.00"), PaymentLedger.EntryType.CHORE_REWARD)

    def post(self, route, data, *, child=None):
        return self.client.post(self.base + route + "/", {"user_id": (child or self.child).pk, **data}, format="json")

    def payout(self, **changes):
        return self.post("payout", {
            "amount": "10.00", "transferred_on": self.today, "reference": "transfer-1",
            "memo": "Weekly pay", "idempotency_key": "test-key-1", **changes,
        })

    def csv(self, *rows):
        return "date,amount,description,reference,type\n" + "\n".join(rows)

    def preview(self, csv_data):
        response = self.post("preview", {"csv_data": csv_data})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["rows"]

    def reconcile(self, csv_data, selections):
        return self.post("reconcile", {"csv_data": csv_data, "selections": selections})

    def payouts(self):
        return PaymentLedger.objects.filter(user=self.child, entry_type=PaymentLedger.EntryType.PAYOUT)

    def card(self, status=Timecard.Status.APPROVED):
        card = Timecard.objects.create(
            user=self.child, week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
            total_earnings=Decimal("5.00"), hourly_earnings=Decimal("5.00"), status=status,
        )
        PaymentService.record_entry(self.child, Decimal("5.00"), PaymentLedger.EntryType.HOURLY, timecard=card)
        return card

    def test_overview_distinguishes_owed_approved_and_observed_balance(self):
        self.card(Timecard.Status.PENDING)
        PaymentService.record_entry(self.child, Decimal("7.00"), PaymentLedger.EntryType.HOURLY)
        data = self.client.get(self.base + f"overview/?user_id={self.child.pk}").json()
        self.assertEqual((data["owed_balance"], data["approved_payable"], data["pending_hourly"]), ("42.00", "30.00", "12.00"))
        self.assertIsNone(data["balance_snapshot"])
        self.assertEqual(data["payouts"], [])

    def test_overview_offers_only_positive_approved_timecards_for_payment(self):
        payable_card = self.card()
        nonpayable_cards = [
            Timecard.objects.create(
                user=self.child, week_start=date(2026, 9, day), week_end=date(2026, 9, day + 6),
                total_hours=Decimal("0.10"), hourly_earnings=amount,
                total_earnings=amount, status=Timecard.Status.APPROVED,
            )
            for day, amount in ((7, Decimal("0.00")), (14, Decimal("-1.00")))
        ]
        ledger_count = PaymentLedger.objects.count()

        response = self.client.get(self.base + f"overview/?user_id={self.child.pk}")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["approved_timecards"], [{
            "id": payable_card.pk, "week_start": "2026-10-05", "total_earnings": "5.00",
        }])
        for card in nonpayable_cards:
            card.refresh_from_db()
            self.assertEqual(card.status, Timecard.Status.APPROVED)
        self.assertEqual(PaymentLedger.objects.count(), ledger_count)
        self.assertFalse(self.payouts().exists())

    def test_zero_timecard_cannot_create_a_payment_or_change_approval(self):
        card = Timecard.objects.create(
            user=self.child, week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
            total_earnings=Decimal("0.00"), status=Timecard.Status.APPROVED,
        )
        ledger_count = PaymentLedger.objects.count()
        responses = [
            self.payout(amount="0.00", timecard_id=card.pk),
            self.client.post(f"/api/timecards/{card.pk}/mark-paid/", {}, format="json"),
        ]
        for response in responses:
            self.assertEqual(response.status_code, 400, response.content)
        card.refresh_from_db()
        self.assertEqual(card.status, Timecard.Status.APPROVED)
        self.assertEqual(PaymentLedger.objects.count(), ledger_count)
        self.assertFalse(self.payouts().exists())
        self.assertFalse(GreenlightTransfer.objects.exists())

    def test_parent_default_balance_aggregates_only_own_family_children(self):
        PaymentService.record_entry(self.sibling, Decimal("7.00"), PaymentLedger.EntryType.CHORE_REWARD)
        PaymentService.record_entry(self.parent, Decimal("60.00"), PaymentLedger.EntryType.ADJUSTMENT)
        PaymentService.record_entry(self.foreign_child, Decimal("90.00"), PaymentLedger.EntryType.CHORE_REWARD)
        response = self.client.get("/api/balance/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["balance"], 37.0)
        self.assertEqual(response.json()["breakdown"], {"chore_reward": 37.0})
        self.assertEqual({row["user"] for row in response.json()["recent_transactions"]}, {self.child.pk, self.sibling.pk})
        response = self.client.get(f"/api/balance/?user_id={self.child.pk}")
        self.assertEqual(response.json()["balance"], 30.0)

    def test_invalid_or_foreign_child_balance_does_not_fall_back_to_family(self):
        for user_id in ("", "invalid", "0", "-1"):
            response = self.client.get(f"/api/balance/?user_id={user_id}")
            self.assertEqual(response.status_code, 400, response.content)
        response = self.client.get(f"/api/balance/?user_id={self.foreign_child.pk}")
        self.assertEqual(response.status_code, 404, response.content)

    def test_disputed_negative_hourly_does_not_release_pending_credit(self):
        self.card(Timecard.Status.PENDING)
        PaymentService.record_entry(self.child, Decimal("-4.00"), PaymentLedger.EntryType.HOURLY)
        data = self.client.get(self.base + f"overview/?user_id={self.child.pk}").json()
        self.assertEqual(data["approved_payable"], "26.00")
        self.assertEqual(data["pending_hourly"], "5.00")

    def test_payment_is_confirmed_once_and_does_not_increment_snapshot(self):
        snapshot = self.post("snapshot", {"amount": "40.25", "as_of": timezone.now().isoformat(), "memo": "Checked app"})
        self.assertEqual(snapshot.status_code, 201, snapshot.content)
        self.assertEqual(snapshot.json()["created_by"], self.parent.pk)
        first = self.payout()
        repeat = self.payout()
        self.assertEqual((first.status_code, repeat.status_code), (201, 200))
        self.assertFalse(repeat.json()["created"])
        self.assertEqual(first.json()["payout"]["id"], repeat.json()["payout"]["id"])
        self.assertEqual(self.payouts().count(), 1)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("20.00"))
        self.assertEqual(GreenlightBalanceSnapshot.objects.get().amount, Decimal("40.25"))

    def test_changed_retry_key_or_reference_payload_conflicts(self):
        self.payout()
        for changes in ({"amount": "9.00"}, {"memo": "Changed"}, {"idempotency_key": "another-key", "amount": "9.00"}):
            with self.subTest(changes=changes):
                response = self.payout(**changes)
                self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(self.payouts().count(), 1)

    def test_same_reference_with_new_key_returns_original(self):
        first = self.payout()
        second = self.payout(idempotency_key="another-key")
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.json()["payout"]["id"], second.json()["payout"]["id"])
        self.assertEqual(self.payouts().count(), 1)

    def test_bad_amounts_and_future_dates_have_no_side_effects(self):
        for amount in (None, "NaN", "Infinity", "-1.00", "0.00", "1.001", "1000000.00", "31.00"):
            with self.subTest(amount=amount):
                response = self.payout(amount=amount)
                self.assertEqual(response.status_code, 400, response.content)
        response = self.payout(transferred_on=(timezone.localdate() + timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.payouts().exists())
        self.assertFalse(GreenlightTransfer.objects.exists())

    def test_future_or_negative_balance_snapshots_rejected(self):
        for data in (
            {"amount": "-1.00", "as_of": timezone.now().isoformat()},
            {"amount": "5.00", "as_of": (timezone.now() + timedelta(days=1)).isoformat()},
        ):
            response = self.post("snapshot", data)
            self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(GreenlightBalanceSnapshot.objects.exists())

    def test_older_snapshot_does_not_replace_latest_observation(self):
        now = timezone.now()
        self.post("snapshot", {"amount": "9.00", "as_of": now.isoformat()})
        self.post("snapshot", {"amount": "15.00", "as_of": (now - timedelta(days=1)).isoformat()})
        data = self.client.get(self.base + f"overview/?user_id={self.child.pk}").json()
        self.assertEqual(data["balance_snapshot"]["amount"], "9.00")
        self.assertEqual(GreenlightBalanceSnapshot.objects.count(), 2)

    def test_timecard_confirmation_and_old_mark_paid_retry_do_not_double_debit(self):
        card = self.card()
        response = self.payout(amount="5.00", timecard_id=card.pk)
        self.assertEqual(response.status_code, 201, response.content)
        card.refresh_from_db()
        self.assertEqual(card.status, Timecard.Status.PAID)
        response = self.client.post(f"/api/timecards/{card.pk}/mark-paid/", {"amount": "5.00"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.payouts().count(), 1)

    def test_unallocated_transfer_cannot_be_paid_again_through_old_timecard_route(self):
        PaymentLedger.objects.filter(user=self.child).delete()
        card = self.card()
        response = self.payout(amount="5.00")
        self.assertEqual(response.status_code, 201, response.content)
        response = self.client.post(f"/api/timecards/{card.pk}/mark-paid/", {"amount": "5.00"}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.payouts().count(), 1)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("0.00"))

    def test_pending_or_partial_or_foreign_timecard_cannot_be_confirmed(self):
        card = self.card(Timecard.Status.PENDING)
        for amount in ("5.00", "4.00"):
            response = self.payout(amount=amount, timecard_id=card.pk)
            self.assertEqual(response.status_code, 400, response.content)
        card.status = Timecard.Status.APPROVED
        card.save()
        response = self.payout(amount="4.00", timecard_id=card.pk)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.payouts().exists())

    def test_confirmation_rolls_back_ledger_and_status_when_metadata_fails(self):
        card = self.card()
        with patch("apps.payments.greenlight.GreenlightTransfer.objects.create", side_effect=RuntimeError("metadata failure")):
            with self.assertRaisesRegex(RuntimeError, "metadata failure"):
                confirm_transfer(self.child, self.parent, amount="5.00", transferred_on=date.fromisoformat(self.today), idempotency_key="rollback", timecard_id=card.pk)
        card.refresh_from_db()
        self.assertEqual(card.status, Timecard.Status.APPROVED)
        self.assertFalse(self.payouts().exists())

    def test_preview_and_legacy_import_do_not_write_money(self):
        csv_data = self.csv(f"{self.today},10.00,Pay,t1,transfer", f"{self.today},-3.00,Shop,s1,purchase", f"{self.today},5.00,Gift,g1,credit")
        rows = self.preview(csv_data)
        self.assertEqual([row["eligible"] for row in rows], [True, False, False])
        response = self.client.post("/api/greenlight/import/", {"user_id": self.child.pk, "csv_data": csv_data}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(self.payouts().exists())
        self.assertFalse(GreenlightStatementTransfer.objects.exists())

    def test_selected_transfer_commit_and_retry_are_idempotent(self):
        csv_data = self.csv(f"{self.today},10.00,Pay,t1,transfer", f"{self.today},-3.00,Shop,s1,purchase")
        rows = self.preview(csv_data)
        selection = [{"fingerprint": rows[0]["fingerprint"]}]
        first = self.reconcile(csv_data, selection)
        second = self.reconcile(csv_data, selection)
        self.assertEqual(first.json(), {"recorded": 1, "matched": 0, "duplicates": 0})
        self.assertEqual(second.json(), {"recorded": 0, "matched": 0, "duplicates": 1})
        self.assertEqual(self.payouts().count(), 1)

    def test_reference_dedupes_description_changes_and_rejects_changed_amount(self):
        original = self.csv(f"{self.today},10.00,Pay,t1,transfer")
        fingerprint = self.preview(original)[0]["fingerprint"]
        self.reconcile(original, [{"fingerprint": fingerprint}])
        changed = self.csv(f"{self.today},10.00,Formatted differently,t1,transfer")
        self.assertEqual(self.preview(changed)[0]["fingerprint"], fingerprint)
        self.assertEqual(self.reconcile(changed, [{"fingerprint": fingerprint}]).json()["duplicates"], 1)
        wrong = self.csv(f"{self.today},11.00,Formatted differently,t1,transfer")
        self.assertFalse(self.preview(wrong)[0]["eligible"])
        self.assertEqual(self.reconcile(wrong, [{"fingerprint": fingerprint}]).status_code, 409)
        self.assertEqual(self.payouts().count(), 1)

    def test_reference_conflicts_inside_one_csv_rejected_before_selection(self):
        csv_data = self.csv(f"{self.today},10.00,First,t1,transfer", f"{self.today},11.00,Second,t1,transfer", f"{self.today},10.00,Third,t1,transfer")
        rows = self.preview(csv_data)
        self.assertEqual([row["eligible"] for row in rows], [False, False, False])
        response = self.reconcile(csv_data, [{"fingerprint": rows[0]["fingerprint"]}])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.payouts().exists())

    def test_invalid_referenced_repeat_cannot_be_hidden_by_a_later_valid_row(self):
        csv_data = self.csv(f"{self.today},NaN,Invalid,t1,transfer", f"{self.today},10.00,Valid,t1,transfer")
        rows = self.preview(csv_data)
        self.assertTrue(all(not row["eligible"] and row["error"] for row in rows))
        response = self.reconcile(csv_data, [{"fingerprint": rows[1]["fingerprint"]}])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.payouts().exists())

    def test_reference_and_confirmation_keys_are_scoped_to_child(self):
        self.payout()
        PaymentService.record_entry(self.sibling, Decimal("10.00"), PaymentLedger.EntryType.CHORE_REWARD)
        response = self.post("payout", {
            "amount": "10.00", "transferred_on": self.today, "reference": "transfer-1",
            "memo": "Weekly pay", "idempotency_key": "test-key-1",
        }, child=self.sibling)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(GreenlightTransfer.objects.count(), 2)

    def test_identical_reference_less_rows_conservatively_dedupe(self):
        csv_data = self.csv(f"{self.today},10.00,Pay,,transfer", f"{self.today},10.00,Pay,,transfer")
        rows = self.preview(csv_data)
        self.assertTrue(rows[1]["duplicate"])
        self.assertEqual(rows[0]["fingerprint"], rows[1]["fingerprint"])
        self.reconcile(csv_data, [{"fingerprint": rows[0]["fingerprint"]}])
        self.assertEqual(self.payouts().count(), 1)

    def test_matching_manual_transfer_preserves_ledger_once(self):
        payout = self.payout().json()["payout"]
        csv_data = self.csv(f"{self.today},10.00,Imported description,transfer-1,transfer")
        row = self.preview(csv_data)[0]
        self.assertEqual(row["match_candidates"], [payout["id"]])
        response = self.reconcile(csv_data, [{"fingerprint": row["fingerprint"], "match_payment_id": payout["id"]}])
        self.assertEqual(response.json(), {"recorded": 0, "matched": 1, "duplicates": 0})
        self.assertEqual(self.payouts().count(), 1)
        self.assertEqual(GreenlightStatementTransfer.objects.get().description, "Imported description")

    def test_matching_legacy_timecard_payment_does_not_deduct_twice(self):
        card = self.card()
        paid = self.client.post(f"/api/timecards/{card.pk}/mark-paid/", {"amount": "5.00"}, format="json")
        self.assertEqual(paid.status_code, 200, paid.content)
        entry = self.payouts().get()
        csv_data = self.csv(f"{self.today},5.00,Timecard pay,legacy-1,transfer")
        row = self.preview(csv_data)[0]
        response = self.reconcile(csv_data, [{"fingerprint": row["fingerprint"], "match_payment_id": entry.pk}])
        self.assertEqual(response.json()["matched"], 1)
        self.assertEqual(self.payouts().count(), 1)
        self.assertEqual(GreenlightTransfer.objects.get().payment_entry.timecard_id, card.pk)

    def test_reference_already_confirmed_requires_explicit_matching(self):
        self.payout()
        csv_data = self.csv(f"{self.today},10.00,Pay,transfer-1,transfer")
        row = self.preview(csv_data)[0]
        response = self.reconcile(csv_data, [{"fingerprint": row["fingerprint"]}])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.payouts().count(), 1)

    def test_manual_reference_with_changed_statement_amount_conflicts(self):
        payment_id = self.payout().json()["payout"]["id"]
        csv_data = self.csv(f"{self.today},11.00,Pay,transfer-1,transfer")
        row = self.preview(csv_data)[0]
        self.assertFalse(row["eligible"])
        response = self.reconcile(csv_data, [{"fingerprint": row["fingerprint"], "match_payment_id": payment_id}])
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(self.payouts().count(), 1)

    def test_mismatched_amount_or_child_or_second_row_matching_is_rejected(self):
        payout = self.payout().json()["payout"]
        foreign = PaymentService.record_entry(self.foreign_child, Decimal("-10.00"), PaymentLedger.EntryType.PAYOUT)
        for amount, payment_id in (("9.00", payout["id"]), ("10.00", foreign.pk)):
            csv_data = self.csv(f"{self.today},{amount},Pay,,transfer")
            row = self.preview(csv_data)[0]
            response = self.reconcile(csv_data, [{"fingerprint": row["fingerprint"], "match_payment_id": payment_id}])
            self.assertEqual(response.status_code, 400, response.content)
        first_csv = self.csv(f"{self.today},10.00,One,transfer-1,transfer")
        row = self.preview(first_csv)[0]
        self.reconcile(first_csv, [{"fingerprint": row["fingerprint"], "match_payment_id": payout["id"]}])
        second_csv = self.csv(f"{self.today},10.00,Two,another-ref,transfer")
        row = self.preview(second_csv)[0]
        response = self.reconcile(second_csv, [{"fingerprint": row["fingerprint"], "match_payment_id": payout["id"]}])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(GreenlightStatementTransfer.objects.count(), 1)

    def test_batch_failure_rolls_back_earlier_selected_rows(self):
        csv_data = self.csv(f"{self.today},10.00,One,t1,transfer", f"{self.today},25.00,Two,t2,transfer")
        rows = self.preview(csv_data)
        response = self.reconcile(csv_data, [{"fingerprint": row["fingerprint"]} for row in rows])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.payouts().exists())
        self.assertFalse(GreenlightTransfer.objects.exists())
        self.assertFalse(GreenlightStatementTransfer.objects.exists())

    def test_statement_metadata_failure_rolls_back_new_payment(self):
        csv_data = self.csv(f"{self.today},10.00,One,t1,transfer")
        row = self.preview(csv_data)[0]
        with patch("apps.payments.greenlight.GreenlightStatementTransfer.objects.create", side_effect=RuntimeError("statement failure")):
            with self.assertRaisesRegex(RuntimeError, "statement failure"):
                self.reconcile(csv_data, [{"fingerprint": row["fingerprint"]}])
        self.assertFalse(self.payouts().exists())
        self.assertFalse(GreenlightTransfer.objects.exists())

    def test_bad_csv_headers_sizes_and_rows_rejected_without_mutations(self):
        for csv_data in ("Amount,Description\n10,Pay", "date,amount,description,reference,type\n" + "x" * (512 * 1024), self.csv(*([f"{self.today},1.00,Pay,,transfer"] * 501))):
            response = self.post("preview", {"csv_data": csv_data})
            self.assertEqual(response.status_code, 400, response.content)
        rows = self.preview(self.csv(f"{self.today},NaN,Pay,t1,transfer", f"{self.today},-1,Pay,t2,transfer", f"{self.today},1.001,Pay,t3,transfer", f"{self.today},1.00,Pay,t4,transfer,extra"))
        self.assertTrue(all(not row["eligible"] and row["error"] for row in rows))
        self.assertFalse(self.payouts().exists())

    def test_unknown_or_duplicate_selection_rejected(self):
        csv_data = self.csv(f"{self.today},10.00,One,t1,transfer")
        row = self.preview(csv_data)[0]
        for selections in ([{"fingerprint": "0" * 64}], [{"fingerprint": row["fingerprint"]}] * 2):
            response = self.reconcile(csv_data, selections)
            self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.payouts().exists())

    def test_parent_family_scope_and_child_write_permissions(self):
        for route, data in (
            ("payout", {"amount": "1.00", "transferred_on": self.today, "idempotency_key": "scope"}),
            ("snapshot", {"amount": "1.00", "as_of": timezone.now().isoformat()}),
            ("preview", {"csv_data": self.csv(f"{self.today},1.00,Pay,t1,transfer")}),
            ("reconcile", {"csv_data": self.csv(f"{self.today},1.00,Pay,t1,transfer"), "selections": [{"fingerprint": "0" * 64}]}),
        ):
            response = self.post(route, data, child=self.foreign_child)
            self.assertEqual(response.status_code, 404, response.content)
            self.client.force_authenticate(self.child)
            response = self.post(route, data)
            self.assertEqual(response.status_code, 403, response.content)
            self.client.force_authenticate(self.parent)
        self.client.force_authenticate(self.child)
        own = self.client.get(self.base + "overview/")
        self.assertEqual(own.status_code, 200, own.content)
        self.assertEqual(own.json()["user_id"], self.child.pk)
        sibling = self.client.get(self.base + f"overview/?user_id={self.sibling.pk}")
        self.assertEqual(sibling.status_code, 404, sibling.content)
        self.client.force_authenticate(self.foreign_parent)
        foreign = self.client.get(self.base + f"overview/?user_id={self.child.pk}")
        self.assertEqual(foreign.status_code, 404, foreign.content)

    def test_legacy_payout_url_requires_confirmation_and_shares_retry_safety(self):
        bare = self.client.post("/api/payments/payout/", {"user_id": self.child.pk, "amount": 1}, format="json")
        self.assertEqual(bare.status_code, 400, bare.content)
        data = {"user_id": self.child.pk, "amount": "10.00", "transferred_on": self.today, "idempotency_key": "legacy-safe"}
        for expected in (201, 200):
            response = self.client.post("/api/payments/payout/", data, format="json")
            self.assertEqual(response.status_code, expected, response.content)
        self.assertEqual(self.payouts().count(), 1)
