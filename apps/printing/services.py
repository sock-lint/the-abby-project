"""Request lifecycle: submit → approve/reject → print → close out.

``PrintJobService`` (the MQTT-facing half) lives in ``jobs.py`` so this
module stays about the human workflow and doesn't import transport code.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.activity.services import ActivityLogService
from apps.notifications.models import NotificationType
from apps.notifications.services import get_display_name, notify, notify_parents
from config.services import finalize_decision

from .budget import PrintBudgetService, quantize_grams
from .matching import mint_slug, plate_filename_for
from .models import PrintBudgetLedger, PrintJob, PrintJobEvent, PrintRequest

logger = logging.getLogger(__name__)

#: Where the frontend surfaces the Forge. Used for notification deep links.
FORGE_LINK = "/quests?tab=forge"


class PrintRequestError(Exception):
    """A request transition that isn't allowed from the current state."""


class BudgetExceededError(PrintRequestError):
    """Approval would push the child past their monthly cap.

    Carries ``problems`` so the API can render the specific overage rather
    than a generic refusal. The parent can re-submit with ``force=true``;
    this is a guard rail, not a lock.
    """

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


class PrintRequestService:
    # ------------------------------------------------------------------ #
    # Submit
    # ------------------------------------------------------------------ #
    @staticmethod
    @transaction.atomic
    def create_request(user, *, title, reason, color, source_kind, source_url="",
                       thumbnail_url="", source_author="", needed_by=None,
                       model_file=None):
        """Create a pending request and tell the parents about it.

        Metadata enrichment (title/thumbnail scraped from the link) runs
        afterwards via Celery so a slow or unreachable model host never
        blocks the child's submit — see ``tasks.enrich_request_metadata``.
        """
        request = PrintRequest.objects.create(
            user=user,
            title=(title or "").strip()[:160] or "Untitled print",
            reason=reason,
            color=color,
            source_kind=source_kind,
            source_url=source_url or "",
            source_author=source_author or "",
            thumbnail_url=thumbnail_url or "",
            needed_by=needed_by,
            model_file=model_file,
            status=PrintRequest.Status.PENDING,
        )

        notify_parents(
            "New print request",
            f"{get_display_name(user)} wants {request.title} printed"
            + (f" — needed by {request.needed_by}" if request.needed_by else ""),
            NotificationType.PRINT_REQUEST_SUBMITTED,
            link=FORGE_LINK,
            about_user=user,
        )
        ActivityLogService.record(
            category="approval",
            event_type="print.request.submitted",
            summary=f"Print request: {request.title}",
            actor=user,
            subject=user,
            target=request,
            extras={"source_kind": source_kind, "source_url": source_url},
        )
        return request

    # ------------------------------------------------------------------ #
    # Decide
    # ------------------------------------------------------------------ #
    @staticmethod
    @transaction.atomic
    def approve(request, parent, *, estimated_grams=None, estimated_minutes=None,
                notes="", force=False):
        """Approve, mint the slug, and hand back the exact plate filename.

        The slug is minted here and **only** here. It embeds the request's
        primary key, so it is unique by construction and stable across
        re-prints — which is what makes ``subtask_name`` matching an
        equality check instead of a guess. A request that already carries a
        slug (re-approved after a failure) keeps it: re-minting would orphan
        a plate the parent has already sliced and saved.
        """
        # Re-fetch under a row lock before deciding. Two parents tapping
        # Approve at the same moment would otherwise both pass the status
        # check, both run the budget check against the same pre-debit
        # remaining, and both notify the child. Same guard shape as
        # ChoreService.approve_completion.
        request = PrintRequest.objects.select_for_update().get(pk=request.pk)
        if request.status != PrintRequest.Status.PENDING:
            raise PrintRequestError(
                f"Only pending requests can be approved (this one is "
                f"{request.get_status_display().lower()}).",
            )

        if estimated_grams is not None:
            request.estimated_grams = estimated_grams
        if estimated_minutes is not None:
            request.estimated_minutes = estimated_minutes

        if not force:
            problems = PrintBudgetService.check_affordable(
                request.user,
                grams=request.estimated_grams,
                minutes=request.estimated_minutes,
            )
            if problems:
                raise BudgetExceededError(problems)

        if not request.slug:
            request.slug = mint_slug(request.pk, request.title)
            request.plate_filename = plate_filename_for(request.slug)

        request.save(update_fields=[
            "slug", "plate_filename", "estimated_grams", "estimated_minutes",
            "updated_at",
        ])

        finalize_decision(
            request,
            PrintRequest.Status.APPROVED,
            parent,
            notes,
            activity_category="approval",
            activity_event_type="print.request.approved",
            activity_summary=f"Approved print: {request.title}",
            activity_extras={
                "plate_filename": request.plate_filename,
                "estimated_grams": str(request.estimated_grams or ""),
                "forced_over_budget": bool(force),
            },
        )

        notify(
            request.user,
            "Print request approved",
            f"{request.title} is approved. It'll start when the printer picks it up.",
            NotificationType.PRINT_REQUEST_APPROVED,
            link=FORGE_LINK,
        )
        return request

    @staticmethod
    @transaction.atomic
    def reject(request, parent, notes=""):
        request = PrintRequest.objects.select_for_update().get(pk=request.pk)
        if request.status != PrintRequest.Status.PENDING:
            raise PrintRequestError(
                f"Only pending requests can be rejected (this one is "
                f"{request.get_status_display().lower()}).",
            )
        finalize_decision(
            request,
            PrintRequest.Status.REJECTED,
            parent,
            notes,
            activity_category="approval",
            activity_event_type="print.request.rejected",
            activity_summary=f"Rejected print: {request.title}",
        )
        notify(
            request.user,
            "Print request declined",
            (notes or f"{request.title} wasn't approved this time.")[:500],
            NotificationType.PRINT_REQUEST_REJECTED,
            link=FORGE_LINK,
        )
        return request

    @staticmethod
    @transaction.atomic
    def cancel(request, actor):
        """Withdraw a request. Owner or parent, pending or approved only.

        Approved-and-cancelled is allowed on purpose: plans change between
        approval and slicing. Once a print has actually started the request
        is a record of something that happened, so it can't be cancelled.
        """
        if request.status not in (PrintRequest.Status.PENDING,
                                  PrintRequest.Status.APPROVED):
            raise PrintRequestError(
                "Only pending or approved requests can be cancelled.",
            )
        request.status = PrintRequest.Status.CANCELLED
        request.save(update_fields=["status", "updated_at"])
        ActivityLogService.record(
            category="approval",
            event_type="print.request.cancelled",
            summary=f"Cancelled print request: {request.title}",
            actor=actor,
            subject=request.user,
            target=request,
        )
        return request

    # ------------------------------------------------------------------ #
    # Manual link — the Handy escape hatch
    # ------------------------------------------------------------------ #
    @staticmethod
    @transaction.atomic
    def link_job(job: PrintJob, request: PrintRequest, parent):
        """Bind an unmatched job to a request by hand.

        This is the fallback for a plate started from Handy without the
        minted filename. It is intentionally parent-only and intentionally
        the *only* non-deterministic path in the system.

        Re-linking an already-linked job is allowed (a parent fixing a
        mis-link) but a job that has already been closed out and debited is
        not — the ledger row is written against the old request and moving
        it would need a compensating pair of entries. Unlink-then-relink
        before close-out, or make an adjustment after.
        """
        if job.grams_debited is not None or job.minutes_debited is not None:
            raise PrintRequestError(
                "This print has already been closed out and its budget "
                "debited. Record a budget adjustment instead of re-linking.",
            )
        if request.status in (PrintRequest.Status.REJECTED,
                              PrintRequest.Status.CANCELLED):
            raise PrintRequestError(
                "Can't link a print to a rejected or cancelled request.",
            )

        previous = job.request
        job.request = request
        job.user = request.user
        job.link_source = PrintJob.LinkSource.MANUAL
        job.save(update_fields=["request", "user", "link_source", "updated_at"])

        PrintJobEvent.objects.create(
            job=job,
            kind=PrintJobEvent.Kind.LINKED,
            message=f"Linked to “{request.title}” by {get_display_name(parent)}",
            context={
                "request_id": request.pk,
                "previous_request_id": previous.pk if previous else None,
                "manual": True,
            },
        )

        # A job linked after it already started should still move the
        # request into `printing` so the child's card reflects reality.
        if job.is_open and request.status == PrintRequest.Status.APPROVED:
            request.status = PrintRequest.Status.PRINTING
            request.started_at = request.started_at or job.started_at
            request.save(update_fields=["status", "started_at", "updated_at"])

        ActivityLogService.record(
            category="system",
            event_type="print.job.linked",
            summary=f"Linked print “{job.subtask_name}” to {request.title}",
            actor=parent,
            subject=request.user,
            target=job,
            extras={"request_id": request.pk, "manual": True},
        )
        return job

    @staticmethod
    @transaction.atomic
    def unlink_job(job: PrintJob, parent):
        """Detach a job from its request (mis-link repair, pre-close-out)."""
        if job.grams_debited is not None or job.minutes_debited is not None:
            raise PrintRequestError(
                "This print has already been closed out and its budget "
                "debited. Record a budget adjustment instead of unlinking.",
            )
        previous = job.request
        job.request = None
        job.user = None
        job.link_source = PrintJob.LinkSource.UNLINKED
        job.save(update_fields=["request", "user", "link_source", "updated_at"])
        PrintJobEvent.objects.create(
            job=job,
            kind=PrintJobEvent.Kind.UNLINKED,
            message=f"Unlinked by {get_display_name(parent)}",
            context={"previous_request_id": previous.pk if previous else None},
        )
        if previous is not None and previous.status == PrintRequest.Status.PRINTING:
            # Nothing else is printing it; put it back in the approved queue.
            has_other_open = previous.jobs.filter(finished_at__isnull=True).exists()
            if not has_other_open:
                previous.status = PrintRequest.Status.APPROVED
                previous.save(update_fields=["status", "updated_at"])
        return job

    # ------------------------------------------------------------------ #
    # Close-out, called by PrintJobService when a job reaches a terminal state
    # ------------------------------------------------------------------ #
    @staticmethod
    def close_out(job: PrintJob):
        """Move the linked request to its terminal status and debit budget.

        Idempotent: a job whose ``grams_debited`` is already set has been
        closed out and is skipped, so a duplicate FINISH report (the printer
        re-sends state on reconnect) can't double-debit.
        """
        request = job.request
        if job.grams_debited is not None:
            return request
        if request is None:
            # An unlinked print still consumed machine time, but we have no
            # child to bill and no request to close. The job row + timeline
            # stand on their own; a parent can link it and adjust manually.
            return None

        succeeded = job.state == PrintJob.State.FINISHED
        cancelled = job.state == PrintJob.State.CANCELLED
        estimate = request.estimated_grams or 0
        if succeeded:
            grams = quantize_grams(estimate)
            reason = PrintBudgetLedger.Reason.PRINT_COMPLETED
        else:
            # A cancelled or failed print still burned filament up to the
            # point it stopped, so it is debited proportionally rather than
            # forgiven — but only for what actually got laid down.
            grams = PrintBudgetService.grams_for_failed_print(
                estimate, job.layer_num, job.total_layer_num,
            )
            reason = PrintBudgetLedger.Reason.PRINT_FAILED

        minutes = job.duration_minutes or 0

        with transaction.atomic():
            PrintBudgetService.record(
                request.user,
                grams=grams,
                minutes=minutes,
                reason=reason,
                request=request,
                job=job,
                note=job.failure_reason[:200] if not succeeded else "",
            )
            job.grams_debited = grams
            job.minutes_debited = minutes
            job.save(update_fields=["grams_debited", "minutes_debited", "updated_at"])

            PrintJobEvent.objects.create(
                job=job,
                kind=PrintJobEvent.Kind.BUDGET,
                message=(
                    f"Debited {grams}g of filament and {minutes} min of print time"
                    + ("" if succeeded else " (partial — print did not finish)")
                ),
                context={
                    "grams": str(grams),
                    "minutes": minutes,
                    "estimated_grams": str(estimate),
                    "layers_done": job.layer_num,
                    "layers_total": job.total_layer_num,
                },
            )

            if succeeded:
                request.status = PrintRequest.Status.COMPLETED
                request.completed_at = job.finished_at or timezone.now()
            elif cancelled:
                # Somebody stopped it on the printer. That is not a failure of
                # the request — the plate is still approved and still named,
                # so a re-slice-and-print re-binds to the same slug.
                request.status = PrintRequest.Status.APPROVED
            else:
                request.status = PrintRequest.Status.FAILED
                request.completed_at = job.finished_at or timezone.now()
            request.save(update_fields=["status", "completed_at", "updated_at"])

        PrintRequestService._notify_finished(
            request, job, succeeded, grams, minutes, cancelled=cancelled,
        )
        return request

    @staticmethod
    def _notify_finished(request, job, succeeded, grams, minutes, *, cancelled=False):
        if cancelled:
            notify(
                request.user,
                "Your print was stopped",
                f"{request.title} was cancelled on the printer. It's still "
                f"approved — it can go back on whenever the printer is free.",
                NotificationType.PRINT_FAILED,
                link=FORGE_LINK,
            )
        elif succeeded:
            notify(
                request.user,
                "Your print is done",
                f"{request.title} finished after {minutes} min. "
                f"That used {grams}g of your filament budget.",
                NotificationType.PRINT_FINISHED,
                link=FORGE_LINK,
            )
            notify_parents(
                "Print finished",
                f"{request.title} for {get_display_name(request.user)} finished.",
                NotificationType.PRINT_FINISHED,
                link=FORGE_LINK,
                about_user=request.user,
            )
        else:
            reason = job.failure_reason or "The printer stopped before it finished."
            notify(
                request.user,
                "Your print stopped",
                f"{request.title} didn't finish. {reason}",
                NotificationType.PRINT_FAILED,
                link=FORGE_LINK,
            )
            notify_parents(
                "Print failed",
                f"{request.title} for {get_display_name(request.user)} failed: {reason}",
                NotificationType.PRINT_FAILED,
                link=FORGE_LINK,
                about_user=request.user,
            )

        if PrintBudgetService.is_low(request.user):
            notify(
                request.user,
                "Filament budget running low",
                "You're near your monthly print allowance. New requests may "
                "have to wait for next month.",
                NotificationType.PRINT_BUDGET_LOW,
                link=FORGE_LINK,
            )
            notify_parents(
                "Print budget running low",
                f"{get_display_name(request.user)} is near their monthly print allowance.",
                NotificationType.PRINT_BUDGET_LOW,
                link=FORGE_LINK,
                about_user=request.user,
            )
