import logging

from django.contrib.auth import authenticate
from rest_framework import permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import (
    NestedProjectResourceMixin, ParentWritePermissionMixin,
    RoleFilteredQuerySetMixin,
    get_child_or_404, child_not_found_response,
)

logger = logging.getLogger(__name__)

from .models import (
    MaterialItem, Project, ProjectCollaborator,
    ProjectMilestone, ProjectResource, ProjectStep, ProjectTemplate, SavingsGoal,
    TemplateMaterial, TemplateMilestone, TemplateResource,
    TemplateStep, User,
)
from .serializers import (
    ChildSerializer, MaterialItemSerializer,
    ProjectCollaboratorSerializer, ProjectDetailSerializer,
    ProjectListSerializer,
    ProjectMilestoneSerializer, ProjectResourceSerializer, ProjectStepSerializer,
    ProjectTemplateSerializer, SavingsGoalSerializer,
    UserSerializer,
)


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
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        user = request.user
        if "theme" in request.data:
            user.theme = request.data["theme"]
            user.save(update_fields=["theme"])
        if "avatar" in request.FILES:
            if user.avatar:
                user.avatar.delete(save=False)
            user.avatar = request.FILES["avatar"]
            user.save(update_fields=["avatar"])
        elif request.data.get("avatar") == "" and user.avatar:
            user.avatar.delete(save=False)
            user.avatar = None
            user.save(update_fields=["avatar"])
        return Response(UserSerializer(user).data)


class ChildViewSet(viewsets.ModelViewSet):
    serializer_class = ChildSerializer
    permission_classes = [IsParent]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return User.objects.filter(role="child")


class DashboardView(APIView):
    def get(self, request):
        user = request.user
        from apps.timecards.services import ClockService, TimeEntryService
        from apps.payments.services import PaymentService
        from apps.timecards.models import TimeEntry, Timecard
        from apps.achievements.models import UserBadge
        from django.utils import timezone
        from django.db.models import Sum
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

        streak = TimeEntryService.current_streak(user)

        # Savings goals
        goals = SavingsGoalSerializer(
            SavingsGoal.objects.filter(user=user, is_completed=False)[:3],
            many=True,
        ).data

        from apps.rewards.services import CoinService
        coin_balance = CoinService.get_balance(user)

        # Chores summary
        from apps.chores.services import ChoreService
        from apps.chores.models import ChoreCompletion
        chores_today = []
        pending_chore_approvals = 0
        if user.role == "child":
            available = ChoreService.get_available_chores(user)
            for c in available:
                chores_today.append({
                    "id": c.pk,
                    "title": c.title,
                    "icon": c.icon,
                    "reward_amount": str(c.reward_amount),
                    "coin_reward": c.coin_reward,
                    "is_done": c.is_done_today,
                    "status": c.today_completion_status,
                })
        elif user.role == "parent":
            pending_chore_approvals = ChoreCompletion.objects.filter(
                status=ChoreCompletion.Status.PENDING,
            ).count()

        # RPG profile
        from apps.habits.models import Habit, HabitLog
        from apps.rpg.models import CharacterProfile
        rpg_profile, _ = CharacterProfile.objects.get_or_create(user=user)
        habits = Habit.objects.filter(user=user, is_active=True)
        habits_data = []
        for h in habits:
            taps_today = HabitLog.objects.filter(
                habit=h, user=user, direction=1, created_at__date=today,
            ).count()
            habits_data.append({
                "id": h.pk,
                "name": h.name,
                "icon": h.icon,
                "habit_type": h.habit_type,
                "strength": h.strength,
                "taps_today": taps_today,
                "max_taps_per_day": h.max_taps_per_day,
            })

        rpg_data = {
            "level": rpg_profile.level,
            "login_streak": rpg_profile.login_streak,
            "longest_login_streak": rpg_profile.longest_login_streak,
            "perfect_days_count": rpg_profile.perfect_days_count,
            "last_active_date": rpg_profile.last_active_date,
            "habits_today": habits_data,
        }

        from apps.projects import priority as priority_module
        next_actions = [
            a.as_dict() for a in priority_module.build_next_actions(user)
        ]

        return Response({
            "role": user.role,
            "active_timer": active_timer,
            "current_balance": balance,
            "coin_balance": coin_balance,
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
            "chores_today": chores_today,
            "next_actions": next_actions,
            "pending_chore_approvals": pending_chore_approvals,
            "rpg": rpg_data,
        })


