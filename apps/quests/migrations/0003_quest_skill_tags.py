"""Life-RPG skill-tag surface for quests (2026-04-21).

Adds the ``QuestSkillTag`` through-table. On quest completion,
``QuestService._complete_quest`` now distributes ``xp_reward`` across
the tagged skills via ``AwardService.grant(xp_tags=...)`` instead of
calling ``AwardService.grant(xp=...)`` untagged (which previously
funnelled through ``_award_badge_xp`` and diluted the XP evenly across
every active skill — no skill-tree signal).

Quests with no ``QuestSkillTag`` rows fall back to the old
even-distribution path so existing definitions still pay XP.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0008_life_rpg_badge_criteria"),
        ("quests", "0002_questdefinition_sprite_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuestSkillTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("xp_weight", models.IntegerField(
                    default=1,
                    help_text="Relative share of QuestDefinition.xp_reward this skill receives.",
                )),
                ("quest_definition", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="skill_tags",
                    to="quests.questdefinition",
                )),
                ("skill", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    to="achievements.skill",
                )),
            ],
            options={
                "unique_together": {("quest_definition", "skill")},
            },
        ),
    ]
