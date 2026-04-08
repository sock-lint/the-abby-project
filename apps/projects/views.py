from django.contrib.auth import authenticate, login, logout
from rest_framework import permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    MaterialItem, Project, ProjectCollaborator, ProjectMilestone, ProjectTemplate,
    SavingsGoal, SkillCategory, TemplateMaterial, TemplateMilestone, User,
)
from .serializers import (
    MaterialItemSerializer, NotificationSerializer, ProjectCollaboratorSerializer,
    ProjectDetailSerializer, ProjectListSerializer, ProjectMilestoneSerializer,
    ProjectTemplateSerializer, SavingsGoalSerializer, SkillCategorySerializer,
    UserSerializer,
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
                token, _ = Token.objects.get_or_create(user=user)
                data = UserSerializer(user).data
                data["token"] = token.key
                return Response(data)
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
        elif action == "logout":
            if request.user.is_authenticated:
                Token.objects.filter(user=request.user).delete()
            return Response({"ok": True})
        return Response(
            {"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST
        )


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        user = request.user
        if "theme" in request.data:
            user.theme = request.data["theme"]
            user.save(update_fields=["theme"])
        return Response(UserSerializer(user).data)


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

        # Savings goals
        goals = SavingsGoalSerializer(
            SavingsGoal.objects.filter(user=user, is_completed=False)[:3],
            many=True,
        ).data

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
            "savings_goals": goals,
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


class InstructablesPreviewView(APIView):
    def get(self, request):
        url = request.query_params.get('url')
        if not url:
            return Response({'error': 'url parameter required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from .scraper import scrape_instructables
            data = scrape_instructables(url)
            return Response(data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return self.request.user.notifications.all()

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = request.user.notifications.filter(is_read=False).count()
        return Response({"count": count})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response(NotificationSerializer(notification).data)


class ProjectSuggestionsView(APIView):
    def get(self, request):
        from .suggestions import get_project_suggestions
        suggestions = get_project_suggestions(request.user)
        return Response(suggestions)


class ProjectQRCodeView(APIView):
    """Generate a QR code for quick clock-in to a project."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk=None):
        import qrcode
        import io
        from django.http import HttpResponse

        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        # QR data is a JSON payload with project ID and action
        import json
        qr_data = json.dumps({
            "app": "summerforge",
            "action": "clock_in",
            "project_id": project.id,
            "project_title": project.title,
        })

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#d97706", back_color="#0a0a0a")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response["Content-Disposition"] = f'inline; filename="project-{pk}-qr.png"'
        return response


class ProjectTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectTemplateSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return ProjectTemplate.objects.all()
        return ProjectTemplate.objects.filter(is_public=True)

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"])
    def shared(self, request):
        """Browse public templates from all families (parent co-op)."""
        templates = ProjectTemplate.objects.filter(is_public=True)
        serializer = ProjectTemplateSerializer(templates, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="create-project")
    def create_project_from_template(self, request, pk=None):
        """Create a new project from this template."""
        template = self.get_object()
        assigned_to_id = request.data.get("assigned_to_id")

        project = Project.objects.create(
            title=template.title,
            description=template.description,
            instructables_url=template.instructables_url,
            difficulty=template.difficulty,
            category=template.category,
            bonus_amount=template.bonus_amount,
            materials_budget=template.materials_budget,
            created_by=request.user,
            assigned_to_id=assigned_to_id,
            status="active",
        )

        for ms in template.milestones.all():
            ProjectMilestone.objects.create(
                project=project, title=ms.title,
                description=ms.description, order=ms.order,
                bonus_amount=ms.bonus_amount,
            )

        for mat in template.materials.all():
            MaterialItem.objects.create(
                project=project, name=mat.name,
                description=mat.description,
                estimated_cost=mat.estimated_cost,
            )

        return Response(ProjectDetailSerializer(project).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="from-project")
    def create_from_project(self, request):
        """Save a completed project as a template."""
        project_id = request.data.get("project_id")
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        template = ProjectTemplate.objects.create(
            title=project.title,
            description=project.description,
            instructables_url=project.instructables_url,
            difficulty=project.difficulty,
            category=project.category,
            bonus_amount=project.bonus_amount,
            materials_budget=project.materials_budget,
            source_project=project,
            created_by=request.user,
            is_public=request.data.get("is_public", False),
        )

        for ms in project.milestones.all():
            TemplateMilestone.objects.create(
                template=template, title=ms.title,
                description=ms.description, order=ms.order,
                bonus_amount=ms.bonus_amount,
            )

        for mat in project.materials.all():
            TemplateMaterial.objects.create(
                template=template, name=mat.name,
                description=mat.description,
                estimated_cost=mat.estimated_cost,
            )

        return Response(ProjectTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class ProjectCollaboratorViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectCollaboratorSerializer

    def get_queryset(self):
        return ProjectCollaborator.objects.filter(
            project_id=self.kwargs.get("project_pk")
        )

    def perform_create(self, serializer):
        serializer.save(project_id=self.kwargs["project_pk"])

    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]


class SavingsGoalViewSet(viewsets.ModelViewSet):
    serializer_class = SavingsGoalSerializer

    def get_queryset(self):
        return SavingsGoal.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def update_amount(self, request, pk=None):
        """Update the current saved amount (recalculated from balance)."""
        from apps.payments.services import PaymentService
        goal = self.get_object()
        balance = PaymentService.get_balance(request.user)
        goal.current_amount = max(balance, 0)
        if goal.current_amount >= goal.target_amount and not goal.is_completed:
            goal.is_completed = True
            from django.utils import timezone
            goal.completed_at = timezone.now()
        goal.save()
        return Response(SavingsGoalSerializer(goal).data)


class GreenlightImportView(APIView):
    """Import Greenlight CSV transaction data for reconciliation."""

    def post(self, request):
        if request.user.role != "parent":
            return Response({"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN)

        import csv
        import io
        from decimal import Decimal, InvalidOperation
        from apps.payments.models import PaymentLedger

        csv_file = request.data.get("csv_data", "")
        if not csv_file:
            return Response({"error": "csv_data required"}, status=status.HTTP_400_BAD_REQUEST)

        child_id = request.data.get("user_id")
        if not child_id:
            return Response({"error": "user_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            child = User.objects.get(id=child_id, role="child")
        except User.DoesNotExist:
            return Response({"error": "Child not found"}, status=status.HTTP_404_NOT_FOUND)

        reader = csv.DictReader(io.StringIO(csv_file))
        imported = 0
        errors = []

        for i, row in enumerate(reader):
            try:
                amount_str = row.get("Amount", row.get("amount", "")).replace("$", "").replace(",", "").strip()
                if not amount_str:
                    continue
                amount = Decimal(amount_str)
                description = row.get("Description", row.get("description", row.get("Memo", "")))

                PaymentLedger.objects.create(
                    user=child,
                    amount=-abs(amount),
                    entry_type="payout",
                    description=f"Greenlight import: {description}".strip(),
                    created_by=request.user,
                )
                imported += 1
            except (InvalidOperation, KeyError, ValueError) as e:
                errors.append(f"Row {i + 1}: {str(e)}")

        return Response({
            "imported": imported,
            "errors": errors,
        })
