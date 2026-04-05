from django.contrib.auth import authenticate, login, logout
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MaterialItem, Project, ProjectMilestone, SkillCategory, User
from .serializers import (
    MaterialItemSerializer, ProjectDetailSerializer, ProjectListSerializer,
    ProjectMilestoneSerializer, SkillCategorySerializer, UserSerializer,
)


class IsParent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "parent"


class AuthView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        action = request.data.get("action")
        if action == "login":
            username = request.data.get("username")
            password = request.data.get("password")
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                return Response(UserSerializer(user).data)
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
        elif action == "logout":
            logout(request)
            return Response({"ok": True})
        return Response(
            {"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST
        )


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class DashboardView(APIView):
    def get(self, request):
        user = request.user
        from apps.timecards.services import ClockService
        from apps.payments.services import PaymentService
        from apps.timecards.models import TimeEntry, Timecard
        from apps.achievements.models import UserBadge
        from django.utils import timezone
        from django.db.models import Sum
        from django.db.models.functions import TruncDate
        from datetime import timedelta

        active_entry = ClockService.get_active_entry(user)
        active_timer = None
        if active_entry:
            elapsed = (timezone.now() - active_entry.clock_in).total_seconds() / 60
            active_timer = {
                "project_id": active_entry.project_id,
                "project_title": active_entry.project.title,
                "clock_in": active_entry.clock_in.isoformat(),
                "elapsed_minutes": round(elapsed),
            }

        balance = float(PaymentService.get_balance(user))

        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        week_entries = TimeEntry.objects.filter(
            user=user, status="completed",
            clock_in__date__gte=week_start,
        )
        week_minutes = week_entries.aggregate(
            total=Sum("duration_minutes")
        )["total"] or 0
        week_hours = round(week_minutes / 60, 1)
        week_projects = week_entries.values("project").distinct().count()

        active_projects = ProjectListSerializer(
            Project.objects.filter(
                assigned_to=user, status__in=["active", "in_progress"]
            )[:5],
            many=True,
        ).data

        pending_timecards = Timecard.objects.filter(user=user, status="pending").count()
        if user.role == "parent":
            pending_timecards = Timecard.objects.filter(status="pending").count()

        recent_badges = list(
            UserBadge.objects.filter(user=user).select_related("badge")
            .order_by("-earned_at")[:5]
            .values("badge__name", "badge__icon", "earned_at")
        )

        # Streak calculation
        days = list(
            TimeEntry.objects.filter(user=user, status="completed")
            .annotate(day=TruncDate("clock_in"))
            .values_list("day", flat=True)
            .distinct()
            .order_by("-day")
        )
        streak = 0
        if days:
            streak = 1
            for i in range(1, len(days)):
                if (days[i - 1] - days[i]).days == 1:
                    streak += 1
                else:
                    break

        return Response({
            "role": user.role,
            "active_timer": active_timer,
            "current_balance": balance,
            "this_week": {
                "hours_worked": week_hours,
                "earnings": float(week_hours * float(user.hourly_rate)),
                "projects_worked_on": week_projects,
            },
            "active_projects": active_projects,
            "pending_timecards": pending_timecards,
            "recent_badges": recent_badges,
            "streak_days": streak,
        })


class SkillCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SkillCategory.objects.all()
    serializer_class = SkillCategorySerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return Project.objects.all()
        return Project.objects.filter(assigned_to=user)

    def get_serializer_class(self):
        if self.action == "list":
            return ProjectListSerializer
        return ProjectDetailSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        project = self.get_object()
        if project.assigned_to != request.user:
            return Response(
                {"error": "Not your project"}, status=status.HTTP_403_FORBIDDEN
            )
        project.status = "in_review"
        project.save()
        return Response(ProjectDetailSerializer(project).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if request.user.role != "parent":
            return Response(
                {"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN
            )
        project = self.get_object()
        project.status = "completed"
        project.save()
        return Response(ProjectDetailSerializer(project).data)

    @action(detail=True, methods=["post"], url_path="request-changes")
    def request_changes(self, request, pk=None):
        if request.user.role != "parent":
            return Response(
                {"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN
            )
        project = self.get_object()
        project.status = "in_progress"
        project.parent_notes = request.data.get("notes", "")
        project.save()
        return Response(ProjectDetailSerializer(project).data)


class ProjectMilestoneViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectMilestoneSerializer

    def get_queryset(self):
        return ProjectMilestone.objects.filter(
            project_id=self.kwargs.get("project_pk")
        )

    def perform_create(self, serializer):
        serializer.save(project_id=self.kwargs["project_pk"])

    @action(detail=True, methods=["post"])
    def complete(self, request, project_pk=None, pk=None):
        milestone = self.get_object()
        milestone.is_completed = True
        milestone.save()
        return Response(ProjectMilestoneSerializer(milestone).data)


class MaterialItemViewSet(viewsets.ModelViewSet):
    serializer_class = MaterialItemSerializer

    def get_queryset(self):
        return MaterialItem.objects.filter(
            project_id=self.kwargs.get("project_pk")
        )

    def perform_create(self, serializer):
        serializer.save(project_id=self.kwargs["project_pk"])

    @action(detail=True, methods=["post"], url_path="mark-purchased")
    def mark_purchased(self, request, project_pk=None, pk=None):
        from django.utils import timezone
        item = self.get_object()
        item.is_purchased = True
        item.purchased_at = timezone.now()
        item.actual_cost = request.data.get("actual_cost", item.estimated_cost)
        item.save()
        return Response(MaterialItemSerializer(item).data)
