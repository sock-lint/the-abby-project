"""Bounded, read-only acquisition hints for one authenticated request."""
from collections import defaultdict

from django.db.models import Prefetch
from django.utils import timezone


def sources_for_request(request):
    if request is None or not request.user.is_authenticated:
        return {}
    if hasattr(request, "_rpg_acquisition_sources"):
        return request._rpg_acquisition_sources
    from apps.achievements.models import UserBadge
    from apps.quests.goals import ACTION_PATHS, FACT_TRIGGERS, TRIGGER_LABELS
    from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestRewardItem
    from apps.quests.queries import active_system_definitions
    from apps.quests.milestone_eligibility import has_milestone_gate, milestone_eligibility
    from apps.rewards.models import Reward
    from .models import CharacterProfile, DropTable
    from .rarity import drop_tier_weights

    user = request.user
    result = defaultdict(list)
    earned = set(UserBadge.objects.filter(user=user).values_list("badge_id", flat=True))
    unavailable_goals = set(ChallengeGoal.objects.filter(
        user=user, repeat_days=0, repeat_weekly=False, occurrences__awarded_at__isnull=False,
    )
        .values_list("pk", flat=True))
    completed_definitions = set(Quest.objects.filter(
        participants__user=user, status="completed", definition__is_repeatable=False,
    ).values_list("definition_id", flat=True))
    now = timezone.now()
    saved_goals = list(ChallengeGoal.objects.filter(user=user, is_catalog=True).select_related("catalog_definition").prefetch_related(
        Prefetch("occurrences", queryset=ChallengeOccurrence.objects.filter(
            starts_at__lte=now, ends_at__gt=now,
        ), to_attr="current_windows"),
    ))
    accepted_definitions = {goal.catalog_definition_id for goal in saved_goals}
    for goal in saved_goals:
        if goal.pk in unavailable_goals or goal.starts_at > now:
            continue
        current = goal.current_windows[0] if goal.current_windows else None
        # An explicit retry has its own frozen window beyond the original
        # goal deadline. Only fall back to that deadline without a saved window.
        if current is None and goal.ends_at <= now and not goal.repeat_days and not goal.repeat_weekly:
            continue
        if current is None and goal.catalog_definition_id and (
            goal.catalog_definition.superseded_by_id or goal.catalog_definition.is_cooperative
        ):
            # Retained personal promises do not advertise a future retired cycle.
            continue
        if current is not None and (current.status != "active" or current.awarded_at is not None):
            continue
        promised = current.snapshot.get("items", []) if current is not None else goal.reward_items
        for reward in promised:
            result[reward["item_id"]].append({"kind": "challenge", "name": goal.name, "path": "/quests?tab=trials"})
    # Legacy active quests also retain their accepted exact item identities.
    # A current catalog edit cannot advertise a different reward for that run.
    from apps.quests.reward_items import accepted_reward_items
    for quest in Quest.objects.filter(
        participants__user=user, status="active", end_date__gt=now,
    ).select_related("definition"):
        accepted_definitions.add(quest.definition_id)
        for reward in accepted_reward_items(quest):
            result[reward.item_id].append({"kind": "challenge", "name": quest.definition.name, "path": "/quests?tab=trials"})

    canonical_ids = dict(QuestDefinition.objects.filter(
        pk__in=accepted_definitions | completed_definitions,
    ).values_list("pk", "superseded_by_id"))
    accepted_definitions |= {canonical_ids.get(pk) or pk for pk in accepted_definitions}
    completed_definitions |= {canonical_ids.get(pk) or pk for pk in completed_definitions}

    # Only public system challenges belong in global item hints. Private
    # parent-authored goal names are never exposed through another household.
    rewards = QuestRewardItem.objects.filter(
        quest_definition__in=active_system_definitions().filter(is_cooperative=False),
    ).select_related(
        "quest_definition", "quest_definition__prerequisite_quest", "quest_definition__required_skill", "quest_definition__required_badge",
    ).order_by("quest_definition__name", "pk")
    milestone_cache = {}
    for reward in rewards:
        definition = reward.quest_definition
        if definition.pk in accepted_definitions or definition.pk in completed_definitions or (definition.required_badge_id and definition.required_badge_id not in earned):
            continue
        if has_milestone_gate(definition):
            if definition.pk not in milestone_cache:
                milestone_cache[definition.pk] = milestone_eligibility(user, definition)["unlocked"]
            if not milestone_cache[definition.pk]:
                continue
        allowed = (definition.trigger_filter or {}).get("allowed_triggers")
        if allowed and not FACT_TRIGGERS.intersection(allowed):
            continue
        result[reward.item_id].append({"kind": "challenge", "name": definition.name, "path": "/quests?tab=trials"})
    offers = Reward.objects.filter(
        family=user.family, is_active=True, fulfillment_kind__in=["digital_item", "both"],
        item_definition__isnull=False,
    ).exclude(stock=0).order_by("name", "pk")
    for offer in offers:
        result[offer.item_definition_id].append({"kind": "shop", "name": offer.name, "path": "/rewards"})
    level = CharacterProfile.objects.filter(user=user).values_list("level", flat=True).first() or 0
    for item_id, trigger, rarity in DropTable.objects.filter(
        min_level__lte=level, weight__gt=0,
    ).order_by("trigger_type").values_list("item_id", "trigger_type", "item__rarity"):
        # Completion loot is a source, not another trackable goal action.
        label = "completed challenges" if trigger == "quest_complete" else TRIGGER_LABELS.get(trigger)
        if label is None or drop_tier_weights(trigger).get(rarity, 0) <= 0:
            continue
        path = ACTION_PATHS.get(trigger, (None, "/quests?tab=trials"))[1]
        result[item_id].append({"kind": "drop", "name": label, "path": path})
    # Keep previews compact; deterministic challenge paths take priority.
    request._rpg_acquisition_sources = {
        item_id: list({(source["kind"], source["name"]): source for source in sources}.values())[:4]
        for item_id, sources in result.items()
    }
    return request._rpg_acquisition_sources
