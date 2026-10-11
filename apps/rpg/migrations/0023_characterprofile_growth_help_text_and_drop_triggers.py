"""Align field metadata while preserving queues and historical drop rows."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rpg", "0022_spriteasset_original_intent")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="characterprofile",
                    name="pending_companion_growth",
                    field=models.JSONField(
                        blank=True,
                        default=list,
                        help_text=(
                            "Queue of unseen companion auto-growth events surfaced as toasts on next page load. "
                            "Appended by PetService.auto_grow_companions on each daily check-in; cleared by the "
                            "/pets/companion-growth/seen/ endpoint. Survives multi-day gaps so a returning user "
                            "sees every tick they missed without flooding the UI."
                        ),
                    ),
                ),
                migrations.AlterField(
                    model_name="droptable",
                    name="trigger_type",
                    field=models.CharField(
                        choices=[
                            ("clock_out", "Clock Out"),
                            ("chore_complete", "Chore Complete"),
                            ("homework_complete", "Homework Complete"),
                            ("homework_created", "Homework Created"),
                            ("milestone_complete", "Milestone Complete"),
                            ("project_complete", "Project Complete"),
                            ("badge_earned", "Badge Earned"),
                            ("quest_complete", "Quest Complete"),
                            ("perfect_day", "Perfect Day"),
                            ("habit_log", "Habit Log"),
                            ("daily_check_in", "Daily Check-In"),
                            ("savings_goal_complete", "Savings Goal Complete"),
                            ("journal_entry", "Journal Entry"),
                            ("creation_logged", "Creation Logged"),
                            ("movement_session", "Movement Session"),
                            ("expedition_returned", "Expedition Returned"),
                        ],
                        max_length=30,
                    ),
                ),
            ],
        ),
    ]
