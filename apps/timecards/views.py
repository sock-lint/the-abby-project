from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project

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


class TimeEntryViewSet(viewsets.ModelViewSet):
    serializer_class = TimeEntrySerializer

    def get_queryset(self):
        user = self.request.user
        qs = TimeEntry.objects.select_related("project")
        if user.role == "child":
            qs = qs.filter(user=user)
        return qs

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        if request.user.role != "parent":
            return Response(
                {"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN
            )
        entry = self.get_object()
        entry.status = "voided"
        entry.save()
        return Response(TimeEntrySerializer(entry).data)


class TimecardViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TimecardSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return Timecard.objects.all()
        return Timecard.objects.filter(user=user)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TimecardDetailSerializer
        return TimecardSerializer

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if request.user.role != "parent":
            return Response(
                {"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN
            )
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

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        if request.user.role != "parent":
            return Response(
                {"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN
            )
        timecard = self.get_object()
        amount = request.data.get("amount", timecard.total_earnings)
        TimecardService.mark_paid(timecard, request.user, amount)
        return Response(TimecardSerializer(timecard).data)


class ExportTimecardsView(APIView):
    def get(self, request):
        from django.http import HttpResponse
        from .export import export_timecards_csv
        csv_content = export_timecards_csv(request.user, request.user.role == "parent")
        response = HttpResponse(csv_content, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="timecards.csv"'
        return response


class ExportTimeEntriesView(APIView):
    def get(self, request):
        from django.http import HttpResponse
        from .export import export_time_entries_csv
        csv_content = export_time_entries_csv(request.user, request.user.role == "parent")
        response = HttpResponse(csv_content, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="time_entries.csv"'
        return response
