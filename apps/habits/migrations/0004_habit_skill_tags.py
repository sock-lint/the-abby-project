"""Life-RPG skill-tag surface for habits (2026-04-21).

Adds the ``HabitSkillTag`` through-table. Positive habit taps now
distribute the habit's ``xp_reward`` pool across the tagged skills
via ``AwardService.grant(xp_tags=...)`` — fixing the silent-drop
where the ``xp_reward`` field existed on every habit but never
reached ``SkillProgress``.

Negative taps remain skill-neutral (matches the no-coins rule).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0008_life_rpg_badge_criteria"),
        ("habits", "0003_remove_stale_decay_periodic_task"),
    ]

    operations = [
        migrations.CreateModel(
            name="HabitSkillTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("xp_weight", models.IntegerField(
                    default=1,
                    help_text="Relative share of Habit.xp_reward this skill receives.",
                )),
                ("habit", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="skill_tags",
                    to="habits.habit",
                )),
                ("skill", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    to="achievements.skill",
                )),
            ],
            options={
                "unique_together": {("habit", "skill")},
            },
        ),
    ]
