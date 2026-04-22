"""Life-RPG skill-tag surface for chores (2026-04-21).

Adds ``Chore.xp_reward`` and the ``ChoreSkillTag`` through-table so
approving a chore distributes XP across the skill tree — closing the
gap where duties fed coins/money but never the skill tree.

Parallel to ``ProjectSkillTag`` (projects) and ``HomeworkSkillTag``
(homework). ``ChoreService.approve_completion`` calls the new
``AwardService.grant(xp_tags=...)`` path after the migration.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0008_life_rpg_badge_criteria"),
        ("chores", "0002_alter_chorecompletion_decided_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="chore",
            name="xp_reward",
            field=models.PositiveIntegerField(
                default=10,
                help_text=(
                    "Total XP pool distributed across ChoreSkillTag rows on approval. "
                    "Zero = chore awards coins/money only (legacy behaviour). "
                    "Split proportionally by each tag's xp_weight."
                ),
            ),
        ),
        migrations.CreateModel(
            name="ChoreSkillTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("xp_weight", models.IntegerField(
                    default=1,
                    help_text="Relative share of Chore.xp_reward this skill receives.",
                )),
                ("chore", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="skill_tags",
                    to="chores.chore",
                )),
                ("skill", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    to="achievements.skill",
                )),
            ],
            options={
                "unique_together": {("chore", "skill")},
            },
        ),
    ]
