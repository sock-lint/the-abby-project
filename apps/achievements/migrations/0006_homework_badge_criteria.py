"""Add HOMEWORK_PLANNED_AHEAD + HOMEWORK_ON_TIME_COUNT to Badge.CriteriaType.

Supports the new organization-themed badges introduced when homework
stopped paying money/coins — rewards now come from XP, drops, and
progression achievements. Checkers live in ``apps/achievements/criteria.py``.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0005_receive_skillcategory"),
    ]

    operations = [
        migrations.AlterField(
            model_name="badge",
            name="criteria_type",
            field=models.CharField(
                choices=[
                    ("projects_completed", "Projects Completed"),
                    ("hours_worked", "Hours Worked"),
                    ("category_projects", "Category Projects"),
                    ("streak_days", "Streak Days"),
                    ("first_project", "First Project"),
                    ("first_clock_in", "First Clock In"),
                    ("materials_under_budget", "Materials Under Budget"),
                    ("perfect_timecard", "Perfect Timecard"),
                    ("skill_level_reached", "Skill Level Reached"),
                    ("skills_unlocked", "Skills Unlocked"),
                    ("skill_categories_breadth", "Skill Categories Breadth"),
                    ("subjects_completed", "Subjects Completed"),
                    ("hours_in_day", "Hours in a Day"),
                    ("photos_uploaded", "Photos Uploaded"),
                    ("total_earned", "Total Earned"),
                    ("days_worked", "Days Worked"),
                    ("cross_category_unlock", "Cross-Category Unlock"),
                    ("quest_completed", "Quest Completed"),
                    ("homework_planned_ahead", "Homework Planned Ahead"),
                    ("homework_on_time_count", "Homework On Time Count"),
                ],
                max_length=30,
            ),
        ),
    ]
