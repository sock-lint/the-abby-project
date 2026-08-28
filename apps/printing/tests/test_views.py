"""Pins the REST surface of the Forge. Every documented endpoint is hit here.

Invariants this file exists to protect:

1. Role scoping at the queryset: a child sees only her own requests, a parent
   sees the whole family's — and never another household's.
2. Deciding is a parent's job. A child may submit, edit and cancel; approving
   and rejecting are parent-only.
3. Over-budget approval answers **409 with ``problems``**, not a bare refusal,
   and yields to ``force: true``. The guard rail is a rail, not a lock.
4. The approve response carries ``plate_filename``. That string is what the
   parent reads off the screen and types into Bambu Studio; if it stops being
   returned, the whole deterministic-matching scheme silently degrades to
   hand-linking.
5. ``preview`` soft-fails: a dead model host still yields 200 and a
   URL-derived title, because the child can still submit.
6. Manual linking is parent-only and family-scoped — a request id from
   another household is a 404, never a 200.
7. Printer credentials never leave the server. No serialised body may carry
   ``encrypted_secret`` / ``access_code``, and the access code string must not
   appear anywhere in a response.
8. The live status endpoint reads the listener's cache, so a cold cache is a
   clean ``connected: false`` rather than an error or a second MQTT socket.
"""
from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.printing.budget import PrintBudgetService
from apps.printing.models import (
    PrintBudget,
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintRequest,
)
from apps.printing.services import PrintRequestService
from config.tests.factories import make_family

ACCESS_CODE = "87654321"

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "printing-view-tests",
    },
}


class FakeResponse:
    """The shape ``config.url_safety.safe_get`` hands back, minus the socket."""

    def __init__(self, content=b"", status_code=200, content_type="text/html"):
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


MODEL_PAGE_HTML = (
    b"<html><head>"
    b'<meta property="og:title" content="Articulated Dragon">'
    b'<meta property="og:image" content="https://cdn.example.com/dragon.jpg">'
    b'<meta property="og:site_name" content="MakerWorld">'
    b"</head><body></body></html>"
)


def rows(response):
    """Unwrap a PageNumberPagination body (or a bare list)."""
    body = response.json()
    return body["results"] if isinstance(body, dict) and "results" in body else body


@override_settings(CACHES=LOCMEM)
class _ApiFixture(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}, {"username": "sibling"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.sibling = self.household.children[1]

        self.printer = PrinterProfile.objects.create(
            family=self.household.family,
            name="Garage X1C",
            serial="00M09A000000001",
            host="192.168.1.50",
        )
        self.printer.set_secrets(access_code=ACCESS_CODE)
        self.printer.save(update_fields=["encrypted_secret"])

        # Nothing in this file is allowed to touch the network. Every outbound
        # fetch in the Forge goes through the SSRF-guarded wrapper, so one
        # patch there covers preview + the enrichment task.
        patcher = mock.patch(
            "apps.printing.metadata.safe_get",
            side_effect=RuntimeError("no network in tests"),
        )
        self.safe_get = patcher.start()
        self.addCleanup(patcher.stop)

    # -- helpers -------------------------------------------------------- #
    def make_request(self, user=None, *, title="Articulated Dragon", **kwargs):
        payload = {
            "title": title,
            "reason": "I want to paint it",
            "color": "green",
            "source_kind": PrintRequest.SourceKind.MAKERWORLD,
            "source_url": "https://makerworld.com/en/models/1",
        }
        payload.update(kwargs)
        return PrintRequestService.create_request(user or self.child, **payload)

    def approved_request(self, user=None, **kwargs):
        request = self.make_request(user, **kwargs)
        return PrintRequestService.approve(
            request, self.parent, estimated_grams=Decimal("50.00"),
            estimated_minutes=90,
        )

