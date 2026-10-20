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
    definitions = {row.pk: row for row in Definition.objects.using(database).filter(
        is_system=True, created_by__isnull=True,
    ).order_by("pk")}
    # Trust retained aliases only within the creatorless global catalog. A
    # cycle, self-reference or owner/private target is not a canonical identity.
    roots = {}
    for pk in definitions:
        path, seen, current = [], set(), pk
        while current not in roots:
            if current not in definitions or current in seen:
                canonical = None
                break
            path.append(current)
            seen.add(current)
            parent = definitions[current].superseded_by_id
            if parent is None:
                canonical = current
                break
            current = parent
        else:
            canonical = roots[current]
        roots.update((member, canonical) for member in path)

    candidates = {pk: row for pk, row in definitions.items() if row.superseded_by_id is None}
    children, ready = defaultdict(list), []
    for pk, row in candidates.items():
        if row.prerequisite_quest_id is None:
            ready.append(pk)
        elif roots.get(row.prerequisite_quest_id) in candidates:
            children[roots[row.prerequisite_quest_id]].append(pk)
    # Process prerequisites before dependants, irrespective of row ID order.
    # Each row enters one ready batch at most. Cyclic/self-gated or private
    # prerequisite paths never become ready and remain held without rewrites.
    resolved = {}
    while ready:
        groups = defaultdict(list)
        for pk in sorted(ready):
            definition = candidates[pk]
            prior = definition.prerequisite_quest_id
            signature = json.dumps({
                "name": definition.name, "type": definition.quest_type,
                "target": definition.target_value, "duration": definition.duration_days,
                "filter": definition.trigger_filter, "badge": definition.required_badge_id,
                "prerequisite": resolved[roots[prior]] if prior is not None else None,
                "required_skill": definition.required_skill_id,
                "required_skill_level": definition.required_skill_level,
                "repeatable": definition.is_repeatable, "coins": definition.coin_reward,
                "xp": definition.xp_reward, "items": sorted(rewards[pk]),
                "skills": sorted(tags[pk]),
            }, sort_keys=True)
            groups[signature].append(pk)
        for members in groups.values():
            canonical = min(members)
            resolved.update((member, canonical) for member in members)
        ready = [child for parent in ready for child in children[parent]]

    canonical_ids = {pk: resolved[root] for pk, root in roots.items() if root in resolved}
    groups = defaultdict(list)
    for pk, canonical in canonical_ids.items():
        if pk != canonical:
            groups[canonical].append(pk)
    for canonical, aliases in groups.items():
        Definition.objects.using(database).filter(pk__in=aliases).update(superseded_by_id=canonical)
        users_with_canonical = set(Goal.objects.using(database).filter(
            catalog_definition_id=canonical,
        ).values_list("user_id", flat=True))
        # Keep one saved goal's ID/windows/receipts/anchor. Additional accepted
        # aliases retain their windows but cannot create future duplicate ones.
        for goal in Goal.objects.using(database).filter(
            catalog_definition_id__in=aliases, is_catalog=True,
        ).order_by("pk"):
            if goal.user_id not in users_with_canonical:
                Goal.objects.using(database).filter(pk=goal.pk).update(catalog_definition_id=canonical)
                users_with_canonical.add(goal.user_id)
    # Only current global prerequisites change; accepted gate snapshots and
    # creator-owned policy fields retain their exact saved values.
    for definition in definitions.values():
        prior = definition.prerequisite_quest_id
        canonical = canonical_ids.get(prior)
        if canonical is not None and prior != canonical:
            Definition.objects.using(database).filter(pk=definition.pk).update(prerequisite_quest_id=canonical)


class Migration(migrations.Migration):
    dependencies = [("quests", "0010_milestone_gate_acceptance")]

    operations = [
        migrations.AddField(
            model_name="questdefinition", name="superseded_by",
            field=models.ForeignKey(blank=True, editable=False, null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name="retained_aliases",
                help_text="Retained duplicate identity; only its canonical definition is offered for new acceptance.",
                to="quests.questdefinition"),
        ),
    ]
