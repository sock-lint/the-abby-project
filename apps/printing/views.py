"""REST surface for the Forge.

Four viewsets:

``PrintRequestViewSet``   child submits, parent decides. Role-filtered.
``PrintJobViewSet``       read-only observed prints + the manual link fallback.
``PrintBudgetViewSet``    per-child monthly caps + the ledger.
``PrinterProfileViewSet`` parent-only printer config. Family-scoped.

Cross-family safety follows the house chokepoints: ``RoleFilteredQuerySetMixin``
for per-user rows, an explicit ``family=`` filter for per-family rows, and
``get_child_or_404(..., requesting_user=request.user)`` wherever a parent
targets a child by id.
"""
from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from config.permissions import IsParent
from config.viewsets import (
    ParentWritePermissionMixin,
    RoleFilteredQuerySetMixin,
    action_declares_permissions,
    child_not_found_response,
    get_child_or_404,
)

from .budget import PrintBudgetService
from .metadata import classify_url, fetch_link_metadata
from .models import (
    PrintBudget,
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintJobEvent,
    PrintRequest,
)
from .serializers import (
    LinkPreviewSerializer,
    PrintBudgetAdjustSerializer,
    PrintBudgetLedgerSerializer,
    PrintBudgetSerializer,
    PrinterProfileSerializer,
    PrinterProfileWriteSerializer,
    PrintJobLinkSerializer,
    PrintJobSerializer,
    PrintRequestApproveSerializer,
    PrintRequestEditSerializer,
    PrintRequestRejectSerializer,
    PrintRequestSerializer,
    PrintRequestWriteSerializer,
)
from .services import BudgetExceededError, PrintRequestError, PrintRequestService


