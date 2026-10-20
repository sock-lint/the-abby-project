"""Reconcile equivalent system templates without deleting accepted promises."""
import json
from collections import defaultdict

import django.db.models.deletion
from django.db import migrations, models


def reconcile_definitions(apps, schema_editor):
    Definition = apps.get_model("quests", "QuestDefinition")
    Reward = apps.get_model("quests", "QuestRewardItem")
    SkillTag = apps.get_model("quests", "QuestSkillTag")
    Goal = apps.get_model("quests", "ChallengeGoal")
    database = schema_editor.connection.alias
    rewards, tags = defaultdict(list), defaultdict(list)
    for definition_id, item_id, quantity in Reward.objects.using(database).values_list(
        "quest_definition_id", "item_id", "quantity",
    ):
        rewards[definition_id].append((item_id, quantity))
    for definition_id, skill_id, weight in SkillTag.objects.using(database).values_list(
        "quest_definition_id", "skill_id", "xp_weight",
    ):
        tags[definition_id].append((skill_id, weight))
    groups = defaultdict(list)
    for definition in Definition.objects.using(database).filter(
        is_system=True, created_by__isnull=True, superseded_by__isnull=True,
    ).order_by("pk"):
        # Display copy/art may differ. Every rule and reward must match exactly;
        # divergent same-name definitions remain unaliased and held by runtime.
        # Creator-owned rows can carry an old loader's system flag. Preserve
        # that provenance and its accepted goals rather than adopting by name.
        signature = json.dumps({
            "name": definition.name, "type": definition.quest_type,
            "target": definition.target_value, "duration": definition.duration_days,
            "filter": definition.trigger_filter, "badge": definition.required_badge_id,
            "repeatable": definition.is_repeatable, "coins": definition.coin_reward,
            "xp": definition.xp_reward, "items": sorted(rewards[definition.pk]),
            "skills": sorted(tags[definition.pk]),
        }, sort_keys=True)
        groups[signature].append(definition.pk)
    for definition_ids in groups.values():
        if len(definition_ids) < 2:
            continue
        canonical, aliases = definition_ids[0], definition_ids[1:]
        Definition.objects.using(database).filter(pk__in=aliases).update(superseded_by_id=canonical)
        users_with_canonical = set(Goal.objects.using(database).filter(
            catalog_definition_id=canonical,
        ).values_list("user_id", flat=True))
        # Keep one existing goal's UUID/windows/receipts/anchor when it is the
        # child's sole identity. Additional accepted aliases retain their saved
        # windows, but runtime never opens another repeat window for them.
        for goal in Goal.objects.using(database).filter(
            catalog_definition_id__in=aliases, is_catalog=True,
        ).order_by("pk"):
            if goal.user_id not in users_with_canonical:
                Goal.objects.using(database).filter(pk=goal.pk).update(catalog_definition_id=canonical)
                users_with_canonical.add(goal.user_id)


class Migration(migrations.Migration):
    dependencies = [("quests", "0009_challenge_discovery")]

    operations = [
        migrations.AddField(
            model_name="questdefinition", name="superseded_by",
            field=models.ForeignKey(blank=True, editable=False, null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name="retained_aliases",
                help_text="Retained duplicate identity; only its canonical definition is offered for new acceptance.",
                to="quests.questdefinition"),
        ),
        migrations.RunPython(reconcile_definitions, migrations.RunPython.noop),
    ]
