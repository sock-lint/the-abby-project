"""One native milestone policy for new automatic and legacy catalog offers.

Eligibility reads award nothing. Accepted goals keep their own frozen promise;
these checks never revoke or rearm one of those goals.
"""
from django.core.exceptions import ValidationError
from django.db import OperationalError, connection, transaction
from django.db.models import Q


def has_milestone_gate(definition):
    return bool(definition.prerequisite_quest_id or definition.required_skill_id
                or definition.required_skill_level)


def validate_milestone_gate(definition, *, active_definitions=None):
    level = definition.required_skill_level
    if type(level) is not int or not 0 <= level <= 6:
        raise ValidationError({"required_skill_level": "Choose a whole skill level from 0 to 6."})
    if bool(definition.required_skill_id) != bool(level):
        raise ValidationError({"required_skill_level": "A required skill needs a level from 1 to 6; no skill requires level 0."})
    if not has_milestone_gate(definition):
        return
    if not definition.is_system or definition.created_by_id is not None or definition.is_repeatable:
        raise ValidationError("Milestone gates apply only to one-time global challenges.")
    if definition.is_cooperative:
        raise ValidationError("Milestone gates apply only to personal challenges.")
    if (definition.quest_type != "collection"
            or definition.trigger_filter != {"allowed_triggers": ["reading_logged"]}):
        raise ValidationError("Milestone gates currently support daily Reading Adventures only, without extra activity filters.")
    seen = {definition.pk} if definition.pk else set()
    prerequisite_id = definition.prerequisite_quest_id
    while prerequisite_id is not None:
        if len(seen) >= 100:
            raise ValidationError({"prerequisite_quest": "Challenge prerequisite chains must contain fewer than 100 entries."})
        if prerequisite_id in seen:
            raise ValidationError({"prerequisite_quest": "Challenge prerequisites cannot form a cycle."})
        seen.add(prerequisite_id)
        if active_definitions is None:
            from .queries import active_system_definitions
            prior = active_system_definitions().filter(pk=prerequisite_id, created_by__isnull=True).values(
                "prerequisite_quest_id",
            ).first()
        else:
            known = active_definitions.get(prerequisite_id)
            prior = {"prerequisite_quest_id": known.prerequisite_quest_id} if known is not None and known.created_by_id is None else None
        if prior is None:
            raise ValidationError({"prerequisite_quest": "Choose an existing canonical global challenge prerequisite."})
        prerequisite_id = prior["prerequisite_quest_id"]


def _equivalent_ids(definition_id):
    from .models import QuestDefinition
    from .queries import equivalent_definition_ids
    definition = QuestDefinition.objects.filter(pk=definition_id).first()
    return equivalent_definition_ids(definition) if definition is not None else []


def prerequisite_completion(user, prerequisite_id):
    """Canonical saved identities; private same-name goals cannot impersonate it.

    Legacy quests have no completed_at. Their last saved state is a conservative
    source cutoff, rather than an invented historical completion timestamp.
    """
    from .models import ChallengeOccurrence, Quest
    definition_ids = _equivalent_ids(prerequisite_id)
    automatic = ChallengeOccurrence.objects.filter(
        goal__user=user, goal__family_id=user.family_id, goal__is_catalog=True,
        goal__catalog_definition_id__in=definition_ids, status="completed",
    )
    legacy = Quest.objects.filter(
        participants__user=user, definition_id__in=definition_ids, status="completed",
    )
    times = list(automatic.exclude(completed_at=None).values_list("completed_at", flat=True))
    times += list(legacy.values_list("updated_at", flat=True))
    return automatic.exists() or legacy.exists(), min(times) if times else None


def discovery_prerequisite_pairs(prerequisite):
    """Typed companion equivalents for a future retired global egg offer.

    This bridge supplies eligibility only. It never completes the retired
    challenge or changes an already accepted milestone's requirement.
    """
    from .availability import definition_uses_egg_discovery

    if prerequisite.created_by_id is not None or not definition_uses_egg_discovery(prerequisite):
        return []
    items = [row.item for row in prerequisite.reward_items.select_related("item__pet_species", "item__potion_type")]
    eggs = [item for item in items if item.item_type == "egg"]
    potions = [item for item in items if item.item_type == "potion"]
    # Untyped historical ingredients cannot establish an exact hatch pair.
    if not potions or any(not item.pet_species_id for item in eggs) or any(not item.potion_type_id for item in potions):
        return []
    return [{"species_id": species_id, "potion_id": potion_id,
             "species_name": species_name, "potion_name": potion_name}
            for species_id, species_name in sorted({(item.pet_species_id, item.pet_species.name) for item in eggs})
            for potion_id, potion_name in sorted({(item.potion_type_id, item.potion_type.name) for item in potions})]


