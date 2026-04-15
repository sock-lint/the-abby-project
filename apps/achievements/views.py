from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from config.viewsets import ParentWritePermissionMixin, WriteReadSerializerMixin

from .models import Badge, Skill, SkillCategory, SkillProgress, Subject, UserBadge
from .serializers import (
    BadgeSerializer, BadgeWriteSerializer, SkillCategorySerializer,
    SkillProgressSerializer, SkillSerializer, SkillWriteSerializer,
    SubjectSerializer, SubjectWriteSerializer, UserBadgeSerializer,
)
from .services import SkillService


class SkillCategoryViewSet(ParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = SkillCategory.objects.all()
    serializer_class = SkillCategorySerializer


class BadgeViewSet(WriteReadSerializerMixin, ParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = Badge.objects.all()
    serializer_class = BadgeSerializer
    write_serializer_class = BadgeWriteSerializer


class UserBadgeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserBadgeSerializer

    def get_queryset(self):
        return UserBadge.objects.filter(
            user=self.request.user
        ).select_related("badge")


class SubjectViewSet(WriteReadSerializerMixin, ParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = Subject.objects.select_related("category").all()
    serializer_class = SubjectSerializer
    write_serializer_class = SubjectWriteSerializer


class SkillViewSet(WriteReadSerializerMixin, ParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = Skill.objects.select_related("category").all()
    serializer_class = SkillSerializer
    write_serializer_class = SkillWriteSerializer


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

        return Response({
            "category": {
                "id": category.id,
                "name": category.name,
                "icon": category.icon,
                "color": category.color,
            },
            "summary": summary,
            "subjects": subjects,
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
