"""Pins the PrintRequest lifecycle: submit → decide → print → close out.

Invariants this file exists to protect:

1. Submitting tells the parents about it and leaves an audit trail — the
   request is worthless to a parent who never learns it exists.
2. Approval is the **only** place a slug is minted, it embeds the primary
   key, and it hands back the exact plate filename the parent must type.
3. A request that already carries a slug keeps it forever. Re-minting after
   a failed print would orphan a plate the parent already sliced and saved.
4. Only pending requests can be approved or rejected; every other transition
   raises ``PrintRequestError`` rather than silently re-deciding.
5. The monthly budget is a guard rail at approval, not a lock: it raises
   ``BudgetExceededError`` (carrying ``.problems``) but yields to ``force``,
   and it never fires when the family set no caps.
6. Cancelling is allowed right up until a print starts, and never after.
7. Manual linking denormalises ``user``, stamps ``link_source=manual``,
   writes a timeline row, and drags an approved request into ``printing``.
8. Linking and unlinking both refuse a job that has already been debited —
   moving a closed-out job would need a compensating pair of ledger entries.
9. Closing out a job that never linked to a request writes no ledger row.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.notifications.models import Notification, NotificationType
from apps.printing.budget import PrintBudgetService
from apps.printing.models import (
    PrintBudget,
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintJobEvent,
    PrintRequest,
)
from apps.printing.services import (
    BudgetExceededError,
    PrintRequestError,
    PrintRequestService,
)
from config.tests.factories import make_family


class _Fixture(TestCase):
    """One family, one printer, and a helper for the common submit call."""

    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid", "display_name": "Abby"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.printer = PrinterProfile.objects.create(
            family=self.household.family,
            name="Garage X1C",
            serial="00M09A000000001",
            host="192.168.1.50",
        )

    def submit(self, title="Articulated Dragon", **kwargs):
        payload = {
            "title": title,
            "reason": "I want to paint it",
            "color": "glow in the dark green",
            "source_kind": PrintRequest.SourceKind.MAKERWORLD,
            "source_url": "https://makerworld.com/en/models/1",
        }
        payload.update(kwargs)
        return PrintRequestService.create_request(self.child, **payload)

    def open_job(self, *, subtask_name="req-0001-dragon", request=None):
        return PrintJob.objects.create(
            printer=self.printer,
            request=request,
            user=request.user if request else None,
            subtask_name=subtask_name,
            normalized_name=subtask_name,
            state=PrintJob.State.RUNNING,
        )


class CreateRequestTests(_Fixture):
    def test_create_request_starts_pending_with_no_slug(self):
        request = self.submit()
        self.assertEqual(request.status, PrintRequest.Status.PENDING)
        self.assertEqual(request.slug, "")
        self.assertEqual(request.plate_filename, "")

    def test_create_request_notifies_every_parent_in_the_family(self):
        request = self.submit()
        note = Notification.objects.get(
            user=self.parent,
            notification_type=NotificationType.PRINT_REQUEST_SUBMITTED,
        )
        self.assertIn(request.title, note.message)
        self.assertIn("Abby", note.message)
        self.assertEqual(note.link, "/quests?tab=forge")

    def test_create_request_does_not_notify_the_child(self):
        self.submit()
        self.assertFalse(
            Notification.objects.filter(
                user=self.child,
                notification_type=NotificationType.PRINT_REQUEST_SUBMITTED,
            ).exists(),
        )

    def test_create_request_writes_an_activity_event(self):
        request = self.submit()
        event = ActivityEvent.objects.get(event_type="print.request.submitted")
        self.assertEqual(event.subject, self.child)
        self.assertEqual(event.actor, self.child)
        self.assertEqual(event.target_id, request.pk)
        self.assertEqual(event.category, "approval")

    def test_blank_title_falls_back_to_a_placeholder(self):
        request = self.submit(title="")
        self.assertEqual(request.title, "Untitled print")


class ApproveTests(_Fixture):
    def test_approve_mints_a_slug_embedding_the_primary_key(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        request.refresh_from_db()
        self.assertEqual(
            request.slug, f"req-{request.pk:04d}-articulated-dragon",
        )

    def test_approve_sets_plate_filename_to_the_slug_plus_3mf(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        request.refresh_from_db()
        self.assertEqual(request.plate_filename, f"{request.slug}.3mf")

    def test_approve_stamps_the_decision_audit_fields(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent, notes="ok, one spool")
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.APPROVED)
        self.assertEqual(request.decided_by, self.parent)
        self.assertIsNotNone(request.decided_at)
        self.assertEqual(request.parent_notes, "ok, one spool")

    def test_approve_stores_the_slicer_estimates(self):
        request = self.submit()
        PrintRequestService.approve(
            request, self.parent,
            estimated_grams=Decimal("120.50"), estimated_minutes=240,
        )
        request.refresh_from_db()
        self.assertEqual(request.estimated_grams, Decimal("120.50"))
        self.assertEqual(request.estimated_minutes, 240)

    def test_approve_notifies_the_child(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        note = Notification.objects.get(
            user=self.child,
            notification_type=NotificationType.PRINT_REQUEST_APPROVED,
        )
        self.assertIn(request.title, note.message)

    def test_approving_an_already_approved_request_raises(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.approve(request, self.parent)

    def test_approving_a_rejected_request_raises(self):
        request = self.submit()
        PrintRequestService.reject(request, self.parent)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.approve(request, self.parent)

    def test_re_approval_keeps_the_original_slug(self):
        # A print that failed can be re-decided. Re-minting would orphan the
        # plate the parent already sliced under the old name.
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        request.refresh_from_db()
        original_slug = request.slug
        original_plate = request.plate_filename

        # Re-open the decision the way a failed-then-retried request does,
        # and change the title so a fresh mint would be visibly different.
        request.status = PrintRequest.Status.PENDING
        request.title = "Completely Different Name"
        request.save(update_fields=["status", "title"])

        PrintRequestService.approve(request, self.parent)
        request.refresh_from_db()
        self.assertEqual(request.slug, original_slug)
        self.assertEqual(request.plate_filename, original_plate)


class ApproveBudgetTests(_Fixture):
    def test_approve_raises_when_the_estimate_exceeds_the_grams_cap(self):
        PrintBudget.objects.update_or_create(
            user=self.child, defaults={"grams_per_month": Decimal("100.00")},
        )
        request = self.submit()
        with self.assertRaises(BudgetExceededError) as ctx:
            PrintRequestService.approve(
                request, self.parent, estimated_grams=Decimal("250.00"),
            )
        self.assertEqual(len(ctx.exception.problems), 1)
        self.assertIn("250.00g", ctx.exception.problems[0])

    def test_budget_exceeded_carries_one_problem_per_blown_dimension(self):
        PrintBudget.objects.update_or_create(
            user=self.child,
            defaults={"grams_per_month": Decimal("100.00"), "minutes_per_month": 60},
        )
        request = self.submit()
        with self.assertRaises(BudgetExceededError) as ctx:
            PrintRequestService.approve(
                request, self.parent,
                estimated_grams=Decimal("250.00"), estimated_minutes=600,
            )
        self.assertEqual(len(ctx.exception.problems), 2)

    def test_a_refused_approval_leaves_the_request_pending_and_unslugged(self):
        PrintBudget.objects.update_or_create(
            user=self.child, defaults={"grams_per_month": Decimal("10.00")},
        )
        request = self.submit()
        with self.assertRaises(BudgetExceededError):
            PrintRequestService.approve(
                request, self.parent, estimated_grams=Decimal("250.00"),
            )
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.PENDING)
        self.assertEqual(request.slug, "")

    def test_force_approves_over_the_cap_and_records_it(self):
        PrintBudget.objects.update_or_create(
            user=self.child, defaults={"grams_per_month": Decimal("100.00")},
        )
        request = self.submit()
        PrintRequestService.approve(
            request, self.parent, estimated_grams=Decimal("250.00"), force=True,
        )
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.APPROVED)

        event = ActivityEvent.objects.get(event_type="print.request.approved")
        self.assertTrue(event.context["extras"]["forced_over_budget"])

    def test_a_normal_approval_is_not_marked_forced(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        event = ActivityEvent.objects.get(event_type="print.request.approved")
        self.assertFalse(event.context["extras"]["forced_over_budget"])

    def test_approve_never_raises_when_no_caps_are_set(self):
        # Both caps null is the default: "no cap on either dimension".
        budget = PrintBudgetService.get_budget(self.child)
        self.assertIsNone(budget.grams_per_month)
        self.assertIsNone(budget.minutes_per_month)
        request = self.submit()
        PrintRequestService.approve(
            request, self.parent,
            estimated_grams=Decimal("99999.00"), estimated_minutes=99999,
        )
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.APPROVED)


class RejectTests(_Fixture):
    def test_reject_stamps_the_decision_and_notifies_the_child(self):
        request = self.submit()
        PrintRequestService.reject(request, self.parent, notes="too much filament")
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.REJECTED)
        self.assertEqual(request.decided_by, self.parent)
        self.assertIsNotNone(request.decided_at)
        note = Notification.objects.get(
            user=self.child,
            notification_type=NotificationType.PRINT_REQUEST_REJECTED,
        )
        self.assertIn("too much filament", note.message)

    def test_reject_never_mints_a_slug(self):
        request = self.submit()
        PrintRequestService.reject(request, self.parent)
        request.refresh_from_db()
        self.assertEqual(request.slug, "")

    def test_rejecting_a_non_pending_request_raises(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.reject(request, self.parent)


class CancelTests(_Fixture):
    def test_cancel_works_from_pending(self):
        request = self.submit()
        PrintRequestService.cancel(request, self.child)
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.CANCELLED)

    def test_cancel_works_from_approved(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        PrintRequestService.cancel(request, self.parent)
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.CANCELLED)

    def test_cancel_writes_an_activity_event(self):
        request = self.submit()
        PrintRequestService.cancel(request, self.child)
        event = ActivityEvent.objects.get(event_type="print.request.cancelled")
        self.assertEqual(event.subject, self.child)

    def test_cancelling_a_printing_request_raises(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        request.status = PrintRequest.Status.PRINTING
        request.save(update_fields=["status"])
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(request, self.parent)

    def test_cancelling_a_completed_request_raises(self):
        request = self.submit()
        PrintRequestService.approve(request, self.parent)
        request.status = PrintRequest.Status.COMPLETED
        request.save(update_fields=["status"])
        with self.assertRaises(PrintRequestError):
            PrintRequestService.cancel(request, self.parent)


class LinkJobTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.request = self.submit()
        PrintRequestService.approve(
            self.request, self.parent, estimated_grams=Decimal("50.00"),
        )
        self.request.refresh_from_db()
        self.job = self.open_job(subtask_name="whatever-she-called-it")

    def test_link_job_binds_the_job_to_the_request(self):
        PrintRequestService.link_job(self.job, self.request, self.parent)
        self.job.refresh_from_db()
        self.assertEqual(self.job.request, self.request)

    def test_link_job_marks_the_link_as_manual(self):
        PrintRequestService.link_job(self.job, self.request, self.parent)
        self.job.refresh_from_db()
        self.assertEqual(self.job.link_source, PrintJob.LinkSource.MANUAL)

    def test_link_job_denormalises_the_owning_user_onto_the_job(self):
        self.assertIsNone(self.job.user)
        PrintRequestService.link_job(self.job, self.request, self.parent)
        self.job.refresh_from_db()
        self.assertEqual(self.job.user, self.child)

    def test_link_job_writes_a_linked_timeline_row(self):
        PrintRequestService.link_job(self.job, self.request, self.parent)
        event = self.job.events.get(kind=PrintJobEvent.Kind.LINKED)
        self.assertIn(self.request.title, event.message)
        self.assertEqual(event.context["request_id"], self.request.pk)
        self.assertTrue(event.context["manual"])

    def test_link_job_moves_an_approved_request_to_printing(self):
        PrintRequestService.link_job(self.job, self.request, self.parent)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, PrintRequest.Status.PRINTING)
        self.assertIsNotNone(self.request.started_at)

    def test_link_job_leaves_the_status_alone_when_the_job_already_closed(self):
        self.job.finished_at = timezone.now()
        self.job.state = PrintJob.State.FINISHED
        self.job.save(update_fields=["finished_at", "state"])
        PrintRequestService.link_job(self.job, self.request, self.parent)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, PrintRequest.Status.APPROVED)

    def test_link_job_refuses_a_job_that_has_already_been_debited(self):
        self.job.finished_at = timezone.now()
        self.job.grams_debited = Decimal("50.00")
        self.job.minutes_debited = 90
        self.job.save(update_fields=[
            "finished_at", "grams_debited", "minutes_debited",
        ])
        with self.assertRaises(PrintRequestError) as ctx:
            PrintRequestService.link_job(self.job, self.request, self.parent)
        self.assertIn("adjustment", str(ctx.exception))
        self.job.refresh_from_db()
        self.assertIsNone(self.job.request)

    def test_link_job_refuses_a_rejected_request(self):
        rejected = self.submit(title="No thanks")
        PrintRequestService.reject(rejected, self.parent)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.link_job(self.job, rejected, self.parent)

    def test_link_job_refuses_a_cancelled_request(self):
        cancelled = self.submit(title="Changed my mind")
        PrintRequestService.cancel(cancelled, self.child)
        with self.assertRaises(PrintRequestError):
            PrintRequestService.link_job(self.job, cancelled, self.parent)


class UnlinkJobTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.request = self.submit()
        PrintRequestService.approve(
            self.request, self.parent, estimated_grams=Decimal("50.00"),
        )
        self.request.refresh_from_db()
        self.job = self.open_job(subtask_name="mislinked")
        PrintRequestService.link_job(self.job, self.request, self.parent)
        self.job.refresh_from_db()
        self.request.refresh_from_db()

    def test_unlink_job_detaches_the_request_and_the_user(self):
        PrintRequestService.unlink_job(self.job, self.parent)
        self.job.refresh_from_db()
        self.assertIsNone(self.job.request)
        self.assertIsNone(self.job.user)
        self.assertEqual(self.job.link_source, PrintJob.LinkSource.UNLINKED)

    def test_unlink_job_writes_an_unlinked_timeline_row(self):
        PrintRequestService.unlink_job(self.job, self.parent)
        event = self.job.events.get(kind=PrintJobEvent.Kind.UNLINKED)
        self.assertEqual(event.context["previous_request_id"], self.request.pk)

    def test_unlink_job_puts_a_printing_request_back_to_approved(self):
        self.assertEqual(self.request.status, PrintRequest.Status.PRINTING)
        PrintRequestService.unlink_job(self.job, self.parent)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, PrintRequest.Status.APPROVED)

    def test_unlink_job_refuses_a_job_that_has_already_been_debited(self):
        self.job.grams_debited = Decimal("50.00")
        self.job.save(update_fields=["grams_debited"])
        with self.assertRaises(PrintRequestError):
            PrintRequestService.unlink_job(self.job, self.parent)
        self.job.refresh_from_db()
        self.assertEqual(self.job.request, self.request)


class CloseOutTests(_Fixture):
    def test_close_out_of_an_unlinked_job_writes_no_ledger_row(self):
        job = self.open_job(subtask_name="somebody-elses-plate")
        job.state = PrintJob.State.FINISHED
        job.finished_at = timezone.now()
        job.duration_minutes = 45
        job.save(update_fields=["state", "finished_at", "duration_minutes"])

        self.assertIsNone(PrintRequestService.close_out(job))
        self.assertFalse(PrintBudgetLedger.objects.exists())
        job.refresh_from_db()
        self.assertIsNone(job.grams_debited)

    def test_close_out_is_idempotent_for_an_already_debited_job(self):
        request = self.submit()
        PrintRequestService.approve(
            request, self.parent, estimated_grams=Decimal("50.00"),
        )
        request.refresh_from_db()
        job = self.open_job(subtask_name=request.slug, request=request)
        job.state = PrintJob.State.FINISHED
        job.finished_at = timezone.now()
        job.duration_minutes = 45
        job.save(update_fields=["state", "finished_at", "duration_minutes"])

        PrintRequestService.close_out(job)
        job.refresh_from_db()
        self.assertEqual(PrintBudgetLedger.objects.count(), 1)

        # A duplicate FINISH report (the printer re-sends on reconnect) must
        # not debit the child twice.
        PrintRequestService.close_out(job)
        self.assertEqual(PrintBudgetLedger.objects.count(), 1)