def _hatched_prerequisite_pairs(user, pairs):
    from django.utils import timezone
    from apps.pets.models import PetIncubation, UserMount, UserPet

    if user is None:
        return False
    expected = {(pair["species_id"], pair["potion_id"]) for pair in pairs}
    owned = set(UserPet.objects.filter(user=user).values_list("species_id", "potion_id"))
    owned.update(UserMount.objects.filter(user=user).values_list("species_id", "potion_id"))
    owned.update(PetIncubation.objects.filter(user=user, hatched_at__lte=timezone.now()).values_list(
        "species_id", "potion_type_id",
    ))
    return expected <= owned


def admit_discovery_prerequisite(definition):
    """Fence fresh bridge ingredients without waiting behind a catalog edit.

    A single savepoint owns every added lock, including the shared ingredient
    fence. A busy prerequisite rolls them all back while source work survives.
    """
    from .availability import RetryCatalogBusy, lock_retry_reward_catalog
    from .models import QuestDefinition, QuestRewardItem

    try:
        with transaction.atomic():
            lock_retry_reward_catalog()
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    # Raw relation edits need not lock their parent row. The
                    # shared table fence also excludes INSERT/UPDATE/DELETE
                    # until the newly accepted pair snapshot is committed.
                    cursor.execute("LOCK TABLE " + connection.ops.quote_name(QuestRewardItem._meta.db_table)
                                   + " IN SHARE MODE NOWAIT")
            if connection.vendor == "postgresql" and definition.prerequisite_quest_id:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM " + connection.ops.quote_name(QuestDefinition._meta.db_table)
                        + " WHERE id = %s FOR SHARE NOWAIT", [definition.prerequisite_quest_id],
                    )
                    cursor.fetchall()
    except OperationalError as error:
        cause = error.__cause__
        if getattr(cause, "sqlstate", getattr(cause, "pgcode", None)) != "55P03":
            raise
        raise RetryCatalogBusy("Prerequisite rewards are changing. Your reading is saved; try your next Reading Adventure.") from error


def prerequisite_unavailable(user, prerequisite_id, *, controls=None):
    """True once ``user`` can no longer complete a one-time prerequisite path.

    An expired unpaid window remains reachable through an explicit native retry.
    Retained aliases share their canonical identity. A prerequisite without an
    accepted goal inherits its own prerequisite's state. Unknown shapes, such as
    a goal without occurrences, stay available.
    """
    from django.utils import timezone
    from .models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition
    from .controls import control_context, retry_state

    now = timezone.now()
    seen = set()
    while prerequisite_id is not None and prerequisite_id not in seen and len(seen) < 100:
        seen.add(prerequisite_id)
        if prerequisite_completion(user, prerequisite_id)[0]:
            return False
        definition_ids = _equivalent_ids(prerequisite_id)
        definition = QuestDefinition.objects.filter(pk=prerequisite_id).first()
        if definition is not None and discovery_prerequisite_pairs(definition):
            # The exact companion can still be earned through discovery even
            # when an old prerequisite attempt ended without completion.
            return False
        canonical_id = (definition.superseded_by_id or definition.pk) if definition is not None else None
        prior = QuestDefinition.objects.filter(pk=canonical_id).values(
            "is_repeatable", "prerequisite_quest_id",
        ).first()
        if prior is None or prior["is_repeatable"]:
            return False
        if Quest.objects.filter(participants__user=user, definition_id__in=definition_ids, status="active").exists():
            return False
        goals = ChallengeGoal.objects.filter(user=user, family_id=user.family_id,
                                            catalog_definition_id__in=definition_ids, is_catalog=True)
        if goals.exists():
            occurrences = ChallengeOccurrence.objects.filter(goal__in=goals)
            if not occurrences.exists() or occurrences.filter(status="active").filter(
                Q(ends_at__gt=now) | Q(ends_at__isnull=True),
            ).exists():
                return False
            controls = controls if controls is not None else control_context(user)
            return not any(retry_state(row, controls)["allowed"] for row in occurrences.select_related("goal__catalog_definition"))
        prerequisite_id = prior["prerequisite_quest_id"]
    return False