    def make_job(self, *, request=None, subtask_name="mystery-plate", open_=True):
        return PrintJob.objects.create(
            printer=self.printer,
            request=request,
            user=request.user if request else None,
            subtask_name=subtask_name,
            normalized_name=subtask_name,
            state=PrintJob.State.RUNNING,
            finished_at=None if open_ else timezone.now(),
        )


# --------------------------------------------------------------------------- #
# /api/print-requests/
# --------------------------------------------------------------------------- #
class PrintRequestListTests(_ApiFixture):
    def test_a_child_sees_only_her_own_requests(self):
        mine = self.make_request(self.child)
        theirs = self.make_request(self.sibling, title="Sibling thing")

        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/print-requests/")
        self.assertEqual(resp.status_code, 200)
        ids = [row["id"] for row in rows(resp)]
        self.assertIn(mine.id, ids)
        self.assertNotIn(theirs.id, ids)

    def test_a_parent_sees_the_whole_family(self):
        mine = self.make_request(self.child)
        theirs = self.make_request(self.sibling, title="Sibling thing")

        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/print-requests/")
        ids = [row["id"] for row in rows(resp)]
        self.assertIn(mine.id, ids)
        self.assertIn(theirs.id, ids)

    def test_a_parent_can_filter_to_one_child(self):
        self.make_request(self.child)
        theirs = self.make_request(self.sibling, title="Sibling thing")

        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/print-requests/?user_id={self.sibling.id}")
        self.assertEqual([row["id"] for row in rows(resp)], [theirs.id])

    def test_status_filter_accepts_a_csv(self):
        pending = self.make_request(self.child)
        approved = self.approved_request(self.child, title="Approved thing")

        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/print-requests/?status=approved")
        ids = [row["id"] for row in rows(resp)]
        self.assertIn(approved.id, ids)
        self.assertNotIn(pending.id, ids)

    def test_retrieve_returns_the_full_card_shape(self):
        request = self.make_request(self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.get(f"/api/print-requests/{request.id}/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["title"], "Articulated Dragon")
        self.assertEqual(body["status"], "pending")
        self.assertIn("plate_filename", body)
        self.assertIn("latest_job", body)

    def test_anonymous_callers_are_refused(self):
        self.assertEqual(self.client.get("/api/print-requests/").status_code, 401)


class PrintRequestCreateTests(_ApiFixture):
    def test_a_child_submits_a_link_request(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/print-requests/", {
            "title": "Baby Yoda",
            "source_url": "https://www.printables.com/model/12345-baby-yoda",
            "color": "green",
            "reason": "for my desk",
            "needed_by": "2026-12-01",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["user"], self.child.id)
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["source_kind"], "printables")

    def test_a_child_submits_an_uploaded_model(self):
        upload = SimpleUploadedFile(
            "dragon.3mf", b"\xff\xd8\xff\xe0" + b"\x00" * 100,
            content_type="application/octet-stream",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/print-requests/", {
            "title": "My own design",
            "model_file": upload,
            "color": "black",
            "reason": "I made it in Tinkercad",
        }, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["source_kind"], "upload")

