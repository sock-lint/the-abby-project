from django.db import models
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import (
    Badge, ProjectSkillTag, Skill, SkillProgress, UserBadge, XP_THRESHOLDS,
)


class SkillService:
    @staticmethod
    def level_for_xp(xp):
        """Determine level based on XP thresholds."""
        level = 0
        for lvl, threshold in sorted(XP_THRESHOLDS.items()):
            if xp >= threshold:
                level = lvl
            else:
                break
        return level

    @classmethod
    def award_xp(cls, user, skill, amount):
        """Award XP to a user for a specific skill. Returns the SkillProgress."""
        progress, _ = SkillProgress.objects.get_or_create(
            user=user, skill=skill,
            defaults={"unlocked": not skill.is_locked_by_default},
        )
        if not progress.unlocked:
            return progress

        progress.xp_points += amount
        progress.level = cls.level_for_xp(progress.xp_points)
        progress.save()

        cls.evaluate_unlocks(user)
        return progress

    @classmethod
    def distribute_project_xp(cls, user, project, total_xp):
        """Distribute XP across a project's skill tags by weight ratio."""
        tags = ProjectSkillTag.objects.filter(project=project).select_related("skill")
        if not tags.exists():
            return

        total_weight = sum(tag.xp_weight for tag in tags)
        for tag in tags:
            skill_xp = round(total_xp * (tag.xp_weight / total_weight))
            if skill_xp > 0:
                cls.award_xp(user, tag.skill, skill_xp)

    @classmethod
    def evaluate_unlocks(cls, user):
        """Check all locked skills to see if prerequisites are now met."""
        locked_skills = Skill.objects.filter(is_locked_by_default=True)
        newly_unlocked = []

        for skill in locked_skills:
            progress, _ = SkillProgress.objects.get_or_create(
                user=user, skill=skill,
                defaults={"unlocked": False},
            )
            if progress.unlocked:
                continue

            prerequisites = skill.prerequisites.select_related("required_skill").all()
            if not prerequisites.exists():
                continue

            all_met = all(
                SkillProgress.objects.filter(
                    user=user,
                    skill=prereq.required_skill,
                    level__gte=prereq.required_level,
                ).exists()
                for prereq in prerequisites
            )

            if all_met:
                progress.unlocked = True
                progress.save()
                newly_unlocked.append(skill)

        return newly_unlocked

    @staticmethod
    def get_category_summary(user, category):
        """Get aggregated level and total XP for a category."""
        progress = SkillProgress.objects.filter(
            user=user, skill__category=category, unlocked=True,
        )
        if not progress.exists():
            return {"level": 0, "total_xp": 0}

        agg = progress.aggregate(
            avg_level=models.Avg("level"),
            total_xp=models.Sum("xp_points"),
        )
        return {
            "level": round(agg["avg_level"] or 0),
            "total_xp": agg["total_xp"] or 0,
        }

    @staticmethod
    def get_skill_tree(user, category):
        """Return all skills in a category with user progress."""
        skills = Skill.objects.filter(category=category).prefetch_related(
            "prerequisites__required_skill",
        )
        progress_map = {
            sp.skill_id: sp
            for sp in SkillProgress.objects.filter(user=user, skill__category=category)
        }

        tree = []
        for skill in skills:
            sp = progress_map.get(skill.id)
            prereqs = [
                {
                    "skill_id": p.required_skill_id,
                    "skill_name": p.required_skill.name,
                    "required_level": p.required_level,
                    "met": SkillProgress.objects.filter(
                        user=user,
                        skill=p.required_skill,
                        level__gte=p.required_level,
                    ).exists() if sp and not sp.unlocked else True,
                }
                for p in skill.prerequisites.all()
            ]
            tree.append({
                "id": skill.id,
                "name": skill.name,
                "icon": skill.icon,
                "description": skill.description,
                "is_locked_by_default": skill.is_locked_by_default,
                "level_names": skill.level_names,
                "xp_points": sp.xp_points if sp else 0,
                "level": sp.level if sp else 0,
                "unlocked": sp.unlocked if sp else not skill.is_locked_by_default,
                "xp_to_next_level": sp.xp_to_next_level if sp else XP_THRESHOLDS.get(1, 100),
                "prerequisites": prereqs,
            })
        return tree