def milestone_eligibility(user, definition, *, new_enrollment=True, facts=None, active_definitions=None, accepted_gate=None):
    from apps.achievements.models import SkillProgress, UserBadge

    try:
        validate_milestone_gate(definition, active_definitions=active_definitions)
    except ValidationError:
        return {"unlocked": False, "requirements": [
            {"kind": "policy", "met": False, "description": "This challenge's milestone rules need review."},
        ], "locked_reasons": ["This challenge's milestone rules need review."]}
    requirements = []
    # An empty prefetched relation establishes that this loaded definition has
    # no reward tags. Do not add catalog queries to taxonomy-free projections;
    # uncached or referenced definitions still check current retirement state.
    prefetched_tags = getattr(definition, "_prefetched_objects_cache", {}).get("skill_tags")
    taxonomy_free = (
        not definition.required_skill_id
        and isinstance(definition.trigger_filter, dict)
        and definition.trigger_filter.get("skill_category_id") is None
        and prefetched_tags is not None and not prefetched_tags
    )
    if new_enrollment and not taxonomy_free:
        from .models import QuestDefinition
        from .reference_locks import definitions_with_available_taxonomy
        if definition.pk and not definitions_with_available_taxonomy(QuestDefinition.objects.filter(pk=definition.pk)).exists():
            requirements.append({"kind": "taxonomy", "met": False,
                                 "description": "Restore retired taxonomy before starting this challenge."})
    if new_enrollment and has_milestone_gate(definition) and user is not None:
        from .models import ChallengeGoal, Quest
        definition_ids = _equivalent_ids(definition.pk)
        if (ChallengeGoal.objects.filter(user=user, family_id=user.family_id,
                                        catalog_definition_id__in=definition_ids).exists()
                or Quest.objects.filter(definition_id__in=definition_ids, participants__user=user).exists()):
            requirements.append({"kind": "accepted", "met": False,
                                 "description": "This one-time challenge already has an accepted window."})
    discovery_pairs = []
    if definition.prerequisite_quest_id:
        if facts is None:
            met, _ = prerequisite_completion(user, definition.prerequisite_quest_id) if user is not None else (False, None)
        else:
            met = definition.prerequisite_quest_id in facts["completed"]
        if new_enrollment:
            discovery_pairs = discovery_prerequisite_pairs(definition.prerequisite_quest)
        elif (isinstance(accepted_gate, dict) and type(accepted_gate.get("version")) is int
              and accepted_gate["version"] == 2):
            frozen = accepted_gate.get("prerequisite_hatch_pairs")
            if isinstance(frozen, list) and frozen and all(
                isinstance(pair, dict) and type(pair.get("species_id")) is int and pair["species_id"] > 0
                and type(pair.get("potion_id")) is int and pair["potion_id"] > 0
                and isinstance(pair.get("species_name"), str) and isinstance(pair.get("potion_name"), str)
                for pair in frozen
            ):
                discovery_pairs = frozen
        if discovery_pairs:
            met = met or _hatched_prerequisite_pairs(user, discovery_pairs)
            companions = ", ".join(f"{pair['potion_name']} {pair['species_name']}" for pair in discovery_pairs)
            description = f"Complete {definition.prerequisite_quest.name}, or hatch {companions}."
        else:
            description = f"Complete {definition.prerequisite_quest.name}."
        requirements.append({"kind": "challenge", "met": met, "description": description})
    if definition.required_skill_id:
        from apps.achievements.taxonomy import available_skills
        available = not new_enrollment or available_skills().filter(pk=definition.required_skill_id).exists()
        met = facts["skill_levels"].get(definition.required_skill_id, 0) >= definition.required_skill_level if facts is not None else SkillProgress.objects.filter(
            user=user, skill_id=definition.required_skill_id, level__gte=definition.required_skill_level,
            unlocked=True,
        ).exists()
        met = met and available
        requirements.append({"kind": "skill", "met": met,
                             "description": f"Reach level {definition.required_skill_level} in {definition.required_skill.name}."})
    if definition.required_badge_id:
        met = definition.required_badge_id in facts["badges"] if facts is not None else UserBadge.objects.filter(user=user, badge_id=definition.required_badge_id).exists()
        requirements.append({"kind": "badge", "met": met,
                             "description": f"Earn the {definition.required_badge.name} badge."})
    reasons = [row["description"] for row in requirements if not row["met"]]
    return {"unlocked": not reasons, "requirements": requirements, "locked_reasons": reasons,
            **({"prerequisite_hatch_pairs": discovery_pairs} if discovery_pairs else {})}