class ProjectViewSet(RoleFilteredQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = ProjectDetailSerializer
    queryset = Project.objects.all()
    role_filter_field = "assigned_to"

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

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

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def activate(self, request, pk=None):
        from django.utils import timezone
        project = self.get_object()
        if project.status not in ("draft", "in_review"):
            return Response(
                {"error": f"cannot activate from status {project.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        project.status = "in_progress"
        if project.started_at is None:
            project.started_at = timezone.now()
        project.save()
        return Response(ProjectDetailSerializer(project).data)

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

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def approve(self, request, pk=None):
        from django.utils import timezone
        project = self.get_object()
        project.status = "completed"
        if project.completed_at is None:
            project.completed_at = timezone.now()
        project.save()
        return Response(ProjectDetailSerializer(project).data)

    @action(detail=True, methods=["post"], url_path="request-changes", permission_classes=[IsParent])
    def request_changes(self, request, pk=None):
        from django.utils import timezone
        project = self.get_object()
        project.status = "in_progress"
        if project.started_at is None:
            project.started_at = timezone.now()
        project.parent_notes = request.data.get("notes", "")
        project.save()
        return Response(ProjectDetailSerializer(project).data)


class ProjectMilestoneViewSet(NestedProjectResourceMixin, viewsets.ModelViewSet):
    serializer_class = ProjectMilestoneSerializer
    queryset = ProjectMilestone.objects.all()

    @action(detail=True, methods=["post"])
    def complete(self, request, project_pk=None, pk=None):
        milestone = self.get_object()
        milestone.is_completed = True
        milestone.save()
        return Response(ProjectMilestoneSerializer(milestone).data)


class MaterialItemViewSet(NestedProjectResourceMixin, viewsets.ModelViewSet):
    serializer_class = MaterialItemSerializer
    queryset = MaterialItem.objects.all()

    @action(detail=True, methods=["post"], url_path="mark-purchased")
    def mark_purchased(self, request, project_pk=None, pk=None):
        from django.utils import timezone
        item = self.get_object()
        item.is_purchased = True
        item.purchased_at = timezone.now()
        item.actual_cost = request.data.get("actual_cost", item.estimated_cost)
        item.save()
        return Response(MaterialItemSerializer(item).data)


def _can_edit_project_step(user, project):
    """Child can toggle steps on projects they're assigned to or collaborating on."""
    if user.role == "parent":
        return True
    if project.assigned_to_id == user.id:
        return True
    return project.collaborators.filter(user=user).exists()


class ProjectStepViewSet(NestedProjectResourceMixin, viewsets.ModelViewSet):
    """Walkthrough steps — purely instructional, no ledger/XP hooks.

    Parents can CRUD steps. Children assigned to (or collaborating on) a
    project can ``complete`` / ``uncomplete`` their own steps.
    """
    serializer_class = ProjectStepSerializer
    queryset = ProjectStep.objects.all()

    def get_permissions(self):
        # Children use complete/uncomplete/reorder; parents can CRUD freely.
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=["post"])
    def complete(self, request, project_pk=None, pk=None):
        from django.utils import timezone
        step = self.get_object()
        if not _can_edit_project_step(request.user, step.project):
            return Response(
                {"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN
            )
        step.is_completed = True
        step.completed_at = timezone.now()
        step.save(update_fields=["is_completed", "completed_at", "updated_at"])
        return Response(ProjectStepSerializer(step).data)

    @action(detail=True, methods=["post"])
    def uncomplete(self, request, project_pk=None, pk=None):
        step = self.get_object()
        if not _can_edit_project_step(request.user, step.project):
            return Response(
                {"error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN
            )
        step.is_completed = False
        step.completed_at = None
        step.save(update_fields=["is_completed", "completed_at", "updated_at"])
        return Response(ProjectStepSerializer(step).data)

    @action(detail=False, methods=["post"])
    def reorder(self, request, project_pk=None):
        """Accepts ``[{id, order}, ...]``; renumbers all project steps atomically."""
        from django.db import transaction
        items = request.data if isinstance(request.data, list) else request.data.get("items", [])
        if not isinstance(items, list):
            return Response(
                {"error": "expected a list"}, status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            steps_by_id = {
                s.id: s
                for s in ProjectStep.objects.select_for_update().filter(project_id=project_pk)
            }
            for idx, entry in enumerate(items):
                step = steps_by_id.get(entry.get("id"))
                if step is None:
                    continue
                step.order = entry.get("order", idx)
                step.save(update_fields=["order", "updated_at"])
        qs = ProjectStep.objects.filter(project_id=project_pk)
        return Response(ProjectStepSerializer(qs, many=True).data)


class ProjectResourceViewSet(NestedProjectResourceMixin, viewsets.ModelViewSet):
    """Reference links (videos, docs, inspiration) attached to a project/step.

    Reference material is parent-authored; children can view but not edit.
    """
    serializer_class = ProjectResourceSerializer
    queryset = ProjectResource.objects.all()
    permission_classes = [IsParent]

    def get_queryset(self):
        qs = super().get_queryset()
        step_id = self.request.query_params.get("step")
        if step_id == "null":
            qs = qs.filter(step__isnull=True)
        elif step_id:
            qs = qs.filter(step_id=step_id)
        return qs


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


class ProjectTemplateViewSet(ParentWritePermissionMixin, viewsets.ModelViewSet):
    serializer_class = ProjectTemplateSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return ProjectTemplate.objects.all()
        return ProjectTemplate.objects.filter(is_public=True)

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
            status="in_progress",
        )

        # Map template-milestone pk -> real ProjectMilestone so steps can
        # rebind their FK to the new project's milestones (not the template's).
        ms_id_map = {}
        for ms in template.milestones.all():
            pm = ProjectMilestone.objects.create(
                project=project, title=ms.title,
                description=ms.description, order=ms.order,
                bonus_amount=ms.bonus_amount,
            )
            ms_id_map[ms.id] = pm

        for mat in template.materials.all():
            MaterialItem.objects.create(
                project=project, name=mat.name,
                description=mat.description,
                estimated_cost=mat.estimated_cost,
            )

        # Clone steps first so we can map template-step ids to real step pks
        # when copying step-scoped resources. Preserve the step→milestone
        # linkage by resolving through ms_id_map.
        step_id_map = {}
        for ts in template.steps.all():
            ps = ProjectStep.objects.create(
                project=project, title=ts.title,
                description=ts.description, order=ts.order,
                milestone=ms_id_map.get(ts.milestone_id) if ts.milestone_id else None,
            )
            step_id_map[ts.id] = ps

        for tr in template.resources.all():
            ProjectResource.objects.create(
                project=project,
                step=step_id_map.get(tr.step_id) if tr.step_id else None,
                title=tr.title,
                url=tr.url,
                resource_type=tr.resource_type,
                order=tr.order,
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

        # Map project-milestone pk -> TemplateMilestone so cloned steps point
        # at the template's milestones, not the source project's.
        ms_id_map = {}
        for ms in project.milestones.all():
            tm = TemplateMilestone.objects.create(
                template=template, title=ms.title,
                description=ms.description, order=ms.order,
                bonus_amount=ms.bonus_amount,
            )
            ms_id_map[ms.id] = tm

        for mat in project.materials.all():
            TemplateMaterial.objects.create(
                template=template, name=mat.name,
                description=mat.description,
                estimated_cost=mat.estimated_cost,
            )

        step_id_map = {}
        for ps in project.steps.all():
            ts = TemplateStep.objects.create(
                template=template, title=ps.title,
                description=ps.description, order=ps.order,
                milestone=ms_id_map.get(ps.milestone_id) if ps.milestone_id else None,
            )
            step_id_map[ps.id] = ts

        for pr in project.resources.all():
            TemplateResource.objects.create(
                template=template,
                step=step_id_map.get(pr.step_id) if pr.step_id else None,
                title=pr.title,
                url=pr.url,
                resource_type=pr.resource_type,
                order=pr.order,
            )

        return Response(ProjectTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class ProjectCollaboratorViewSet(NestedProjectResourceMixin, viewsets.ModelViewSet):
    serializer_class = ProjectCollaboratorSerializer
    queryset = ProjectCollaborator.objects.all()

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

    def list(self, request, *args, **kwargs):
        # Running completion detection here — rather than only from
        # ``PaymentService.record_entry`` — guarantees any goal whose
        # target was edited down below the current balance auto-completes
        # on the next list fetch without requiring another ledger write.
        from .savings_service import SavingsGoalService
        SavingsGoalService.check_and_complete(request.user)
        return super().list(request, *args, **kwargs)




class GreenlightImportView(APIView):
    """Import Greenlight CSV transaction data for reconciliation."""

    permission_classes = [IsParent]

    def post(self, request):
        import csv
        import io
        from decimal import Decimal, InvalidOperation
        from apps.payments.services import PaymentService

        csv_file = request.data.get("csv_data", "")
        if not csv_file:
            return Response({"error": "csv_data required"}, status=status.HTTP_400_BAD_REQUEST)

        child_id = request.data.get("user_id")
        if not child_id:
            return Response({"error": "user_id required"}, status=status.HTTP_400_BAD_REQUEST)

        child = get_child_or_404(child_id)
        if child is None:
            return child_not_found_response()

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

                PaymentService.record_entry(
                    child,
                    -abs(amount),
                    "payout",
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
