from rest_framework import serializers

from .models import Badge, Skill, SkillProgress, UserBadge


class SkillSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Skill
        fields = [
            "id", "name", "category", "category_name", "description",
            "icon", "level_names", "is_locked_by_default", "order",
        ]


class SkillProgressSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_icon = serializers.CharField(source="skill.icon", read_only=True)
    category_name = serializers.CharField(
        source="skill.category.name", read_only=True
    )

    class Meta:
        model = SkillProgress
        fields = [
            "id", "user", "skill", "skill_name", "skill_icon",
            "category_name", "xp_points", "level", "unlocked",
            "xp_to_next_level",
        ]


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = [
            "id", "name", "description", "icon", "criteria_type",
            "criteria_value", "xp_bonus", "rarity",
        ]


class UserBadgeSerializer(serializers.ModelSerializer):
    badge = BadgeSerializer(read_only=True)

    class Meta:
        model = UserBadge
        fields = ["id", "user", "badge", "earned_at"]
