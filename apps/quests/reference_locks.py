"""Keep fresh explicit category choices valid through private definition writes."""
from apps.achievements.models import SkillCategory
from apps.rpg.taxonomy_references import admit_references


def lock_filter_category(trigger_filter):
    """Call AFTER definition INSERT, inside that same atomic transaction.

    Catalog retirement takes table admission before target-row locks; inserting
    first preserves that order. SHARE also excludes non-key retirement UPDATEs.
    """
    category_id = trigger_filter.get("skill_category_id") if isinstance(trigger_filter, dict) else None
    if category_id is None:
        return
    if type(category_id) is not int or category_id < 1 or not SkillCategory.objects.filter(pk=category_id).exists():
        raise ValueError("Choose an existing skill category.")
    admit_references(SkillCategory, [category_id])


def admit_definition_choices(definition):
    """Validate before NEW acceptance; accepted snapshots/payouts skip this."""
    from apps.achievements.models import Skill
    lock_filter_category(definition.trigger_filter)
    ids = {tag.skill_id for tag in definition.skill_tags.all()}
    if definition.required_skill_id:
        ids.add(definition.required_skill_id)
    admit_references(Skill, ids)


def lock_definition_write():
    """Admit private tag replacements before taking taxonomy row locks."""
    from django.db import connection
    from .models import QuestDefinition
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("LOCK TABLE " + connection.ops.quote_name(QuestDefinition._meta.db_table)
                           + " IN ROW EXCLUSIVE MODE")


def definitions_with_available_taxonomy(queryset):
    """Projection-only filtering; canonical identities/history stay unfiltered."""
    from django.db.models import Q, Subquery
    from apps.achievements.models import Skill
    from apps.achievements.taxonomy import available_skills
    unavailable = Skill.objects.exclude(pk__in=Subquery(available_skills().values("pk")))
    # A JSON transform and an integer-valued subquery have incompatible PG
    # types (jsonb = bigint). Literal RHS values use Django's JSON adaptation;
    # legacy malformed filters therefore never require an unsafe integer cast.
    retired_categories = list(SkillCategory.objects.filter(is_retired=True).values_list("pk", flat=True))
    return queryset.exclude(
        Q(required_skill_id__in=Subquery(unavailable.values("pk")))
        | Q(skill_tags__skill_id__in=Subquery(unavailable.values("pk")))
        | (Q(trigger_filter__has_key="skill_category_id")
           & Q(trigger_filter__skill_category_id__in=retired_categories))
    ).distinct()


def admit_snapshot_choices(snapshot, *, required_skill_id=None):
    """Only a newly materialized occurrence/retry calls this admission gate."""
    from apps.achievements.models import Skill
    lock_filter_category(snapshot.get("filter", {}))
    ids = {row["skill_id"] for row in snapshot.get("skill_tags", [])}
    if required_skill_id:
        ids.add(required_skill_id)
    admit_references(Skill, ids)