class PrintRequestViewSet(RoleFilteredQuerySetMixin, viewsets.ModelViewSet):
    """`/api/print-requests/` — the child-facing half of the Forge."""

    serializer_class = PrintRequestSerializer
    role_filter_field = "user"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    # No PUT: everything mutating goes through an action or a narrow PATCH.
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = (
        PrintRequest.objects
        .select_related("user", "decided_by")
        .prefetch_related(
            Prefetch("jobs", queryset=PrintJob.objects.order_by("-started_at")),
        )
    )

    def get_permissions(self):
        if action_declares_permissions(self):
            return super().get_permissions()
        if self.action in ("destroy",):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = self.get_role_filtered_queryset(super().get_queryset())
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status__in=[s for s in status_filter.split(",") if s])
        user_id = self.request.query_params.get("user_id")
        if user_id and self.request.user.role == "parent":
            qs = qs.filter(user_id=user_id)
        return qs

    # ------------------------------------------------------------------ #
    def create(self, request, *args, **kwargs):
        write = PrintRequestWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = write.validated_data

        target_user = request.user
        if request.user.role == "parent":
            child_id = data.get("user_id") or request.data.get("user_id")
            if not child_id:
                return Response(
                    {"error": "Pass user_id to file a print request for a child."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            target_user = get_child_or_404(child_id, requesting_user=request.user)
            if target_user is None:
                return child_not_found_response()

        source_url = data.get("source_url", "")
        model_file = data.get("model_file")
        source_kind = (
            classify_url(source_url) if source_url
            else PrintRequest.SourceKind.UPLOAD
        )

        print_request = PrintRequestService.create_request(
            target_user,
            title=data.get("title", ""),
            reason=data["reason"],
            color=data["color"],
            source_kind=source_kind,
            source_url=source_url,
            needed_by=data.get("needed_by"),
            model_file=model_file,
        )

        # Enrich asynchronously — a slow model host must never block a submit.
        # Falls back to running inline when Celery isn't reachable so a
        # single-container dev setup still gets a thumbnail.
        if source_url:
            from .tasks import enrich_request_metadata

            try:
                enrich_request_metadata.delay(print_request.pk)
            except Exception:  # noqa: BLE001 - broker down / eager mode
                enrich_request_metadata(print_request.pk)
            print_request.refresh_from_db()

        return Response(
            PrintRequestSerializer(print_request).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        """Narrow edits only, and only while the decision is still open."""
        instance = self.get_object()
        if request.user.role != "parent" and instance.user_id != request.user.id:
            raise PermissionDenied("You can only edit your own print requests.")
        if instance.status not in (PrintRequest.Status.PENDING,
                                   PrintRequest.Status.APPROVED):
            return Response(
                {"error": "This request has already been printed or closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        edit = PrintRequestEditSerializer(instance, data=request.data, partial=True)
        edit.is_valid(raise_exception=True)
        edit.save()
        return Response(PrintRequestSerializer(instance).data)

    # ------------------------------------------------------------------ #
    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def approve(self, request, pk=None):
        """Approve and mint the plate filename.

        A 409 means "this would blow the monthly budget" and carries the
        specific overage in ``problems``; the parent can re-POST with
        ``force: true``. That's a guard rail, not a lock — the parent is the
        one who decides.
        """
        print_request = self.get_object()
        payload = PrintRequestApproveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            print_request = PrintRequestService.approve(
                print_request,
                request.user,
                estimated_grams=payload.validated_data.get("estimated_grams"),
                estimated_minutes=payload.validated_data.get("estimated_minutes"),
                notes=payload.validated_data.get("notes", ""),
                force=payload.validated_data.get("force", False),
            )
        except BudgetExceededError as exc:
            return Response(
                {
                    "error": (
                        "That would go over this month's print budget: "
                        + "; ".join(exc.problems)
                    ),
                    "problems": exc.problems,
                    "budget": PrintBudgetService.summary(print_request.user),
                },
                status=status.HTTP_409_CONFLICT,
            )
        except PrintRequestError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PrintRequestSerializer(print_request).data)

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def reject(self, request, pk=None):
        print_request = self.get_object()
        payload = PrintRequestRejectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            print_request = PrintRequestService.reject(
                print_request, request.user, payload.validated_data.get("notes", ""),
            )
        except PrintRequestError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PrintRequestSerializer(print_request).data)

    @action(detail=True, methods=["post"],
            permission_classes=[permissions.IsAuthenticated])
    def cancel(self, request, pk=None):
        """Owner withdraws, or a parent cancels on their behalf."""
        print_request = self.get_object()
        if request.user.role != "parent" and print_request.user_id != request.user.id:
            raise PermissionDenied("You can only cancel your own print requests.")
        try:
            print_request = PrintRequestService.cancel(print_request, request.user)
        except PrintRequestError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PrintRequestSerializer(print_request).data)

    @action(detail=False, methods=["post"],
            permission_classes=[permissions.IsAuthenticated])
    def preview(self, request):
        """Scrape a link's title + thumbnail so the submit form can show a card.

        Soft-fails by design: a 200 with an ``error`` string and a
        URL-derived title is far more useful here than a 502, because the
        child can still submit.
        """
        payload = LinkPreviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        meta = fetch_link_metadata(payload.validated_data["url"])
        return Response({
            "title": meta.title,
            "thumbnail_url": meta.thumbnail_url,
            "author": meta.author,
            "source_kind": meta.source_kind,
            "error": meta.error or None,
        })


class PrintJobViewSet(viewsets.ReadOnlyModelViewSet):
    """`/api/print-jobs/` — what the printer actually did.

    Not ``RoleFilteredQuerySetMixin``: an unmatched job has ``user=None``, and
    the mixin's parent filter (``user__family=…``) would hide exactly the rows
    a parent needs to see in order to link them. Parents scope by the
    printer's family instead; children still see only their own.
    """

    serializer_class = PrintJobSerializer
    queryset = (
        PrintJob.objects
        .select_related("printer", "request", "user")
        .prefetch_related(
            Prefetch("events", queryset=PrintJobEvent.objects.order_by("created_at", "id")),
        )
    )

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role == "parent":
            if user.family_id is None:
                return qs.none()
            qs = qs.filter(printer__family_id=user.family_id)
        else:
            qs = qs.filter(user=user)

        if self.request.query_params.get("unlinked") == "true":
            qs = qs.filter(request__isnull=True)
        if self.request.query_params.get("open") == "true":
            qs = qs.filter(finished_at__isnull=True)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def link(self, request, pk=None):
        """The Handy escape hatch: bind an unmatched print to a request by hand.

        This is the only non-deterministic path in the system, and it exists
        only because someone will occasionally start a plate from their phone
        without renaming it first.
        """
        job = self.get_object()
        payload = PrintJobLinkSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        print_request = PrintRequest.objects.filter(
            pk=payload.validated_data["request_id"],
            user__family=request.user.family,
        ).first()
        if print_request is None:
            return Response(
                {"error": "Print request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            job = PrintRequestService.link_job(job, print_request, request.user)
        except PrintRequestError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PrintJobSerializer(job).data)

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def unlink(self, request, pk=None):
        job = self.get_object()
        try:
            job = PrintRequestService.unlink_job(job, request.user)
        except PrintRequestError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PrintJobSerializer(job).data)


class PrintBudgetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """`/api/print-budgets/` — the part that makes approval mean something.

    Explicit mixins rather than ``ModelViewSet``: budgets are 1:1 with users
    and materialised lazily, so there is no meaningful "create a budget"
    request and no route for one. POST is enabled only for the ``adjust``
    action.
    """

    serializer_class = PrintBudgetSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]
    queryset = PrintBudget.objects.select_related("user")

    def get_permissions(self):
        if action_declares_permissions(self):
            return super().get_permissions()
        if self.action == "partial_update":
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role == "parent":
            if user.family_id is None:
                return qs.none()
            return qs.filter(user__family_id=user.family_id)
        return qs.filter(user=user)

    def list(self, request, *args, **kwargs):
        """Materialise a budget row per child so the UI never sees a gap.

        ``PrintBudget`` rows are created lazily on first use, which would
        otherwise mean a family with no prints yet renders an empty budget
        panel rather than "no cap set".
        """
        if request.user.role == "parent" and request.user.family_id:
            from apps.families.queries import children_in

            for child in children_in(request.user.family):
                PrintBudgetService.get_budget(child)
        else:
            PrintBudgetService.get_budget(request.user)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def adjust(self, request, pk=None):
        """Manual correction — the compensating entry for a bad debit.

        Positive grams/minutes consume more budget; negative give it back.
        Nothing is ever edited or deleted in the ledger, so the history stays
        readable.
        """
        budget = self.get_object()
        payload = PrintBudgetAdjustSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        grams = payload.validated_data.get("grams") or 0
        minutes = payload.validated_data.get("minutes") or 0
        if not grams and not minutes:
            return Response(
                {"error": "Give a grams or minutes amount to adjust."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        PrintBudgetService.record(
            budget.user,
            grams=grams,
            minutes=minutes,
            reason=(
                PrintBudgetLedger.Reason.REFUND if (grams < 0 or minutes < 0)
                else PrintBudgetLedger.Reason.ADJUSTMENT
            ),
            note=payload.validated_data.get("note", ""),
            recorded_by=request.user,
        )
        budget.refresh_from_db()
        return Response(PrintBudgetSerializer(budget).data)

    @action(detail=True, methods=["get"],
            permission_classes=[permissions.IsAuthenticated])
    def ledger(self, request, pk=None):
        """This month's budget entries, newest first."""
        budget = self.get_object()
        entries = (
            PrintBudgetLedger.objects
            .filter(user=budget.user)
            .select_related("request")[:100]
        )
        return Response(PrintBudgetLedgerSerializer(entries, many=True).data)


class PrinterProfileViewSet(ParentWritePermissionMixin, viewsets.ModelViewSet):
    """`/api/printers/` — parent-only printer config, family-scoped."""

    serializer_class = PrinterProfileSerializer
    queryset = PrinterProfile.objects.all()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "family_id", None) is None:
            return PrinterProfile.objects.none()
        return super().get_queryset().filter(family_id=user.family_id)

    def create(self, request, *args, **kwargs):
        write = PrinterProfileWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = dict(write.validated_data)
        secrets = {
            key: data.pop(key, None)
            for key in ("access_code", "cloud_user_id", "cloud_token")
        }
        printer = PrinterProfile(
            family=request.user.family, created_by=request.user, **data,
        )
        printer.set_secrets(**secrets)
        printer.save()
        return Response(
            PrinterProfileSerializer(printer).data, status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        printer = self.get_object()
        write = PrinterProfileWriteSerializer(data=request.data, partial=True)
        write.is_valid(raise_exception=True)
        data = dict(write.validated_data)
        secrets = {
            key: data.pop(key, None)
            for key in ("access_code", "cloud_user_id", "cloud_token")
        }
        for field, value in data.items():
            setattr(printer, field, value)
        # Omitted credentials keep their stored value — see set_secrets().
        printer.set_secrets(**secrets)
        printer.save()
        return Response(PrinterProfileSerializer(printer).data)

    # ``url_path`` keeps the public route at /api/printers/<id>/status/ while
    # the method name avoids shadowing DRF's ``status`` module inside this class.
    @action(detail=True, methods=["get"], url_path="status",
            permission_classes=[permissions.IsAuthenticated])
    def live_status(self, request, pk=None):
        """Live snapshot, served from the listener's fan-out cache.

        This endpoint exists so the SPA can render a live view **without**
        opening a second MQTT connection to the printer. The X1's broker
        tolerates about four clients total; a per-browser-tab connection would
        exhaust that instantly and start kicking Home Assistant off.
        """
        from .fanout import read_state

        printer = self.get_object()
        snapshot = read_state(printer.serial)
        open_job = (
            PrintJob.objects
            .select_related("request", "user")
            .filter(printer=printer, finished_at__isnull=True)
            .first()
        )

        # A child may only see the details of her OWN print. The printer is
        # shared, so a sibling's job would otherwise leak its request title
        # and owner to anyone in the family who hits this endpoint — the UI
        # hides it, but the UI is not the access control. She still gets
        # "busy", because "can I print now?" is a fair question to ask.
        owns_it = (
            request.user.role == "parent"
            or (open_job is not None and open_job.user_id == request.user.id)
        )

        job_payload = None
        if open_job is not None:
            job_payload = (
                PrintJobSerializer(open_job).data if owns_it
                else {"busy_with_someone_elses_print": True}
            )

        # The snapshot leaks identity too, which is easy to miss: subtask_name
        # IS the plate filename, and the plate filename embeds the slug — so
        # it spells out the sibling's request title. Redact the two fields
        # that carry a name; the telemetry (state, progress, temps) is fine
        # for anyone in the household to see.
        if snapshot is not None and not owns_it:
            snapshot = {
                key: value for key, value in snapshot.items()
                if key not in ("subtask_name", "gcode_file")
            }

        return Response({
            "printer": PrinterProfileSerializer(printer).data,
            "live": snapshot,
            "connected": snapshot is not None,
            "job": job_payload,
        })
