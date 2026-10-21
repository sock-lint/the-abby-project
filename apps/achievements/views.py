from copy import copy

from rest_framework import viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.viewsets import StaffParentWritePermissionMixin, WriteReadSerializerMixin
from apps.rpg.catalog_icons import category_catalog_icon

from .models import Badge, Skill, SkillCategory, SkillProgress, Subject, UserBadge
from .serializers import (
    BadgeSerializer, BadgeWriteSerializer, SkillCategorySerializer,
    SkillProgressSerializer, SkillSerializer, SkillWriteSerializer,
    SubjectSerializer, SubjectWriteSerializer, UserBadgeSerializer,
)
from .services import SkillService
from .taxonomy import available_categories, available_for_new_choices, available_skills, available_subjects
from apps.rpg.content.taxonomy_deletion import delete_taxonomy
from apps.rpg.content.authoring import (
    direct_catalog_write, natural_lookup, record_direct_override, require_catalog_ownership, validate_catalog_object,
)
from apps.rpg.content.loader import ContentPackError


class SafeTaxonomyDeleteMixin:
    def perform_destroy(self, instance):
        delete_taxonomy(self.request.user, type(instance), instance.pk)


class TaxonomyChoiceMixin:
    """Default lists are pickers; explicit history/management reads keep IDs."""
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list" or self.request.query_params.get("include_retired", "").lower() == "true":
            return queryset
        return {SkillCategory: available_categories, Subject: available_subjects, Skill: available_skills}[
            queryset.model](queryset)


class DirectTaxonomyWriteMixin:
    def _save_taxonomy(self, serializer):
        try:
            with direct_catalog_write(self.request.user) as actor:
                current = serializer.instance
                if current is not None:
                    current = type(current).objects.select_for_update(of=("self",)).filter(pk=current.pk).first()
                    if current is None:
                        raise NotFound("Taxonomy entry not found.")
                    try:
                        require_catalog_ownership(actor, current)
                    except ContentPackError:
                        raise PermissionDenied("This taxonomy entry is read-only here.") from None
                    serializer.instance = current
                candidate = copy(current) if current is not None else serializer.Meta.model()
                before = natural_lookup(current) if current is not None else None
                for field, value in serializer.validated_data.items():
                    setattr(candidate, field, value)
                try:
                    validate_catalog_object(candidate)
                except ContentPackError as error:
                    raise ValidationError(str(error)) from error
                saved = serializer.save()
                record_direct_override(actor, saved, before or natural_lookup(saved))
                # DRF parsed relations before the fence. Serialize fresh parents
                # so the effective availability reflects the admitted catalog.
                saved._state.fields_cache.clear()
        except ContentPackError:
            raise PermissionDenied("This taxonomy entry is read-only here.") from None

    def perform_create(self, serializer):
        self._save_taxonomy(serializer)

    def perform_update(self, serializer):
        self._save_taxonomy(serializer)


# All four ViewSets author GLOBAL content shared across every family in a
# deployment. Gate writes on IsStaffParent so a signup-created parent in one
# family can't rename/delete a Skill or Badge that other families' children
# are progressing toward. Reads stay open to any authenticated user.
class SkillCategoryViewSet(TaxonomyChoiceMixin, DirectTaxonomyWriteMixin, SafeTaxonomyDeleteMixin, StaffParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = SkillCategory.objects.all()
    serializer_class = SkillCategorySerializer


class BadgeViewSet(DirectTaxonomyWriteMixin, SafeTaxonomyDeleteMixin, WriteReadSerializerMixin, StaffParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = Badge.objects.all()
    serializer_class = BadgeSerializer
    write_serializer_class = BadgeWriteSerializer

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "is_staff", False) and getattr(user, "role", None) == "parent":
            return super().get_queryset()
        from .availability import availability_for_request, visible_badges
        return visible_badges(super().get_queryset(), user, availability=availability_for_request(self.request))


class UserBadgeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserBadgeSerializer

    def get_queryset(self):
        return UserBadge.objects.filter(
            user=self.request.user
        ).select_related("badge")


class SubjectViewSet(TaxonomyChoiceMixin, DirectTaxonomyWriteMixin, SafeTaxonomyDeleteMixin, WriteReadSerializerMixin, StaffParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = Subject.objects.select_related("category").all()
    serializer_class = SubjectSerializer
    write_serializer_class = SubjectWriteSerializer


class SkillViewSet(TaxonomyChoiceMixin, DirectTaxonomyWriteMixin, SafeTaxonomyDeleteMixin, WriteReadSerializerMixin, StaffParentWritePermissionMixin, viewsets.ModelViewSet):
    queryset = Skill.objects.select_related("category", "subject__category").all()
    serializer_class = SkillSerializer
    write_serializer_class = SkillWriteSerializer


class SkillProgressViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SkillProgressSerializer

    def get_queryset(self):
        return SkillProgress.objects.filter(
            user=self.request.user
        ).select_related("skill", "skill__category", "skill__subject")


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
                "catalog_icon": category_catalog_icon(category),
                "color": category.color,
                "is_retired": category.is_retired,
                "available_for_new_choices": available_for_new_choices(category),
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
        ).select_related("skill", "skill__category", "skill__subject")

        categories = {}
        for sp in progress:
            cat_name = sp.skill.category.name
            if cat_name not in categories:
                categories[cat_name] = {
                    "category_id": sp.skill.category_id,
                    "icon": sp.skill.category.icon,
                    "catalog_icon": category_catalog_icon(sp.skill.category),
                    "color": sp.skill.category.color,
                    "skills": [],
                }
            categories[cat_name]["skills"].append(
                SkillProgressSerializer(sp).data
            )

        return Response({
            "badges_earned": UserBadgeSerializer(badges, many=True, context={"request": request}).data,
            "total_badges": self._total_badges(request),
            "skill_categories": categories,
        })

    @staticmethod
    def _total_badges(request):
        from .availability import availability_for_request, visible_badges
        return visible_badges(Badge.objects.all(), request.user, availability=availability_for_request(request)).count()
