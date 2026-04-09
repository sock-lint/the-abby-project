from django.conf import settings
from django.db import models

XP_THRESHOLDS = {
    0: 0,
    1: 100,
    2: 300,
    3: 600,
    4: 1000,
    5: 1500,
    6: 2500,
}


class Subject(models.Model):
    """Intermediate grouping between SkillCategory and Skill.

    Modeled after the SkillTree platform's Project -> Subject -> Skill
    hierarchy. Categories hold Subjects; Subjects hold Skills.
    """

    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        "projects.SkillCategory", on_delete=models.CASCADE,
        related_name="subjects",
    )
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["category", "order", "name"]
        unique_together = [("category", "name")]

    def __str__(self):
        return f"{self.icon} {self.name}"


class Skill(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        "projects.SkillCategory", on_delete=models.CASCADE,
        related_name="skills",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="skills",
    )
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    level_names = models.JSONField(default=dict)
    is_locked_by_default = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["category", "subject", "order"]
        unique_together = [("category", "name")]

    def __str__(self):
        return f"{self.icon} {self.name}"


class SkillPrerequisite(models.Model):
    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="prerequisites"
    )
    required_skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="unlocks"
    )
    required_level = models.IntegerField(default=2)

    class Meta:
        unique_together = [("skill", "required_skill")]

    def __str__(self):
        return f"{self.skill.name} requires {self.required_skill.name} L{self.required_level}"


class SkillProgress(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="skill_progress",
    )
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    xp_points = models.IntegerField(default=0)
    level = models.IntegerField(default=0)
    unlocked = models.BooleanField(default=True)

    class Meta:
        unique_together = [("user", "skill")]

    def __str__(self):
        return f"{self.user} — {self.skill.name} (L{self.level})"

    @property
    def category_id(self):
        return self.skill.category_id

    @property
    def xp_to_next_level(self):
        next_level = self.level + 1
        if next_level not in XP_THRESHOLDS:
            return 0
        return XP_THRESHOLDS[next_level] - self.xp_points


class ProjectSkillTag(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE,
        related_name="skill_tags",
    )
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    xp_weight = models.IntegerField(default=1)

    class Meta:
        unique_together = [("project", "skill")]

    def __str__(self):
        return f"{self.project.title} — {self.skill.name} ({self.xp_weight}x)"


class MilestoneSkillTag(models.Model):
    milestone = models.ForeignKey(
        "projects.ProjectMilestone", on_delete=models.CASCADE,
        related_name="skill_tags",
    )
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    xp_amount = models.IntegerField(default=15)

    class Meta:
        unique_together = [("milestone", "skill")]

    def __str__(self):
        return f"{self.milestone.title} — {self.skill.name} ({self.xp_amount} XP)"


class Badge(models.Model):
    class CriteriaType(models.TextChoices):
        PROJECTS_COMPLETED = "projects_completed", "Projects Completed"
        HOURS_WORKED = "hours_worked", "Hours Worked"
        CATEGORY_PROJECTS = "category_projects", "Category Projects"
        STREAK_DAYS = "streak_days", "Streak Days"
        FIRST_PROJECT = "first_project", "First Project"
        FIRST_CLOCK_IN = "first_clock_in", "First Clock In"
        MATERIALS_UNDER_BUDGET = "materials_under_budget", "Materials Under Budget"
        PERFECT_TIMECARD = "perfect_timecard", "Perfect Timecard"
        SKILL_LEVEL_REACHED = "skill_level_reached", "Skill Level Reached"
        SKILLS_UNLOCKED = "skills_unlocked", "Skills Unlocked"
        SKILL_CATEGORIES_BREADTH = "skill_categories_breadth", "Skill Categories Breadth"
        SUBJECTS_COMPLETED = "subjects_completed", "Subjects Completed"
        HOURS_IN_DAY = "hours_in_day", "Hours in a Day"
        PHOTOS_UPLOADED = "photos_uploaded", "Photos Uploaded"
        TOTAL_EARNED = "total_earned", "Total Earned"
        DAYS_WORKED = "days_worked", "Days Worked"
        CROSS_CATEGORY_UNLOCK = "cross_category_unlock", "Cross-Category Unlock"

    class Rarity(models.TextChoices):
        COMMON = "common", "Common"
        UNCOMMON = "uncommon", "Uncommon"
        RARE = "rare", "Rare"
        EPIC = "epic", "Epic"
        LEGENDARY = "legendary", "Legendary"

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    icon = models.CharField(max_length=50, blank=True)
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="badges",
    )
    criteria_type = models.CharField(max_length=30, choices=CriteriaType.choices)
    criteria_value = models.JSONField(default=dict)
    xp_bonus = models.PositiveIntegerField(default=0)
    rarity = models.CharField(
        max_length=10, choices=Rarity.choices, default=Rarity.COMMON
    )

    class Meta:
        ordering = ["rarity", "name"]

    def __str__(self):
        return f"{self.icon} {self.name}"


class UserBadge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="badges",
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="awards")
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "badge")]

    def __str__(self):
        return f"{self.user} earned {self.badge.name}"
