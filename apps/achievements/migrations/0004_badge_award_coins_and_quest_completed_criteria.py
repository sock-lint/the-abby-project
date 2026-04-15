"""Add Badge.award_coins + QUEST_COMPLETED criteria type.

``award_coins`` lets specific badges opt out of the rarity-scaled coin
payout in ``BadgeService._award_badge_coins`` — used for quest-completion
badges where the quest itself already paid out.

``QUEST_COMPLETED`` is the 18th ``CriteriaType`` value. Its evaluator
lives in ``apps/achievements/criteria.py`` and checks for a completed
``Quest`` matching a given quest-definition name.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0003_alter_subject_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="badge",
            name="award_coins",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When True (default), earning this badge pays rarity-scaled coins "
                    "per COINS_PER_BADGE_RARITY. Set False for badges that represent "
                    "purely cosmetic achievement titles (e.g. quest-completion badges) "
                    "where the associated quest already paid out."
                ),
            ),
        ),
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
                ],
                max_length=30,
            ),
        ),
    ]