    def test_a_request_needs_a_link_or_a_file(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/print-requests/", {
            "color": "black", "reason": "just because",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_a_parent_files_on_behalf_of_a_child(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/print-requests/", {
            "user_id": self.child.id,
            "title": "Bracket",
            "source_url": "https://makerworld.com/en/models/9",
            "color": "black",
            "reason": "fixes the shelf",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["user"], self.child.id)

    def test_a_parent_must_say_which_child(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/print-requests/", {
            "title": "Bracket",
            "source_url": "https://makerworld.com/en/models/9",
            "color": "black",
            "reason": "fixes the shelf",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("user_id", resp.json()["error"])


class PrintRequestEditTests(_ApiFixture):
    def test_the_owner_can_patch_the_narrow_field_set(self):
        request = self.make_request(self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.patch(f"/api/print-requests/{request.id}/", {
            "color": "translucent blue", "needed_by": "2027-01-05",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["color"], "translucent blue")

    def test_a_sibling_cannot_patch_somebody_elses_request(self):
        request = self.make_request(self.child)
        self.client.force_authenticate(self.sibling)
        resp = self.client.patch(
            f"/api/print-requests/{request.id}/", {"color": "pink"}, format="json",
        )
        # Not even visible to her, so this is a 404 rather than a 403.
        self.assertEqual(resp.status_code, 404)

    def test_a_closed_request_can_no_longer_be_edited(self):
        request = self.approved_request(self.child)
        request.status = PrintRequest.Status.COMPLETED
        request.save(update_fields=["status"])
        self.client.force_authenticate(self.child)
        resp = self.client.patch(
            f"/api/print-requests/{request.id}/", {"color": "pink"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_only_a_parent_may_delete(self):
        request = self.make_request(self.child)
        self.client.force_authenticate(self.child)
        self.assertEqual(
            self.client.delete(f"/api/print-requests/{request.id}/").status_code, 403,
        )
        self.client.force_authenticate(self.parent)
        self.assertEqual(
            self.client.delete(f"/api/print-requests/{request.id}/").status_code, 204,
        )
        self.assertFalse(PrintRequest.objects.filter(pk=request.pk).exists())


class PrintRequestApproveTests(_ApiFixture):
    def test_approve_returns_the_plate_filename_the_parent_must_type(self):
        request = self.make_request(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-requests/{request.id}/approve/", {
            "estimated_grams": "120.00", "estimated_minutes": 240,
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["plate_filename"], f"req-{request.id:04d}-articulated-dragon.3mf")
        self.assertEqual(body["slug"], f"req-{request.id:04d}-articulated-dragon")

    def test_approve_over_budget_is_a_409_naming_the_problem(self):
        PrintBudget.objects.update_or_create(
            user=self.child, defaults={"grams_per_month": Decimal("100.00")},
        )
        request = self.make_request(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-requests/{request.id}/approve/", {
            "estimated_grams": "250.00",
        }, format="json")
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(len(body["problems"]), 1)
        self.assertIn("filament", body["problems"][0])
        self.assertIn("budget", body)
        self.assertEqual(
            Decimal(str(body["budget"]["grams_per_month"])), Decimal("100.00"),
        )
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.PENDING)

    def test_force_approves_the_same_request_that_just_409d(self):
        PrintBudget.objects.update_or_create(
            user=self.child, defaults={"grams_per_month": Decimal("100.00")},
        )
        request = self.make_request(self.child)
        self.client.force_authenticate(self.parent)
        self.client.post(f"/api/print-requests/{request.id}/approve/", {
            "estimated_grams": "250.00",
        }, format="json")
        resp = self.client.post(f"/api/print-requests/{request.id}/approve/", {
            "estimated_grams": "250.00", "force": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], "approved")

    def test_approving_a_decided_request_is_a_400(self):
        request = self.approved_request(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/print-requests/{request.id}/approve/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_reject_records_the_note(self):
        request = self.make_request(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-requests/{request.id}/reject/", {
            "notes": "not this month",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], "rejected")
        self.assertEqual(resp.json()["parent_notes"], "not this month")

    def test_a_parent_cannot_reach_another_familys_request(self):
        other = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        theirs = self.make_request(other.children[0], title="Their dragon")
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/print-requests/{theirs.id}/approve/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_a_child_cannot_approve_her_own_request(self):
        # Regression: a get_permissions() override used to return
        # [IsAuthenticated] unconditionally, silently discarding the
        # permission_classes=[IsParent] on the @action decorator. A child
        # could self-approve — minting a plate name and skipping the budget
        # check, which is the entire point of parent approval. See
        # config.viewsets.action_declares_permissions.
        request = self.make_request(self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/print-requests/{request.id}/approve/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_a_child_cannot_reject_her_own_request(self):
        # Same regression as above.
        request = self.make_request(self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/print-requests/{request.id}/reject/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 403)


class PrintRequestCancelTests(_ApiFixture):
    def test_the_owner_can_cancel(self):
        request = self.make_request(self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/print-requests/{request.id}/cancel/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], "cancelled")

    def test_a_parent_can_cancel_on_a_childs_behalf(self):
        request = self.approved_request(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/print-requests/{request.id}/cancel/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_cancelling_a_printing_request_is_a_400(self):
        request = self.approved_request(self.child)
        request.status = PrintRequest.Status.PRINTING
        request.save(update_fields=["status"])
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/print-requests/{request.id}/cancel/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 400)


class LinkPreviewTests(_ApiFixture):
    def test_preview_returns_scraped_metadata(self):
        with mock.patch(
            "apps.printing.metadata.safe_get",
            return_value=FakeResponse(MODEL_PAGE_HTML),
        ):
            self.client.force_authenticate(self.child)
            resp = self.client.post("/api/print-requests/preview/", {
                "url": "https://makerworld.com/en/models/1",
            }, format="json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["title"], "Articulated Dragon")
        self.assertEqual(body["thumbnail_url"], "https://cdn.example.com/dragon.jpg")
        self.assertEqual(body["author"], "MakerWorld")
        self.assertEqual(body["source_kind"], "makerworld")
        self.assertIsNone(body["error"])

    def test_preview_soft_fails_with_a_url_derived_title(self):
        # safe_get is patched to raise for the whole fixture. A dead model
        # host must still let the child submit.
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/print-requests/preview/", {
            "url": "https://www.printables.com/model/12345-articulated-dragon",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["title"], "Articulated Dragon")
        self.assertEqual(body["source_kind"], "printables")
        self.assertTrue(body["error"])

    def test_preview_needs_a_url(self):
        self.client.force_authenticate(self.child)
        self.assertEqual(
            self.client.post("/api/print-requests/preview/", {}, format="json")
            .status_code,
            400,
        )


# --------------------------------------------------------------------------- #
# /api/print-jobs/
# --------------------------------------------------------------------------- #
class PrintJobViewTests(_ApiFixture):
    def test_a_parent_sees_unmatched_jobs_a_child_cannot(self):
        unmatched = self.make_job()

        self.client.force_authenticate(self.parent)
        self.assertIn(unmatched.id, [row["id"] for row in rows(
            self.client.get("/api/print-jobs/"))])

        self.client.force_authenticate(self.child)
        self.assertNotIn(unmatched.id, [row["id"] for row in rows(
            self.client.get("/api/print-jobs/"))])

    def test_the_unlinked_filter_returns_only_jobs_needing_a_link(self):
        unmatched = self.make_job()
        linked = self.make_job(
            request=self.approved_request(self.child), subtask_name="req-0001-dragon",
            open_=False,
        )
        self.client.force_authenticate(self.parent)
        ids = [row["id"] for row in rows(
            self.client.get("/api/print-jobs/?unlinked=true"))]
        self.assertIn(unmatched.id, ids)
        self.assertNotIn(linked.id, ids)

    def test_the_open_filter_returns_only_running_jobs(self):
        running = self.make_job()
        done = self.make_job(subtask_name="older-plate", open_=False)
        self.client.force_authenticate(self.parent)
        ids = [row["id"] for row in rows(self.client.get("/api/print-jobs/?open=true"))]
        self.assertIn(running.id, ids)
        self.assertNotIn(done.id, ids)

    def test_a_job_carries_its_timeline(self):
        request = self.approved_request(self.child)
        job = self.make_job(request=request, subtask_name=request.slug)
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/print-jobs/{job.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("events", resp.json())

    def test_a_parent_links_an_unmatched_job(self):
        request = self.approved_request(self.child)
        job = self.make_job()
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-jobs/{job.id}/link/", {
            "request_id": request.id,
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["request"], request.id)
        self.assertEqual(resp.json()["link_source"], "manual")

    def test_a_child_cannot_link_a_job(self):
        request = self.approved_request(self.child)
        job = self.make_job()
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/print-jobs/{job.id}/link/", {
            "request_id": request.id,
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_linking_to_another_familys_request_is_a_404(self):
        other = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        theirs = PrintRequestService.approve(
            self.make_request(other.children[0], title="Their dragon"),
            other.parents[0],
        )
        job = self.make_job()
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-jobs/{job.id}/link/", {
            "request_id": theirs.id,
        }, format="json")
        self.assertEqual(resp.status_code, 404)
        job.refresh_from_db()
        self.assertIsNone(job.request)

    def test_linking_a_debited_job_is_a_400(self):
        request = self.approved_request(self.child)
        job = self.make_job(open_=False)
        job.grams_debited = Decimal("30.00")
        job.save(update_fields=["grams_debited"])
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-jobs/{job.id}/link/", {
            "request_id": request.id,
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_a_parent_unlinks_a_mislinked_job(self):
        request = self.approved_request(self.child)
        job = self.make_job()
        PrintRequestService.link_job(job, request, self.parent)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-jobs/{job.id}/unlink/", {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.json()["request"])
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.APPROVED)

    def test_a_child_cannot_unlink_a_job(self):
        request = self.approved_request(self.child)
        job = self.make_job()
        PrintRequestService.link_job(job, request, self.parent)
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/print-jobs/{job.id}/unlink/", {}, format="json")
        self.assertEqual(resp.status_code, 403)


# --------------------------------------------------------------------------- #
# /api/print-budgets/
# --------------------------------------------------------------------------- #
class PrintBudgetViewTests(_ApiFixture):
    def test_listing_materialises_a_budget_row_per_child(self):
        self.assertEqual(PrintBudget.objects.count(), 0)
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/print-budgets/")
        self.assertEqual(resp.status_code, 200)
        usernames = {row["username"] for row in rows(resp)}
        self.assertEqual(usernames, {"kid", "sibling"})

    def test_a_child_sees_only_her_own_budget(self):
        PrintBudgetService.get_budget(self.child)
        PrintBudgetService.get_budget(self.sibling)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/print-budgets/")
        self.assertEqual([row["username"] for row in rows(resp)], ["kid"])

    def test_a_parent_sets_the_monthly_caps(self):
        budget = PrintBudgetService.get_budget(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/print-budgets/{budget.id}/", {
            "grams_per_month": "500.00", "minutes_per_month": 1200,
            "notes": "one spool a month",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["grams_per_month"], "500.00")
        self.assertEqual(body["minutes_remaining"], 1200)

    def test_a_child_cannot_raise_her_own_cap(self):
        budget = PrintBudgetService.get_budget(self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.patch(f"/api/print-budgets/{budget.id}/", {
            "grams_per_month": "99999.00",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_adjust_appends_a_ledger_row(self):
        budget = PrintBudgetService.get_budget(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-budgets/{budget.id}/adjust/", {
            "grams": "25.00", "note": "spool she wasted",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        # Note the type: capped values render as DecimalField strings while
        # the rolled-up usage comes back through a SerializerMethodField and
        # lands as a JSON number. The frontend has to cope with both.
        self.assertEqual(Decimal(str(resp.json()["grams_used"])), Decimal("25.00"))
        entry = PrintBudgetLedger.objects.get(user=self.child)
        self.assertEqual(entry.reason, PrintBudgetLedger.Reason.ADJUSTMENT)
        self.assertEqual(entry.recorded_by, self.parent)

    def test_a_negative_adjustment_is_recorded_as_a_refund(self):
        budget = PrintBudgetService.get_budget(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/print-budgets/{budget.id}/adjust/", {
            "grams": "-25.00", "note": "bad debit",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            PrintBudgetLedger.objects.get(user=self.child).reason,
            PrintBudgetLedger.Reason.REFUND,
        )

    def test_an_empty_adjustment_is_a_400(self):
        budget = PrintBudgetService.get_budget(self.child)
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/print-budgets/{budget.id}/adjust/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_a_child_cannot_adjust_her_own_budget(self):
        budget = PrintBudgetService.get_budget(self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/print-budgets/{budget.id}/adjust/", {
            "grams": "-500.00",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_the_ledger_endpoint_lists_recent_entries(self):
        budget = PrintBudgetService.get_budget(self.child)
        PrintBudgetService.record(
            self.child, grams=Decimal("40.00"), minutes=60,
            reason=PrintBudgetLedger.Reason.PRINT_COMPLETED,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get(f"/api/print-budgets/{budget.id}/ledger/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["grams"], "40.00")
        self.assertEqual(body[0]["reason"], "print_completed")


# --------------------------------------------------------------------------- #
# /api/printers/
# --------------------------------------------------------------------------- #
class PrinterProfileViewTests(_ApiFixture):
    def test_a_parent_lists_only_their_own_familys_printers(self):
        other = make_family("Bravo", parents=[{"username": "bravo_parent"}])
        PrinterProfile.objects.create(
            family=other.family, name="Their P1S", serial="00M09A000000099",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/printers/")
        self.assertEqual([row["serial"] for row in rows(resp)], ["00M09A000000001"])

    def test_a_parent_registers_a_printer_with_its_access_code(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/printers/", {
            "name": "Basement P1S",
            "serial": "00M09A000000002",
            "host": "192.168.1.51",
            "access_code": "abcd1234",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.json()["has_credentials"])
        printer = PrinterProfile.objects.get(serial="00M09A000000002")
        self.assertEqual(printer.family, self.household.family)
        self.assertEqual(printer.get_secrets()["access_code"], "abcd1234")

    def test_registering_without_an_access_code_is_a_400_not_a_broken_printer(self):
        # The whole point: a printer the listener can never dial used to 201
        # and then sit in the list wearing a red "No credentials" badge, with
        # the field that fixes it hidden behind Edit. Refuse it at the point
        # the parent is still looking at the form.
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/printers/", {
            "name": "Basement P1S",
            "serial": "00M09A000000010",
            "host": "192.168.1.51",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("access_code", resp.json())
        self.assertIn("Settings", resp.json()["access_code"][0])
        self.assertFalse(
            PrinterProfile.objects.filter(serial="00M09A000000010").exists(),
        )

    def test_a_lan_printer_without_a_host_is_a_400_on_the_host_field(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/printers/", {
            "name": "Basement P1S", "serial": "00M09A000000011",
            "access_code": "abcd1234",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(list(resp.json()), ["host"])

    def test_a_cloud_printer_needs_a_uid_and_a_token(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/printers/", {
            "name": "Cloud X1C", "serial": "00M09A000000012", "transport": "cloud",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            sorted(resp.json()), ["cloud_token", "cloud_user_id"],
        )

    def test_switching_transport_without_the_new_credentials_is_refused(self):
        # A LAN printer flipped to cloud keeps its access code, which is
        # useless there — the write must not leave a printer the supervisor
        # will silently skip.
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/printers/{self.printer.id}/", {
            "transport": "cloud",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(sorted(resp.json()), ["cloud_token", "cloud_user_id"])
        self.printer.refresh_from_db()
        self.assertEqual(self.printer.transport, PrinterProfile.Transport.LOCAL)

    def test_clearing_a_stored_access_code_is_refused(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/printers/{self.printer.id}/", {
            "access_code": "",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.printer.refresh_from_db()
        self.assertEqual(self.printer.get_secrets()["access_code"], ACCESS_CODE)

    def test_re_adding_a_serial_answers_400_rather_than_500(self):
        # (family, serial) is unique in the database and this is a plain
        # Serializer, so nothing turned that into a validation error: a parent
        # who removed a printer and re-added it got an IntegrityError 500.
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/printers/", {
            "name": "Garage X1C again", "serial": self.printer.serial,
            "host": "192.168.1.50", "access_code": "abcd1234",
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("serial", resp.json())

    def test_the_same_serial_in_another_household_is_fine(self):
        other = make_family("Bravo", parents=[{"username": "bravo_parent2"}])
        self.client.force_authenticate(other.parents[0])
        resp = self.client.post("/api/printers/", {
            "name": "Their X1C", "serial": self.printer.serial,
            "host": "10.0.0.9", "access_code": "abcd1234",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_a_rename_keeps_its_own_serial_without_tripping_the_clash_check(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/printers/{self.printer.id}/", {
            "name": "Garage X1C v2", "serial": self.printer.serial,
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_the_read_shape_says_which_field_is_missing(self):
        broken = PrinterProfile.objects.create(
            family=self.household.family, name="Half-configured P1S",
            serial="00M09A000000013", host="192.168.1.60",
        )
        self.client.force_authenticate(self.parent)
        body = self.client.get(f"/api/printers/{broken.id}/").json()
        self.assertFalse(body["has_credentials"])
        self.assertEqual(body["missing_credentials"], ["access_code"])
        self.assertIn("access code", body["credential_hint"])
        # And a healthy printer says nothing, so the card stays quiet.
        ok_body = self.client.get(f"/api/printers/{self.printer.id}/").json()
        self.assertEqual(ok_body["missing_credentials"], [])
        self.assertEqual(ok_body["credential_hint"], "")

    def test_saving_a_printer_clears_the_supervisors_stale_complaint(self):
        PrinterProfile.objects.filter(pk=self.printer.pk).update(
            last_error="No LAN access code saved — ...",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/printers/{self.printer.id}/", {
            "access_code": "99887766",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["last_error"], "")

    def test_a_child_cannot_register_a_printer(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/printers/", {
            "name": "Mine now", "serial": "00M09A000000003",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_no_response_ever_carries_the_access_code(self):
        self.client.force_authenticate(self.parent)
        for url in ("/api/printers/", f"/api/printers/{self.printer.id}/",
                    f"/api/printers/{self.printer.id}/status/"):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                self.assertNotIn(ACCESS_CODE, resp.content.decode())
                self.assertNotIn(b"encrypted_secret", resp.content)
                self.assertNotIn(b"access_code", resp.content)

    def test_a_patch_that_omits_the_access_code_does_not_wipe_it(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/printers/{self.printer.id}/", {
            "name": "Renamed X1C", "serial": self.printer.serial,
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotIn(ACCESS_CODE, resp.content.decode())
        self.printer.refresh_from_db()
        self.assertEqual(self.printer.name, "Renamed X1C")
        self.assertEqual(self.printer.get_secrets()["access_code"], ACCESS_CODE)

    def test_a_parent_deletes_a_printer(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/printers/{self.printer.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(PrinterProfile.objects.filter(pk=self.printer.pk).exists())

    def test_a_child_may_read_printers_but_not_change_them(self):
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/printers/").status_code, 200)
        self.assertEqual(
            self.client.delete(f"/api/printers/{self.printer.id}/").status_code, 403,
        )

    def test_status_is_disconnected_when_the_listener_cache_is_cold(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/printers/{self.printer.id}/status/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["connected"])
        self.assertIsNone(body["live"])
        self.assertIsNone(body["job"])
        self.assertEqual(body["printer"]["serial"], self.printer.serial)

    def test_status_serves_the_listeners_snapshot_and_the_open_job(self):
        from apps.printing import fanout

        request = self.approved_request(self.child)
        job = self.make_job(request=request, subtask_name=request.slug)
        fanout.publish_state(self.printer.serial, {
            "serial": self.printer.serial, "gcode_state": "RUNNING", "percent": 42,
        })
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/printers/{self.printer.id}/status/")
        body = resp.json()
        self.assertTrue(body["connected"])
        self.assertEqual(body["live"]["percent"], 42)
        self.assertEqual(body["job"]["id"], job.id)
