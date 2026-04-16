from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import (
    ApprovalActionMixin,
    RoleFilteredQuerySetMixin,
    WriteReadSerializerMixin,
    get_child_or_404,
    child_not_found_response,
)

from .models import HomeworkAssignment, HomeworkSubmission, HomeworkTemplate
from .serializers import (
    HomeworkAssignmentSerializer,
    HomeworkAssignmentWriteSerializer,
    HomeworkSubmissionSerializer,
    HomeworkTemplateSerializer,
)
from .services import HomeworkError, HomeworkService


class HomeworkAssignmentViewSet(
    RoleFilteredQuerySetMixin, WriteReadSerializerMixin, viewsets.ModelViewSet,
):
    serializer_class = HomeworkAssignmentSerializer
    write_serializer_class = HomeworkAssignmentWriteSerializer
    role_filter_field = "assigned_to"

    def get_permissions(self):
        # Children can create assignments (auto-assigned to self in
        # perform_create); only parents can edit or delete.
        if self.action in ("update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = HomeworkAssignment.objects.filter(
            is_active=True,
        ).select_related(
            "assigned_to", "created_by",
        ).prefetch_related(
            "skill_tags__skill", "submissions",
        )
        return self.get_role_filtered_queryset(qs)

    def perform_create(self, serializer):
        data = serializer.validated_data.copy()
        data["skill_tags"] = self.request.data.get("skill_tags", [])

        # Children auto-assign to self.
        user = self.request.user
        if user.role == "child":
            data["assigned_to"] = user

        return HomeworkService.create_assignment(user, data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            assignment = self.perform_create(serializer)
        except HomeworkError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            HomeworkAssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        assignment = self.get_object()
        images = request.FILES.getlist("images")
        notes = request.data.get("notes", "")
        try:
            submission = HomeworkService.submit_completion(
                request.user, assignment, images, notes,
            )
        except HomeworkError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            HomeworkSubmissionSerializer(submission).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def save_template(self, request, pk=None):
        assignment = self.get_object()
        template = HomeworkService.save_as_template(assignment, request.user)
        return Response(
            HomeworkTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def plan(self, request, pk=None):
        """Trigger AI planning — creates a linked Project via Claude.

        Parent-only: AI calls are non-trivial and cost real money; children
        request planning by asking a parent in the UI.
        """
        assignment = self.get_object()
        try:
            updated = HomeworkService.plan_assignment(assignment, request.user)
        except HomeworkError as exc:
            message = str(exc)
            http_status = (
                status.HTTP_501_NOT_IMPLEMENTED
                if "not configured" in message
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"error": message}, status=http_status)
        return Response(HomeworkAssignmentSerializer(updated).data)


class HomeworkSubmissionViewSet(
    ApprovalActionMixin, RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet,
):
    serializer_class = HomeworkSubmissionSerializer
    queryset = HomeworkSubmission.objects.select_related(
        "assignment", "user",
    ).prefetch_related("proofs")
    approval_service = HomeworkService
    approval_approve_method = "approve_submission"
    approval_reject_method = "reject_submission"

    def get_queryset(self):
        qs = self.get_role_filtered_queryset(super().get_queryset())
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def adjust(self, request, pk=None):
        """Parent overrides effort/reward/coins on a pending submission.

        Re-computes the submission's reward snapshot using the frozen
        timeliness multiplier and clears the assignment's
        ``rewards_pending_review`` flag. Used when AI effort estimation
        was unavailable or when the parent wants to tweak the AI's
        determination before approving.
        """
        submission = self.get_object()
        try:
            updated = HomeworkService.adjust_submission(
                submission,
                request.user,
                effort_level=request.data.get("effort_level"),
                reward_amount=request.data.get("reward_amount"),
                coin_reward=request.data.get("coin_reward"),
            )
        except (HomeworkError, TypeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HomeworkSubmissionSerializer(updated).data)


class HomeworkTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = HomeworkTemplateSerializer
    permission_classes = [IsParent]

    def get_queryset(self):
        return HomeworkTemplate.objects.filter(created_by=self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def create_assignment(self, request, pk=None):
        template = self.get_object()
        assigned_to_id = request.data.get("assigned_to_id")
        due_date = request.data.get("due_date")

        if not assigned_to_id or not due_date:
            return Response(
                {"error": "assigned_to_id and due_date are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        child = get_child_or_404(assigned_to_id)
        if child is None:
            return child_not_found_response()

        try:
            assignment = HomeworkService.create_from_template(
                template, child, due_date,
            )
        except HomeworkError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            HomeworkAssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )


class HomeworkDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == "child":
            dashboard = HomeworkService.get_child_dashboard(user)
            return Response({
                "today": HomeworkAssignmentSerializer(
                    [item["assignment"] for item in dashboard["today"]], many=True,
                ).data,
                "upcoming": HomeworkAssignmentSerializer(
                    [item["assignment"] for item in dashboard["upcoming"]], many=True,
                ).data,
                "overdue": HomeworkAssignmentSerializer(
                    [item["assignment"] for item in dashboard["overdue"]], many=True,
                ).data,
                "stats": dashboard["stats"],
            })
        else:
            overview = HomeworkService.get_parent_overview()
            return Response({
                "pending_submissions": HomeworkSubmissionSerializer(
                    overview["pending_submissions"], many=True,
                ).data,
            })
