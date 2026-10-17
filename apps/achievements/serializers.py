from rest_framework import serializers
from apps.rpg.catalog_icons import badge_catalog_icon, category_catalog_icon, skill_catalog_icon, subject_catalog_icon

from .models import Badge, Skill, SkillCategory, SkillProgress, Subject, UserBadge


class SkillCategorySerializer(serializers.ModelSerializer):
    catalog_icon = serializers.SerializerMethodField()

    def get_catalog_icon(self, obj):
        return category_catalog_icon(obj)

    class Meta:
        model = SkillCategory
        fields = ["id", "name", "icon", "catalog_icon", "color", "description"]


class SubjectSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    catalog_icon = serializers.SerializerMethodField()

    def get_catalog_icon(self, obj):
        return subject_catalog_icon(obj)

    class Meta:
        model = Subject
        fields = ["id", "name", "category", "category_name", "description", "icon", "catalog_icon", "order"]


class SubjectWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["name", "category", "description", "icon", "order"]


class SkillSerializer(serializers.ModelSerializer):
    catalog_icon = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)

    def get_catalog_icon(self, obj):
        return skill_catalog_icon(obj)

    class Meta:
        model = Skill
        fields = [
            "id", "name", "category", "category_name",
            "subject", "subject_name", "description",
            "icon", "catalog_icon", "level_names", "is_locked_by_default", "order",
        ]


class SkillWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = [
            "name", "category", "subject", "description",
            "icon", "level_names", "is_locked_by_default", "order",
        ]


class SkillProgressSerializer(serializers.ModelSerializer):
    skill_catalog_icon = serializers.SerializerMethodField()
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_icon = serializers.CharField(source="skill.icon", read_only=True)
    subject_name = serializers.CharField(source="skill.subject.name", read_only=True, default=None)
    category_name = serializers.CharField(
        source="skill.category.name", read_only=True
    )

    def get_skill_catalog_icon(self, obj):
        return skill_catalog_icon(obj.skill)

    class Meta:
        model = SkillProgress
        fields = [
            "id", "user", "skill", "skill_name", "skill_icon", "skill_catalog_icon",
            "category_name", "subject_name", "xp_points", "level", "unlocked",
            "xp_to_next_level",
        ]


class BadgeSerializer(serializers.ModelSerializer):
    catalog_available = serializers.SerializerMethodField()
    catalog_icon = serializers.SerializerMethodField()

    def get_catalog_icon(self, obj):
        return badge_catalog_icon(obj)

    def get_catalog_available(self, obj):
        from .availability import badge_goal_is_available
        request = self.context.get("request")
        return badge_goal_is_available(obj, getattr(request, "user", None))

    class Meta:
        model = Badge
        fields = [
            "id", "name", "description", "icon", "catalog_icon", "subject", "criteria_type",
            "criteria_value", "xp_bonus", "rarity", "catalog_available",
        ]


class BadgeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = [
            "name", "description", "icon", "subject", "criteria_type",
            "criteria_value", "xp_bonus", "rarity",
        ]


class UserBadgeSerializer(serializers.ModelSerializer):
    badge = BadgeSerializer(read_only=True)

    class Meta:
        model = UserBadge
        fields = ["id", "user", "badge", "earned_at"]
