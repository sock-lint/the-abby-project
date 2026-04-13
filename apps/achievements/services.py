from django.db import models
from django.db.models import Count, Sum

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
    def _serialize_skill(skill, sp, user):
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
        return {
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
        }

    @staticmethod
    def get_subject_summary(user, subject):
        """Get aggregated level and total XP for a subject."""
        progress = SkillProgress.objects.filter(
            user=user, skill__subject=subject, unlocked=True,
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

    @classmethod
    def get_skill_tree(cls, user, category):
        """Return subjects nested with skills + user progress for a category."""
        from .models import Subject

        subjects = Subject.objects.filter(category=category).order_by("order", "name")
        skills = Skill.objects.filter(category=category).prefetch_related(
            "prerequisites__required_skill",
        )
        progress_map = {
            sp.skill_id: sp
            for sp in SkillProgress.objects.filter(user=user, skill__category=category)
        }

        skills_by_subject = {}
        orphan_skills = []
        for skill in skills:
            entry = cls._serialize_skill(skill, progress_map.get(skill.id), user)
            if skill.subject_id:
                skills_by_subject.setdefault(skill.subject_id, []).append(entry)
            else:
                orphan_skills.append(entry)

        tree = []
        for subject in subjects:
            tree.append({
                "id": subject.id,
                "name": subject.name,
                "icon": subject.icon,
                "description": subject.description,
                "order": subject.order,
                "summary": cls.get_subject_summary(user, subject),
                "skills": skills_by_subject.get(subject.id, []),
            })
        if orphan_skills:
            tree.append({
                "id": None,
                "name": "Other",
                "icon": "",
                "description": "",
                "order": 9999,
                "summary": {"level": 0, "total_xp": 0},
                "skills": orphan_skills,
            })
        return tree


class AwardService:
    """Unified XP + coin + badge awarding pipeline.

    The same three-step sequence (award XP → award coins → re-evaluate badges)
    runs from clock-out, project completion, and milestone completion. Routing
    it through one call site keeps those hooks consistent and makes it trivial
    to add a new award trigger later.
    """

    @staticmethod
    def grant(
        user,
        *,
        project=None,
        xp=0,
        coins=0,
        coin_reason=None,
        coin_description="",
        created_by=None,
    ):
        if project is not None and xp > 0:
            SkillService.distribute_project_xp(user, project, xp)

        if coins > 0 and coin_reason is not None:
            from apps.rewards.services import CoinService
            CoinService.award_coins(
                user,
                coins,
                coin_reason,
                description=coin_description,
                created_by=created_by,
            )

        BadgeService.evaluate_badges(user)


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
                cls._award_badge_coins(user, badge)
                newly_earned.append(badge)

        return newly_earned

    @staticmethod
    def _award_badge_coins(user, badge):
        """Award coins scaled by badge rarity."""
        from django.conf import settings
        from apps.rewards.services import CoinService
        from apps.rewards.models import CoinLedger

        rarity_map = getattr(settings, "COINS_PER_BADGE_RARITY", {})
        amount = int(rarity_map.get(badge.rarity, 0))
        if amount <= 0:
            return
        CoinService.award_coins(
            user, amount, CoinLedger.Reason.BADGE_BONUS,
            description=f"Badge earned: {badge.name}",
        )

    @classmethod
    def _check_criteria(cls, user, badge):
        checker = _CRITERIA_CHECKERS.get(badge.criteria_type)
        if checker is None:
            return False
        return checker(user, badge.criteria_value or {})

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


# ---------------------------------------------------------------------------
# Badge criteria checker registry
# ---------------------------------------------------------------------------
#
# Each checker is a pure function ``(user, criteria: dict) -> bool``. The
# registry keeps the dispatch in BadgeService._check_criteria trivial and makes
# every criterion testable on its own.


def _check_first_clock_in(user, _c):
    from apps.timecards.services import TimeEntryService
    return TimeEntryService.completed_entries(user).exists()


def _check_first_project(user, _c):
    return user.assigned_projects.filter(status="completed").exists()


def _check_projects_completed(user, c):
    return user.assigned_projects.filter(status="completed").count() >= c.get("count", 1)


def _check_hours_worked(user, c):
    from apps.timecards.services import TimeEntryService
    total = TimeEntryService.completed_entries(user).aggregate(
        total=Sum("duration_minutes")
    )["total"] or 0
    return (total / 60) >= c.get("hours", 0)


def _check_hours_in_day(user, c):
    from apps.timecards.services import TimeEntryService
    target = c.get("hours", 4)
    return TimeEntryService.daily_minute_totals(user).filter(
        total__gte=target * 60
    ).exists()


def _check_days_worked(user, c):
    from apps.timecards.services import TimeEntryService
    return len(TimeEntryService.distinct_days(user)) >= c.get("count", 5)


def _check_streak_days(user, c):
    from apps.timecards.services import TimeEntryService
    return TimeEntryService.longest_streak_at_least(user, c.get("days", 7))


def _check_category_projects(user, c):
    count = c.get("count", 3)
    category_count = c.get("categories")
    if category_count:
        cats = user.assigned_projects.filter(
            status="completed", category__isnull=False,
        ).values("category").annotate(n=Count("id")).filter(n__gte=1)
        return cats.count() >= category_count
    return user.assigned_projects.filter(
        status="completed", category__name__iexact=c.get("category"),
    ).count() >= count


def _check_materials_under_budget(user, _c):
    from apps.projects.models import Project
    return Project.objects.filter(
        assigned_to=user, status="completed", materials_budget__gt=0,
    ).annotate(
        actual_total=Sum("materials__actual_cost")
    ).filter(
        actual_total__lt=models.F("materials_budget") * models.Value(0.9)
    ).exists()


def _check_perfect_timecard(user, _c):
    return user.timecards.filter(status="approved").exists()


def _check_skill_level_reached(user, c):
    return SkillProgress.objects.filter(
        user=user, level__gte=c.get("level", 2),
    ).count() >= c.get("count", 1)


def _check_skills_unlocked(user, c):
    return SkillProgress.objects.filter(
        user=user, unlocked=True, skill__is_locked_by_default=True,
    ).count() >= c.get("count", 1)


def _check_subjects_completed(user, c):
    return SkillProgress.objects.filter(
        user=user,
        level__gte=c.get("min_level", 2),
        skill__subject__isnull=False,
    ).values("skill__subject").distinct().count() >= c.get("count", 1)


def _check_skill_categories_breadth(user, c):
    return SkillProgress.objects.filter(
        user=user, level__gte=c.get("min_level", 1),
    ).values("skill__category").distinct().count() >= c.get("categories", 4)


def _check_photos_uploaded(user, c):
    return user.photos.count() >= c.get("count", 10)


def _check_total_earned(user, c):
    from apps.payments.models import PaymentLedger
    total = PaymentLedger.objects.filter(
        user=user, amount__gt=0,
    ).aggregate(total=Sum("amount"))["total"] or 0
    return total >= c.get("amount", 500)


def _check_cross_category_unlock(user, _c):
    from apps.achievements.models import SkillPrerequisite
    unlocked_skills = SkillProgress.objects.filter(
        user=user, unlocked=True, skill__is_locked_by_default=True,
    ).values_list("skill_id", flat=True)
    return SkillPrerequisite.objects.filter(
        skill_id__in=unlocked_skills,
    ).exclude(
        required_skill__category=models.F("skill__category"),
    ).exists()


_CRITERIA_CHECKERS = {
    Badge.CriteriaType.FIRST_CLOCK_IN: _check_first_clock_in,
    Badge.CriteriaType.FIRST_PROJECT: _check_first_project,
    Badge.CriteriaType.PROJECTS_COMPLETED: _check_projects_completed,
    Badge.CriteriaType.HOURS_WORKED: _check_hours_worked,
    Badge.CriteriaType.HOURS_IN_DAY: _check_hours_in_day,
    Badge.CriteriaType.DAYS_WORKED: _check_days_worked,
    Badge.CriteriaType.STREAK_DAYS: _check_streak_days,
    Badge.CriteriaType.CATEGORY_PROJECTS: _check_category_projects,
    Badge.CriteriaType.MATERIALS_UNDER_BUDGET: _check_materials_under_budget,
    Badge.CriteriaType.PERFECT_TIMECARD: _check_perfect_timecard,
    Badge.CriteriaType.SKILL_LEVEL_REACHED: _check_skill_level_reached,
    Badge.CriteriaType.SKILLS_UNLOCKED: _check_skills_unlocked,
    Badge.CriteriaType.SUBJECTS_COMPLETED: _check_subjects_completed,
    Badge.CriteriaType.SKILL_CATEGORIES_BREADTH: _check_skill_categories_breadth,
    Badge.CriteriaType.PHOTOS_UPLOADED: _check_photos_uploaded,
    Badge.CriteriaType.TOTAL_EARNED: _check_total_earned,
    Badge.CriteriaType.CROSS_CATEGORY_UNLOCK: _check_cross_category_unlock,
}
