from django.conf import settings
from django.db import models


class SkillCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default="#D97706")
    description = models.TextField(blank=True)

    class Meta:
        # Preserve original table name so the move is a state-only migration.
        db_table = "projects_skillcategory"
        verbose_name_plural = "skill categories"
        ordering = ["name"]

    def __str__(self):
        return f"{self.icon} {self.name}"


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
        SkillCategory, on_delete=models.CASCADE,
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
        SkillCategory, on_delete=models.CASCADE,
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
        TOTAL_COINS_EARNED = "total_coins_earned", "Total Coins Earned"
        DAYS_WORKED = "days_worked", "Days Worked"
        CROSS_CATEGORY_UNLOCK = "cross_category_unlock", "Cross-Category Unlock"
        QUEST_COMPLETED = "quest_completed", "Quest Completed"
        HOMEWORK_PLANNED_AHEAD = "homework_planned_ahead", "Homework Planned Ahead"
        HOMEWORK_ON_TIME_COUNT = "homework_on_time_count", "Homework On Time Count"
        # Pet / mount collection
        PETS_HATCHED = "pets_hatched", "Pets Hatched"
        PET_SPECIES_OWNED = "pet_species_owned", "Pet Species Owned"
        MOUNTS_EVOLVED = "mounts_evolved", "Mounts Evolved"
        # Progression beats that had no badge coverage
        CHORE_COMPLETIONS = "chore_completions", "Chore Completions Approved"
        MILESTONES_COMPLETED = "milestones_completed", "Milestones Completed"
        PERFECT_DAYS_COUNT = "perfect_days_count", "Perfect Days (lifetime)"
        SAVINGS_GOAL_COMPLETED = "savings_goal_completed", "Savings Goal Completed"
        BOUNTY_COMPLETED = "bounty_completed", "Bounty Project Completed"
        REWARD_REDEEMED = "reward_redeemed", "Rewards Redeemed"
        HABIT_MAX_STRENGTH = "habit_max_strength", "Habit Max Strength"
        STREAK_FREEZE_USED = "streak_freeze_used", "Streak Freeze Used"
        EARLY_BIRD = "early_bird", "Clock In Before 8 AM"
        LATE_NIGHT = "late_night", "Clock In After 9 PM"
        FAST_PROJECT = "fast_project", "Project Completed Quickly"
        # 2026-04-22 review — depth-in-one-dimension badges
        CATEGORY_MASTERY = "category_mastery", "Category Mastery"
        FULL_POTION_SHELF = "full_potion_shelf", "Full Potion Shelf"
        CONSUMABLE_VARIETY = "consumable_variety", "Consumable Variety"
        COINS_SPENT_LIFETIME = "coins_spent_lifetime", "Coins Spent (lifetime)"
        GRADE_REACHED = "grade_reached", "Grade Reached"
        BIRTHDAYS_LOGGED = "birthdays_logged", "Birthdays Logged"
        COSMETIC_FULL_SET = "cosmetic_full_set", "All Cosmetic Slots Equipped"
        # 2026-04-23 content review — new subsystem-recognition criteria.
        # Each has a registered checker in ``apps/achievements/criteria.py``.
        HABIT_TAPS_LIFETIME = "habit_taps_lifetime", "Habit Taps (lifetime)"
        HABIT_COUNT_AT_STRENGTH = "habit_count_at_strength", "Habit Count at Strength"
        BADGES_EARNED_COUNT = "badges_earned_count", "Badges Earned (count)"
        CO_OP_PROJECT_COMPLETED = "co_op_project_completed", "Co-op Project Completed"
        BOSS_QUESTS_COMPLETED = "boss_quests_completed", "Boss Quests Completed"
        COLLECTION_QUESTS_COMPLETED = "collection_quests_completed", "Collection Quests Completed"
        CHRONICLE_MILESTONES_LOGGED = "chronicle_milestones_logged", "Chronicle Milestones Logged"
        COSMETIC_SET_OWNED = "cosmetic_set_owned", "Cosmetic Set Owned"
        # Journal-authoring criteria (Scribe badge line).
        JOURNAL_ENTRIES_WRITTEN = "journal_entries_written", "Journal Entries Written"
        JOURNAL_STREAK_DAYS = "journal_streak_days", "Journal Streak Days"

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
    award_coins = models.BooleanField(
        default=True,
        help_text=(
            "When True (default), earning this badge pays rarity-scaled coins "
            "per COINS_PER_BADGE_RARITY. Set False for badges that represent "
            "purely cosmetic achievement titles (e.g. quest-completion badges) "
            "where the associated quest already paid out."
        ),
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
