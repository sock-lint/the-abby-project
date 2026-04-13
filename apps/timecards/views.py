from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin

from .models import Timecard, TimeEntry
from .serializers import (
    TimecardDetailSerializer, TimecardSerializer, TimeEntrySerializer,
)
from .services import ClockService, TimecardService


class ClockView(APIView):
    def get(self, request):
        """Get current active clock-in status."""
        entry = ClockService.get_active_entry(request.user)
        if entry:
            return Response(TimeEntrySerializer(entry).data)
        return Response(None)

    def post(self, request):
        action = request.data.get("action")
        if action == "in":
            project_id = request.data.get("project_id")
            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                return Response(
                    {"error": "Project not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            try:
                entry = ClockService.clock_in(request.user, project)
                return Response(
                    TimeEntrySerializer(entry).data,
                    status=status.HTTP_201_CREATED,
                )
            except ValueError as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
                )
        elif action == "out":
            notes = request.data.get("notes", "")
            try:
                entry = ClockService.clock_out(request.user, notes=notes)
                return Response(TimeEntrySerializer(entry).data)
            except ValueError as e:
                return Response(
                    {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
                )
        return Response(
            {"error": "Invalid action. Use 'in' or 'out'."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class TimeEntryViewSet(RoleFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = TimeEntrySerializer
    queryset = TimeEntry.objects.select_related("project")

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def void(self, request, pk=None):
        entry = self.get_object()
        entry.status = "voided"
        entry.save()
        return Response(TimeEntrySerializer(entry).data)


class TimecardViewSet(RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TimecardSerializer
    queryset = Timecard.objects.all()

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TimecardDetailSerializer
        return TimecardSerializer

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def approve(self, request, pk=None):
        timecard = self.get_object()
        notes = request.data.get("notes", "")
        TimecardService.approve_timecard(timecard, request.user, notes)
        return Response(TimecardSerializer(timecard).data)

    @action(detail=True, methods=["post"])
    def dispute(self, request, pk=None):
        timecard = self.get_object()
        timecard.status = "disputed"
        timecard.save()
        return Response(TimecardSerializer(timecard).data)

    @action(detail=True, methods=["post"], url_path="mark-paid", permission_classes=[IsParent])
    def mark_paid(self, request, pk=None):
        timecard = self.get_object()
        amount = request.data.get("amount", timecard.total_earnings)
        TimecardService.mark_paid(timecard, request.user, amount)
        return Response(TimecardSerializer(timecard).data)


def _csv_response(content, filename):
    from django.http import HttpResponse
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class ExportTimecardsView(APIView):
    def get(self, request):
        from .export import export_timecards_csv
        csv_content = export_timecards_csv(request.user, request.user.role == "parent")
        return _csv_response(csv_content, "timecards.csv")


class ExportTimeEntriesView(APIView):
    def get(self, request):
        from .export import export_time_entries_csv
        csv_content = export_time_entries_csv(request.user, request.user.role == "parent")
        return _csv_response(csv_content, "time_entries.csv")
