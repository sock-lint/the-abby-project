"""Every Forge surface is scoped to one household. Nothing crosses.

A deployment hosts many unrelated families. The Forge adds a printer, a
budget, a request queue and a job feed per household, and every one of them
is a leak if the queryset forgets its family filter — a print request carries
a child's name and reason, a printer carries a LAN address, and a budget
carries what a family will spend.

Invariants this file exists to protect, each asserted from the other
household's side of the fence:

1. Listing requests, jobs, budgets and printers returns only your family's.
2. Retrieving another family's row by id is a 404 — not a 403, which would
   confirm the row exists.
3. Deciding on another family's request is a 404.
4. Patching another family's budget is a 404.
5. A job in your family can never be linked to another family's request,
   even by a parent who legitimately owns the job.

Modelled on ``apps/chores/tests/test_family_scoping.py``.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.printing.budget import PrintBudgetService
from apps.printing.models import PrinterProfile, PrintJob, PrintRequest
from apps.printing.services import PrintRequestService
from config.tests.factories import make_family

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "printing-scoping-tests",
    },
}


@override_settings(CACHES=LOCMEM)
class _TwoFamilyFixture(APITestCase):
    def setUp(self):
        self.alpha = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.bravo = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        self.alpha_parent = self.alpha.parents[0]
        self.alpha_kid = self.alpha.children[0]
        self.bravo_parent = self.bravo.parents[0]
        self.bravo_kid = self.bravo.children[0]

        self.alpha_printer = PrinterProfile.objects.create(
            family=self.alpha.family, name="Alpha X1C",
            serial="00M09A0000000AA", host="192.168.1.50",
        )
        self.bravo_printer = PrinterProfile.objects.create(
            family=self.bravo.family, name="Bravo P1S",
            serial="00M09A0000000BB", host="10.0.0.50",
        )

        self.alpha_request = self.submit(self.alpha_kid, "Alpha dragon")
        self.bravo_request = self.submit(self.bravo_kid, "Bravo dragon")

        self.alpha_job = PrintJob.objects.create(
            printer=self.alpha_printer, subtask_name="alpha-plate",
            normalized_name="alpha-plate", state=PrintJob.State.RUNNING,
        )
        self.bravo_job = PrintJob.objects.create(
            printer=self.bravo_printer, subtask_name="bravo-plate",
            normalized_name="bravo-plate", state=PrintJob.State.RUNNING,
        )

        self.alpha_budget = PrintBudgetService.get_budget(self.alpha_kid)
        self.bravo_budget = PrintBudgetService.get_budget(self.bravo_kid)

    @staticmethod
    def submit(user, title):
        return PrintRequestService.create_request(
            user, title=title, reason="because", color="red",
            source_kind=PrintRequest.SourceKind.OTHER_URL,
        )

    @staticmethod
    def ids(response):
        body = response.json()
        rows = body["results"] if isinstance(body, dict) and "results" in body else body
        return [row["id"] for row in rows]


class RequestScopingTests(_TwoFamilyFixture):
    def test_listing_requests_never_crosses_families(self):
        self.client.force_authenticate(self.alpha_parent)
        ids = self.ids(self.client.get("/api/print-requests/"))
        self.assertIn(self.alpha_request.id, ids)
        self.assertNotIn(self.bravo_request.id, ids)

    def test_retrieving_another_familys_request_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.get(f"/api/print-requests/{self.bravo_request.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_approving_another_familys_request_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.post(
            f"/api/print-requests/{self.bravo_request.id}/approve/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.bravo_request.refresh_from_db()
        self.assertEqual(self.bravo_request.status, PrintRequest.Status.PENDING)

    def test_rejecting_another_familys_request_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.post(
            f"/api/print-requests/{self.bravo_request.id}/reject/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_cancelling_another_familys_request_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.post(
            f"/api/print-requests/{self.bravo_request.id}/cancel/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_deleting_another_familys_request_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.delete(f"/api/print-requests/{self.bravo_request.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(PrintRequest.objects.filter(pk=self.bravo_request.pk).exists())

    def test_a_parent_cannot_file_a_request_for_another_familys_child(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.post("/api/print-requests/", {
            "user_id": self.bravo_kid.id,
            "title": "Sneaky",
            "source_url": "https://makerworld.com/en/models/1",
            "color": "red",
            "reason": "nope",
        }, format="json")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(PrintRequest.objects.filter(title="Sneaky").exists())


class JobScopingTests(_TwoFamilyFixture):
    def test_listing_jobs_never_crosses_families(self):
        self.client.force_authenticate(self.alpha_parent)
        ids = self.ids(self.client.get("/api/print-jobs/"))
        self.assertIn(self.alpha_job.id, ids)
        self.assertNotIn(self.bravo_job.id, ids)

    def test_retrieving_another_familys_job_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        self.assertEqual(
            self.client.get(f"/api/print-jobs/{self.bravo_job.id}/").status_code, 404,
        )

    def test_linking_your_own_job_to_another_familys_request_is_a_404(self):
        approved = PrintRequestService.approve(
            self.bravo_request, self.bravo_parent, estimated_grams=Decimal("10.00"),
        )
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.post(f"/api/print-jobs/{self.alpha_job.id}/link/", {
            "request_id": approved.id,
        }, format="json")
        self.assertEqual(resp.status_code, 404)
        self.alpha_job.refresh_from_db()
        self.assertIsNone(self.alpha_job.request)

    def test_unlinking_another_familys_job_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.post(
            f"/api/print-jobs/{self.bravo_job.id}/unlink/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 404)


class BudgetScopingTests(_TwoFamilyFixture):
    def test_listing_budgets_never_crosses_families(self):
        self.client.force_authenticate(self.alpha_parent)
        ids = self.ids(self.client.get("/api/print-budgets/"))
        self.assertIn(self.alpha_budget.id, ids)
        self.assertNotIn(self.bravo_budget.id, ids)

    def test_retrieving_another_familys_budget_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        self.assertEqual(
            self.client.get(f"/api/print-budgets/{self.bravo_budget.id}/").status_code,
            404,
        )

    def test_patching_another_familys_budget_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.patch(f"/api/print-budgets/{self.bravo_budget.id}/", {
            "grams_per_month": "1.00",
        }, format="json")
        self.assertEqual(resp.status_code, 404)
        self.bravo_budget.refresh_from_db()
        self.assertIsNone(self.bravo_budget.grams_per_month)

    def test_adjusting_another_familys_budget_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.post(f"/api/print-budgets/{self.bravo_budget.id}/adjust/", {
            "grams": "500.00",
        }, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_reading_another_familys_ledger_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        self.assertEqual(
            self.client.get(
                f"/api/print-budgets/{self.bravo_budget.id}/ledger/",
            ).status_code,
            404,
        )


class PrinterScopingTests(_TwoFamilyFixture):
    def test_listing_printers_never_crosses_families(self):
        self.client.force_authenticate(self.alpha_parent)
        ids = self.ids(self.client.get("/api/printers/"))
        self.assertIn(self.alpha_printer.id, ids)
        self.assertNotIn(self.bravo_printer.id, ids)

    def test_retrieving_another_familys_printer_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        self.assertEqual(
            self.client.get(f"/api/printers/{self.bravo_printer.id}/").status_code, 404,
        )

    def test_reading_another_familys_printer_status_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        self.assertEqual(
            self.client.get(
                f"/api/printers/{self.bravo_printer.id}/status/",
            ).status_code,
            404,
        )

    def test_patching_another_familys_printer_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        resp = self.client.patch(f"/api/printers/{self.bravo_printer.id}/", {
            "name": "Mine now", "serial": self.bravo_printer.serial,
            "access_code": "00000000",
        }, format="json")
        self.assertEqual(resp.status_code, 404)
        self.bravo_printer.refresh_from_db()
        self.assertEqual(self.bravo_printer.name, "Bravo P1S")

    def test_deleting_another_familys_printer_is_a_404(self):
        self.client.force_authenticate(self.alpha_parent)
        self.assertEqual(
            self.client.delete(f"/api/printers/{self.bravo_printer.id}/").status_code,
            404,
        )
        self.assertTrue(
            PrinterProfile.objects.filter(pk=self.bravo_printer.pk).exists(),
        )

    def test_a_printer_created_without_a_family_lands_in_the_default_family(self):
        # Defense in depth, matching User / Reward / ProjectTemplate: a
        # fixture that forgets the family gets a known home rather than an
        # IntegrityError.
        from apps.families.models import Family

        orphan = PrinterProfile.objects.create(name="Legacy", serial="00M09A0000000CC")
        self.assertEqual(orphan.family, Family.objects.get(slug="default-family"))
