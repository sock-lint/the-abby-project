"""Expand Badge.CriteriaType with life-RPG progression criteria.

Adds criterion types for pet/mount collection, chore/milestone/savings-goal/
bounty/reward counters, Perfect Day tallies, habit strength, streak-freeze
use, time-of-day clock-ins, and fast-project completion. Each has a matching
``@criterion`` checker in ``apps/achievements/criteria.py``.

Also includes ``total_coins_earned``, which was added to the enum alongside
the coin ledger rollout but never made it into an AlterField migration —
folding it in here keeps the declared choices list in sync with the model.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0007_pr1_reward_cleanup"),
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
                    ("total_coins_earned", "Total Coins Earned"),
                    ("days_worked", "Days Worked"),
                    ("cross_category_unlock", "Cross-Category Unlock"),
                    ("quest_completed", "Quest Completed"),
                    ("homework_planned_ahead", "Homework Planned Ahead"),
                    ("homework_on_time_count", "Homework On Time Count"),
                    ("pets_hatched", "Pets Hatched"),
                    ("pet_species_owned", "Pet Species Owned"),
                    ("mounts_evolved", "Mounts Evolved"),
                    ("chore_completions", "Chore Completions Approved"),
                    ("milestones_completed", "Milestones Completed"),
                    ("perfect_days_count", "Perfect Days (lifetime)"),
                    ("savings_goal_completed", "Savings Goal Completed"),
                    ("bounty_completed", "Bounty Project Completed"),
                    ("reward_redeemed", "Rewards Redeemed"),
                    ("habit_max_strength", "Habit Max Strength"),
                    ("streak_freeze_used", "Streak Freeze Used"),
                    ("early_bird", "Clock In Before 8 AM"),
                    ("late_night", "Clock In After 9 PM"),
                    ("fast_project", "Project Completed Quickly"),
                ],
                max_length=30,
            ),
        ),
    ]