class BadgeService:
    @classmethod
    def evaluate_badges(cls, user):
        """Check all unearned badges and award any newly qualified."""
        earned_ids = set(
            UserBadge.objects.filter(user=user).values_list("badge_id", flat=True)
        )
        all_badges = Badge.objects.exclude(id__in=earned_ids)
        newly_earned = []

        for badge in all_badges:
            if cls._check_criteria(user, badge):
                UserBadge.objects.create(user=user, badge=badge)
                if badge.xp_bonus > 0:
                    cls._award_badge_xp(user, badge)
                newly_earned.append(badge)

        return newly_earned

    @classmethod
    def _check_criteria(cls, user, badge):
        criteria = badge.criteria_value
        ct = badge.criteria_type

        if ct == Badge.CriteriaType.FIRST_CLOCK_IN:
            return user.time_entries.filter(status="completed").exists()

        elif ct == Badge.CriteriaType.FIRST_PROJECT:
            return user.assigned_projects.filter(status="completed").exists()

        elif ct == Badge.CriteriaType.PROJECTS_COMPLETED:
            count = criteria.get("count", 1)
            return user.assigned_projects.filter(status="completed").count() >= count

        elif ct == Badge.CriteriaType.HOURS_WORKED:
            target = criteria.get("hours", 0)
            total = user.time_entries.filter(
                status="completed"
            ).aggregate(
                total=Sum("duration_minutes")
            )["total"] or 0
            return (total / 60) >= target

        elif ct == Badge.CriteriaType.HOURS_IN_DAY:
            target = criteria.get("hours", 4)
            from django.db.models.functions import TruncDate
            daily = user.time_entries.filter(
                status="completed"
            ).annotate(
                day=TruncDate("clock_in")
            ).values("day").annotate(
                total=Sum("duration_minutes")
            ).filter(total__gte=target * 60)
            return daily.exists()

        elif ct == Badge.CriteriaType.DAYS_WORKED:
            target = criteria.get("count", 5)
            from django.db.models.functions import TruncDate
            days = user.time_entries.filter(
                status="completed"
            ).annotate(
                day=TruncDate("clock_in")
            ).values("day").distinct().count()
            return days >= target

        elif ct == Badge.CriteriaType.STREAK_DAYS:
            target = criteria.get("days", 7)
            return cls._check_streak(user, target)

        elif ct == Badge.CriteriaType.CATEGORY_PROJECTS:
            count = criteria.get("count", 3)
            category_count = criteria.get("categories", None)
            if category_count:
                cats = user.assigned_projects.filter(
                    status="completed", category__isnull=False,
                ).values("category").annotate(
                    c=Count("id")
                ).filter(c__gte=1)
                return cats.count() >= category_count
            else:
                category_name = criteria.get("category")
                return user.assigned_projects.filter(
                    status="completed",
                    category__name__iexact=category_name,
                ).count() >= count

        elif ct == Badge.CriteriaType.MATERIALS_UNDER_BUDGET:
            from apps.projects.models import Project
            return Project.objects.filter(
                assigned_to=user, status="completed",
                materials_budget__gt=0,
            ).annotate(
                actual_total=Sum("materials__actual_cost")
            ).filter(
                actual_total__lt=models.F("materials_budget") * models.Value(0.9)
            ).exists()

        elif ct == Badge.CriteriaType.PERFECT_TIMECARD:
            return user.timecards.filter(status="approved").exists()

        elif ct == Badge.CriteriaType.SKILL_LEVEL_REACHED:
            target_level = criteria.get("level", 2)
            count = criteria.get("count", 1)
            return SkillProgress.objects.filter(
                user=user, level__gte=target_level,
            ).count() >= count

        elif ct == Badge.CriteriaType.SKILLS_UNLOCKED:
            count = criteria.get("count", 1)
            unlocked = SkillProgress.objects.filter(
                user=user, unlocked=True, skill__is_locked_by_default=True,
            ).count()
            return unlocked >= count

        elif ct == Badge.CriteriaType.SKILL_CATEGORIES_BREADTH:
            min_level = criteria.get("min_level", 1)
            category_count = criteria.get("categories", 4)
            cats = SkillProgress.objects.filter(
                user=user, level__gte=min_level,
            ).values("skill__category").distinct().count()
            return cats >= category_count

        elif ct == Badge.CriteriaType.PHOTOS_UPLOADED:
            count = criteria.get("count", 10)
            return user.photos.count() >= count

        elif ct == Badge.CriteriaType.TOTAL_EARNED:
            target = criteria.get("amount", 500)
            from apps.payments.models import PaymentLedger
            total = PaymentLedger.objects.filter(
                user=user, amount__gt=0,
            ).aggregate(total=Sum("amount"))["total"] or 0
            return total >= target

        elif ct == Badge.CriteriaType.CROSS_CATEGORY_UNLOCK:
            from apps.achievements.models import SkillPrerequisite
            unlocked_skills = SkillProgress.objects.filter(
                user=user, unlocked=True, skill__is_locked_by_default=True,
            ).values_list("skill_id", flat=True)
            return SkillPrerequisite.objects.filter(
                skill_id__in=unlocked_skills,
            ).exclude(
                required_skill__category=models.F("skill__category"),
            ).exists()

        return False

    @staticmethod
    def _check_streak(user, target_days):
        """Check if user has a consecutive day streak of at least target_days."""
        from django.db.models.functions import TruncDate
        days = list(
            user.time_entries.filter(
                status="completed"
            ).annotate(
                day=TruncDate("clock_in")
            ).values_list("day", flat=True).distinct().order_by("-day")
        )
        if not days:
            return False

        streak = 1
        for i in range(1, len(days)):
            if (days[i - 1] - days[i]).days == 1:
                streak += 1
                if streak >= target_days:
                    return True
            else:
                streak = 1
        return streak >= target_days

    @staticmethod
    def _award_badge_xp(user, badge):
        """Distribute badge XP bonus evenly across user's active skills."""
        active_progress = SkillProgress.objects.filter(
            user=user, unlocked=True, level__gt=0,
        )
        if not active_progress.exists():
            return
        xp_each = max(1, badge.xp_bonus // active_progress.count())
        for sp in active_progress:
            sp.xp_points += xp_each
            sp.level = SkillService.level_for_xp(sp.xp_points)
            sp.save()