def retry_milestone_states(user, definitions, *, catalog, identities, legacy):
    """Build current retry eligibility once for the shared control context.

    Definitions and canonical/legacy maps come from that context. Required
    skills, badges and automatic completions each use one batched read; all
    subsequent result/history/receipt projections reuse these exact facts.
    """
    from apps.achievements.models import SkillProgress, UserBadge
    from .models import ChallengeOccurrence

    if not definitions:
        return {}
    prerequisites = {row.prerequisite_quest_id for row in definitions if row.prerequisite_quest_id}
    equivalent_ids = {pk for pk, canonical in identities.items() if (canonical or pk) in prerequisites}
    completed = {pk for pk, statuses in legacy.items() if "completed" in statuses}
    completed.update(identities.get(pk) or pk for pk in ChallengeOccurrence.objects.filter(
        goal__user=user, goal__family_id=user.family_id, goal__is_catalog=True,
        goal__catalog_definition_id__in=equivalent_ids, status="completed",
    ).values_list("goal__catalog_definition_id", flat=True))
    facts = {
        "completed": completed,
        "skill_levels": dict(SkillProgress.objects.filter(
            user=user, unlocked=True,
            skill_id__in={row.required_skill_id for row in definitions if row.required_skill_id},
        ).values_list("skill_id", "level")),
        "badges": set(UserBadge.objects.filter(
            user=user, badge_id__in={row.required_badge_id for row in definitions if row.required_badge_id},
        ).values_list("badge_id", flat=True)),
    }
    # Each canonical identity's latest accepted attempt owns its gate policy,
    # matching control_context's retry choice. V1 promises keep their strict
    # original prerequisite; V2 retries reuse only their frozen exact pairs,
    # even after discovery is disabled or the catalog bundle changes.
    target_ids = {row.pk for row in definitions}
    accepted_ids = {pk for pk, canonical in identities.items() if (canonical or pk) in target_ids}
    gates = {}
    for row in ChallengeOccurrence.objects.filter(
        goal__user=user, goal__family_id=user.family_id, goal__is_catalog=True,
        goal__catalog_definition_id__in=accepted_ids,
    ).order_by("-starts_at", "-pk").values("goal__catalog_definition_id", "snapshot"):
        definition_id = row["goal__catalog_definition_id"]
        canonical = identities.get(definition_id) or definition_id
        if canonical not in gates:
            gates[canonical] = row["snapshot"].get("catalog_gate") if isinstance(row["snapshot"], dict) else None
    return {row.pk: milestone_eligibility(user, row, new_enrollment=False, facts=facts,
                                        active_definitions=catalog, accepted_gate=gates.get(row.pk))["unlocked"]
            for row in definitions}


def gate_snapshot(definition, *, prerequisite_hatch_pairs=None):
    return {"version": 1, "prerequisite_quest_id": definition.prerequisite_quest_id,
            "required_skill_id": definition.required_skill_id,
            "required_skill_level": definition.required_skill_level,
            "required_badge_id": definition.required_badge_id,
            **({"version": 2, "prerequisite_hatch_pairs": prerequisite_hatch_pairs} if prerequisite_hatch_pairs else {})}


def gated_definitions():
    from .queries import active_system_definitions
    return active_system_definitions().filter(created_by__isnull=True, is_cooperative=False).filter(
        Q(prerequisite_quest__isnull=False) | Q(required_skill__isnull=False)
        | Q(required_skill_level__gt=0),
    ).select_related("prerequisite_quest", "required_skill", "required_badge")
