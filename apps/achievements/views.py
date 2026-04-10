from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import SkillCategory
from config.permissions import IsParent

from .models import Badge, Skill, SkillProgress, Subject, UserBadge
from .serializers import (
    BadgeSerializer, BadgeWriteSerializer, SkillProgressSerializer,
    SkillSerializer, SkillWriteSerializer, SubjectSerializer,
    SubjectWriteSerializer, UserBadgeSerializer,
)
from .services import SkillService


class BadgeViewSet(viewsets.ModelViewSet):
    queryset = Badge.objects.all()
    serializer_class = BadgeSerializer

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return BadgeWriteSerializer
        return BadgeSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]


class UserBadgeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserBadgeSerializer

    def get_queryset(self):
        return UserBadge.objects.filter(
            user=self.request.user
        ).select_related("badge")


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.select_related("category").all()
    serializer_class = SubjectSerializer

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return SubjectWriteSerializer
        return SubjectSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]


class SkillViewSet(viewsets.ModelViewSet):
    queryset = Skill.objects.select_related("category").all()
    serializer_class = SkillSerializer

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return SkillWriteSerializer
        return SkillSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]


class SkillProgressViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SkillProgressSerializer

    def get_queryset(self):
        return SkillProgress.objects.filter(
            user=self.request.user
        ).select_related("skill", "skill__category")


class SkillTreeView(APIView):
    def get(self, request, category_id):
        try:
            category = SkillCategory.objects.get(id=category_id)
        except SkillCategory.DoesNotExist:
            return Response({"error": "Category not found"}, status=404)

        subjects = SkillService.get_skill_tree(request.user, category)
        summary = SkillService.get_category_summary(request.user, category)

        # Flattened skill list kept for backward compatibility with any
        # existing clients; new shape is under `subjects`.
        flat_skills = [s for subj in subjects for s in subj["skills"]]

        return Response({
            "category": {
                "id": category.id,
                "name": category.name,
                "icon": category.icon,
                "color": category.color,
            },
            "summary": summary,
            "subjects": subjects,
            "skills": flat_skills,
        })


class AchievementsSummaryView(APIView):
    def get(self, request):
        user = request.user
        badges = UserBadge.objects.filter(user=user).select_related("badge")
        progress = SkillProgress.objects.filter(
            user=user
        ).select_related("skill", "skill__category")

        categories = {}
        for sp in progress:
            cat_name = sp.skill.category.name
            if cat_name not in categories:
                categories[cat_name] = {
                    "category_id": sp.skill.category_id,
                    "icon": sp.skill.category.icon,
                    "color": sp.skill.category.color,
                    "skills": [],
                }
            categories[cat_name]["skills"].append(
                SkillProgressSerializer(sp).data
            )

        return Response({
            "badges_earned": UserBadgeSerializer(badges, many=True).data,
            "total_badges": Badge.objects.count(),
            "skill_categories": categories,
        })
