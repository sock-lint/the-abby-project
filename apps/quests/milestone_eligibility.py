"""One native milestone policy for new automatic and legacy catalog offers.

Eligibility reads award nothing. Accepted goals keep their own frozen promise;
these checks never revoke or rearm one of those goals.
"""
from django.core.exceptions import ValidationError
from django.db.models import Q


def has_milestone_gate(definition):
    return bool(definition.prerequisite_quest_id or definition.required_skill_id
                or definition.required_skill_level)


def validate_milestone_gate(definition):
    from .models import QuestDefinition

    level = definition.required_skill_level
    if type(level) is not int or not 0 <= level <= 6:
        raise ValidationError({"required_skill_level": "Choose a whole skill level from 0 to 6."})
    if bool(definition.required_skill_id) != bool(level):
        raise ValidationError({"required_skill_level": "A required skill needs a level from 1 to 6; no skill requires level 0."})
    if not has_milestone_gate(definition):
        return
    if not definition.is_system or definition.created_by_id is not None or definition.is_repeatable:
        raise ValidationError("Milestone gates apply only to one-time global challenges.")
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
        prior = QuestDefinition.objects.filter(pk=prerequisite_id, is_system=True, created_by__isnull=True).values(
            "prerequisite_quest_id",
        ).first()
        if prior is None:
            raise ValidationError({"prerequisite_quest": "Choose an existing global challenge prerequisite."})
        prerequisite_id = prior["prerequisite_quest_id"]


def prerequisite_completion(user, prerequisite_id):
    """Exact catalog identity; private same-name goals cannot impersonate it.

    Legacy quests have no completed_at. Their last saved state is a conservative
    source cutoff, rather than an invented historical completion timestamp.
    """
    from .models import ChallengeOccurrence, Quest
    automatic = ChallengeOccurrence.objects.filter(
        goal__user=user, goal__family_id=user.family_id, goal__is_catalog=True,
        goal__catalog_definition_id=prerequisite_id, status="completed",
    )
    legacy = Quest.objects.filter(
        participants__user=user, definition_id=prerequisite_id, status="completed",
    )
    times = list(automatic.exclude(completed_at=None).values_list("completed_at", flat=True))
    times += list(legacy.values_list("updated_at", flat=True))
    return automatic.exists() or legacy.exists(), min(times) if times else None


def prerequisite_unavailable(user, prerequisite_id):
    """True once ``user`` can no longer complete a one-time prerequisite path.

    A nonrepeatable catalog goal keeps exactly one accepted window, and new
    legacy starts are refused once that goal exists, so an ended window without
    completion is final. A prerequisite that has no accepted goal yet and is
    itself milestone-gated inherits its own prerequisite's state. Unknown
    shapes, such as a goal without occurrences, stay available.
    """
    from django.utils import timezone
    from .models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition

    now = timezone.now()
    seen = set()
    while prerequisite_id is not None and prerequisite_id not in seen and len(seen) < 100:
        seen.add(prerequisite_id)
        if prerequisite_completion(user, prerequisite_id)[0]:
            return False
        prior = QuestDefinition.objects.filter(pk=prerequisite_id).values(
            "is_repeatable", "prerequisite_quest_id",
        ).first()
        if prior is None or prior["is_repeatable"]:
            return False
        if Quest.objects.filter(participants__user=user, definition_id=prerequisite_id, status="active").exists():
            return False
        goals = ChallengeGoal.objects.filter(user=user, catalog_definition_id=prerequisite_id, is_catalog=True)
        if goals.exists():
            occurrences = ChallengeOccurrence.objects.filter(goal__in=goals)
            return occurrences.exists() and not occurrences.filter(status="active", ends_at__gt=now).exists()
        prerequisite_id = prior["prerequisite_quest_id"]
    return False


def milestone_eligibility(user, definition):
    from apps.achievements.models import SkillProgress, UserBadge

    try:
        validate_milestone_gate(definition)
    except ValidationError:
        return {"unlocked": False, "requirements": [
            {"kind": "policy", "met": False, "description": "This challenge's milestone rules need review."},
        ], "locked_reasons": ["This challenge's milestone rules need review."]}
    requirements = []
    if has_milestone_gate(definition) and user is not None:
        from .models import ChallengeGoal, Quest
        if (ChallengeGoal.objects.filter(user=user, catalog_definition=definition).exists()
                or Quest.objects.filter(definition=definition, participants__user=user).exists()):
            requirements.append({"kind": "accepted", "met": False,
                                 "description": "This one-time challenge already has an accepted window."})
    if definition.prerequisite_quest_id:
        met, _ = prerequisite_completion(user, definition.prerequisite_quest_id) if user is not None else (False, None)
        requirements.append({"kind": "challenge", "met": met,
                             "description": f"Complete {definition.prerequisite_quest.name}."})
    if definition.required_skill_id:
        met = SkillProgress.objects.filter(
            user=user, skill_id=definition.required_skill_id, level__gte=definition.required_skill_level,
            unlocked=True,
        ).exists()
        requirements.append({"kind": "skill", "met": met,
                             "description": f"Reach level {definition.required_skill_level} in {definition.required_skill.name}."})
    if definition.required_badge_id:
        met = UserBadge.objects.filter(user=user, badge_id=definition.required_badge_id).exists()
        requirements.append({"kind": "badge", "met": met,
                             "description": f"Earn the {definition.required_badge.name} badge."})
    reasons = [row["description"] for row in requirements if not row["met"]]
    return {"unlocked": not reasons, "requirements": requirements, "locked_reasons": reasons}


def gate_snapshot(definition):
    return {"version": 1, "prerequisite_quest_id": definition.prerequisite_quest_id,
            "required_skill_id": definition.required_skill_id,
            "required_skill_level": definition.required_skill_level,
            "required_badge_id": definition.required_badge_id}


def gated_definitions():
    from .models import QuestDefinition
    return QuestDefinition.objects.filter(is_system=True, created_by__isnull=True).filter(
        Q(prerequisite_quest__isnull=False) | Q(required_skill__isnull=False)
        | Q(required_skill_level__gt=0),
    ).select_related("prerequisite_quest", "required_skill", "required_badge")
