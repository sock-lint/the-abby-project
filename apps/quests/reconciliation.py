"""Reviewed identity links for an explicit pair of conflicting global templates.

This is not a content editor. Definitions and accepted promises stay in place;
only an alias pointer and an eligible saved goal's catalog FK may change.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.families.models import Family
from apps.rpg.content.errors import ContentAuthorPermissionDenied, ContentObjectNotFound
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.publication import _catalog_lock, _digest
from apps.rpg.models import ContentPackEntry, ContentPackPublication, RPGContentOverride

from .models import ChallengeGoal, QuestDefinition


OPERATION = "quest_reconciliation_v1"
MAX_MEMBERS = 5000
FIELDS = (
    "name", "description", "icon", "sprite_key", "quest_type", "target_value", "duration_days",
    "trigger_filter", "required_badge_id", "prerequisite_quest_id", "required_skill_id",
    "required_skill_level", "coin_reward", "xp_reward", "is_repeatable", "is_cooperative", "is_system",
)
PRESERVATION = [
    "Both definitions and their authorship remain saved; only the selected source becomes a retained alias.",
    "Accepted windows, progress, contributions, pins, reward promises and earned receipts keep their identities and values.",
    "A sole saved personal goal keeps its identity and repeating anchor under the canonical definition; overlapping accepted windows remain, without future duplicate cycles.",
    "No activity is replayed and no rewards are granted. Existing one-time completion and retry lifetime guards recognize both identities.",
]


class ReconciliationConflict(ContentPackError):
    """The exact reviewed identity plan no longer authorizes this operation."""


def _id(value):
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        raise ContentPackError("Select an existing global challenge by its integer ID.")
    return value


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ContentPackError("Provide a valid reconciliation request UUID.") from None


def _mutex():
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            # Before family/user locks, distinct from the ordinary catalog lock.
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [584680272])


def _bindings(ids):
    rows = list(ChallengeGoal.objects.filter(catalog_definition_id__in=ids).order_by("pk").values_list(
        "pk", "user_id", "family_id", "catalog_definition_id", "is_catalog", "user__family_id",
    )[:MAX_MEMBERS * 2 + 1])
    if len(rows) > MAX_MEMBERS * 2:
        raise ContentPackError("This reconciliation exceeds the supported member limit.")
    return rows


def _members(actor, ids, bindings):
    user_ids = {row[1] for row in bindings} | {actor.pk}
    user_ids.update(QuestDefinition.objects.filter(pk__in=ids).exclude(created_by=None).values_list(
        "created_by_id", flat=True,
    ))
    if len(user_ids) > MAX_MEMBERS:
        raise ContentPackError("This reconciliation exceeds the supported member limit.")
    users = dict(get_user_model().objects.filter(pk__in=user_ids).values_list("pk", "family_id"))
    families = {value for value in users.values() if value is not None}
    families.update(row[2] for row in bindings if row[2] is not None)
    return users, families


@contextmanager
def _authorized(actor, ids=()):
    """Lock household/account gates before catalog or taxonomy admission."""
    bindings = _bindings(ids)
    members, families = _members(actor, ids, bindings)
    if getattr(actor, "family_id", None) is None:
        raise ContentAuthorPermissionDenied("Reconciliation requires a current active staff parent and family.")
    families.add(actor.family_id)
    locked_families = set(Family.objects.select_for_update(no_key=True).filter(pk__in=families)
                          .order_by("pk").values_list("pk", flat=True))
    locked = {user.pk: user for user in get_user_model().objects.select_for_update(no_key=True)
              .filter(pk__in=members).order_by("pk")}
    fresh = locked.get(actor.pk)
    if (fresh is None or not fresh.is_active or not fresh.is_staff or fresh.role != "parent"
            or fresh.family_id != actor.family_id or fresh.family_id not in locked_families):
        raise ContentAuthorPermissionDenied("Reconciliation requires a current active staff parent and family.")
    if {pk: user.family_id for pk, user in locked.items()} != members or locked_families != families:
        raise ReconciliationConflict("Household membership changed; preview this reconciliation again.")
    yield fresh, bindings, members, families


def _receipt(actor, preview_id, *, lock=True):
    queryset = ContentPackPublication.objects.all()
    if lock:
        queryset = queryset.select_for_update()
    receipt = queryset.filter(
        pk=preview_id, actor=actor, family_id=actor.family_id,
    ).first()
    if (receipt is None or receipt.pack != f"qa-{preview_id.hex}"
            or receipt.stats.get("operation") != OPERATION):
        raise ContentObjectNotFound("Reconciliation preview not found for this actor and family.")
    return receipt


def _filter(value):
    # Global previews must not disclose household-specific project/chore/savings IDs.
    if (not isinstance(value, dict)
            or set(value) - {"allowed_triggers", "skill_category_id", "on_time"}):
        raise ContentPackError("Reconciliation supports global activity filters only.")
    if "skill_category_id" in value:
        _id(value["skill_category_id"])
    if "on_time" in value and type(value["on_time"]) is not bool:
        raise ContentPackError("The saved on-time activity filter must be a boolean.")
    if "allowed_triggers" in value and (not isinstance(value["allowed_triggers"], list)
            or any(not isinstance(trigger, str) for trigger in value["allowed_triggers"])):
        raise ContentPackError("The saved activity triggers must be a list of trigger strings.")


def _definition(row):
    return {"id": row.pk, **{field: deepcopy(getattr(row, field)) for field in FIELDS},
            "superseded_by_id": row.superseded_by_id,
            "reward_items": sorted(({"item_id": link.item_id, "quantity": link.quantity}
                                    for link in row.reward_items.all()), key=lambda link: (link["item_id"], link["quantity"])),
            "skill_tags": sorted(({"skill_id": tag.skill_id, "xp_weight": tag.xp_weight}
                                  for tag in row.skill_tags.all()), key=lambda tag: tag["skill_id"]),
            "creator_provenance": "same_family_parent" if row.created_by_id else "creatorless_global"}


def _plan(actor, source_id, canonical_id, original_bindings, members, families):
    ids = (source_id, canonical_id)
    # Acquire definition write locks BEFORE the final binding read. A first
    # acceptance may finish while this waits for its definition SHARE fence.
    rows = {row.pk: row for row in QuestDefinition.objects.select_for_update(no_key=True)
            .filter(pk__in=ids).order_by("pk").prefetch_related("reward_items", "skill_tags")}
    if len(rows) != 2 or any(not row.is_system for row in rows.values()):
        raise ContentObjectNotFound("Select two existing global challenge definitions.")
    bindings = _bindings(ids)
    current_members, current_families = _members(actor, ids, bindings)
    if (bindings != original_bindings or current_members != members or current_families != families):
        raise ReconciliationConflict("Saved challenge identities changed; preview this reconciliation again.")
    source, canonical = rows[source_id], rows[canonical_id]
    if source.created_by_id:
        creator = get_user_model().objects.get(pk=source.created_by_id)
        if creator.family_id != actor.family_id or creator.role != "parent":
            raise ContentAuthorPermissionDenied("This source is authored by another household and is read-only here.")
    if canonical.created_by_id is not None:
        raise ContentPackError("The selected canonical definition must be creatorless global content.")
    if (source.superseded_by_id or canonical.superseded_by_id or source.name != canonical.name
            or set(QuestDefinition.objects.filter(is_system=True, name=source.name,
                superseded_by=None).values_list("pk", flat=True)) != set(ids)):
        raise ContentPackError("Select the exact two unresolved global roots with the same name.")
    if QuestDefinition.objects.filter(superseded_by_id__in=ids).exists():
        raise ContentPackError("Existing retained aliases require a separately reviewed reconciliation.")
    if (source.prerequisite_quest_id or canonical.prerequisite_quest_id
            or QuestDefinition.objects.filter(prerequisite_quest_id__in=ids).exists()):
        raise ContentPackError("Prerequisite relationships require a separately reviewed reconciliation.")
    claims = list(ContentPackEntry.objects.filter(model_label="quests.questdefinition", object_id__in=ids)
                  .order_by("pk").values())
    overrides = list(RPGContentOverride.objects.filter(model_label="quests.questdefinition", object_id__in=ids)
                     .order_by("pk").values())
    if any(row["family_id"] != actor.family_id for row in [*claims, *overrides]):
        raise ContentAuthorPermissionDenied("This catalog identity is authored by another household and is read-only here.")
    if any(row["object_id"] == source_id for row in [*claims, *overrides]):
        raise ContentPackError("The source retains a loader claim or override; reconcile its authoring identity separately.")
    if any(not row[4] for row in bindings):
        raise ContentPackError("A saved noncatalog goal uses this identity; manual review is required.")
    for row in rows.values():
        _filter(row.trigger_filter)
        try:
            row.full_clean()
        except ValidationError as error:
            raise ContentPackError("; ".join(error.messages)) from error
    before, target = _definition(source), _definition(canonical)
    differences = [{"field": field, "source": before[field], "canonical": target[field]}
                   for field in (*FIELDS, "reward_items", "skill_tags") if before[field] != target[field]]
    cooperative = differences == [{"field": "is_cooperative", "source": False, "canonical": True}]
    if cooperative and source.is_repeatable:
        raise ContentPackError("A repeating personal promise cannot transition to cooperative offers in this workflow.")
    if differences and not cooperative:
        raise ContentPackError("The definitions differ in saved rules, rewards or presentation; reconcile only equivalent promises.")
    preservation = list(PRESERVATION)
    if cooperative:
        preservation.append("Future offers require parent assignment to at least two children. Saved personal one-time versions remain individual promises and cannot receive a second shared reward.")
    global_plan = {"source_definition": before, "canonical_definition": target, "differences": differences,
                   "requires_cooperative_acknowledgement": cooperative, "preservation": preservation}
    state = _digest({"definitions": list(QuestDefinition.objects.filter(pk__in=ids).order_by("pk").values()),
                     "global_plan": global_plan, "claims": claims, "overrides": overrides,
                     "binding": _digest(bindings)})
    return global_plan, state, bindings


def _inputs(source_id, canonical_id):
    _id(source_id)
    _id(canonical_id)
    if source_id == canonical_id:
        raise ContentPackError("Source and canonical definitions must be different.")
    return _digest({"operation": OPERATION, "source_definition_id": source_id,
                    "canonical_definition_id": canonical_id})


@transaction.atomic
def preview_reconciliation(actor, source_definition_id, canonical_definition_id, client_request_id):
    content = _inputs(source_definition_id, canonical_definition_id)
    request_id = _uuid(client_request_id)
    _mutex()
    existing = ContentPackPublication.objects.filter(pk=request_id).exists()
    # An immutable response recovery never discovers/locks later household use.
    ids = () if existing else (source_definition_id, canonical_definition_id)
    with _authorized(actor, ids) as (fresh, bindings, members, families):
        if existing:
            receipt = _receipt(fresh, request_id)
            if receipt.content_digest != content:
                raise ReconciliationConflict("This request UUID already identifies another reconciliation.")
            return deepcopy(receipt.stats["preview_response"])
        _catalog_lock()
        plan, state, _ = _plan(fresh, source_definition_id, canonical_definition_id, bindings, members, families)
        expires = timezone.now() + timedelta(minutes=30)
        projection = {"preview_id": str(request_id), "content_digest": content, "state_digest": state,
                      "expires_at": expires.isoformat(), "published_at": None,
                      "acknowledged_cooperative_transition": False, **plan}
        ContentPackPublication.objects.create(pk=request_id, pack=f"qa-{request_id.hex}", actor=fresh,
            family_id=fresh.family_id, content_digest=content, state_digest=state, changes=[],
            stats={"operation": OPERATION, "preview_response": projection}, expires_at=expires)
        return deepcopy(projection)


@transaction.atomic
def get_reconciliation(actor, preview_id):
    preview_id = _uuid(preview_id)
    with _authorized(actor) as (fresh, *_):
        receipt = _receipt(fresh, preview_id)
        return deepcopy(receipt.stats.get("published_response", receipt.stats["preview_response"]))


def _open_saved_one_time_windows(source_id, bindings):
    # Enrollment can precede a one-time goal's start (an earlier non-matching
    # activity), leaving its accepted window unopened. Retirement opens no new
    # windows, so save each source window before linking or superseding, as
    # list_goals would; an ended one remains available to repaired facts.
    from .goals import _occurrence
    now = timezone.now()
    goals = (ChallengeGoal.objects.filter(pk__in=[row[0] for row in bindings if row[3] == source_id],
                                          repeat_weekly=False, repeat_days=0)
             .exclude(occurrences__isnull=False).order_by("pk"))
    for goal in goals:
        _occurrence(goal, max(goal.starts_at, now))


@transaction.atomic
def publish_reconciliation(actor, preview_id, content_digest, acknowledge_cooperative_transition=False):
    preview_id = _uuid(preview_id)
    if type(acknowledge_cooperative_transition) is not bool:
        raise ContentPackError("Cooperative transition acknowledgement must be an explicit boolean.")
    _mutex()
    # Only read the stored global selections here; all authority is checked
    # again under family/user locks before using or returning this receipt.
    stored = ContentPackPublication.objects.filter(pk=preview_id, actor_id=actor.pk,
                                                   family_id=actor.family_id).first()
    plan = stored.stats.get("preview_response", {}) if stored else {}
    ids = tuple(plan.get(key, {}).get("id") for key in ("source_definition", "canonical_definition"))
    valid_ids = (() if stored and stored.published_at else
                 tuple(value for value in ids if type(value) is int and value > 0))
    with _authorized(actor, valid_ids) as (fresh, bindings, members, families):
        # Ordinary content publication takes catalog before receipt locks. A
        # scoped unlocked inspection enables early replay without reversing
        # that order for a new publication of this shared receipt model.
        receipt = _receipt(fresh, preview_id, lock=False)
        if not isinstance(content_digest, str) or receipt.content_digest != content_digest:
            raise ReconciliationConflict("Content digest does not match the reviewed reconciliation.")
        original = receipt.stats["preview_response"]
        if original["requires_cooperative_acknowledgement"] and not acknowledge_cooperative_transition:
            raise ContentPackError("Explicitly acknowledge the transition from personal to cooperative future offers.")
        if receipt.published_at:
            return deepcopy(receipt.stats["published_response"])
        if receipt.expires_at <= timezone.now():
            raise ReconciliationConflict("Reconciliation preview expired; preview it again.")
        _catalog_lock()
        receipt = _receipt(fresh, preview_id)
        if (receipt.content_digest != content_digest or receipt.published_at
                or receipt.expires_at <= timezone.now()
                or receipt.stats["preview_response"] != original):
            raise ReconciliationConflict("Reviewed reconciliation changed; retrieve or preview it again.")
        current, state, bindings = _plan(fresh, *ids, bindings, members, families)
        if state != receipt.state_digest or any(current[key] != original[key] for key in current):
            raise ReconciliationConflict("Catalog or saved identities changed; preview this reconciliation again.")
        # All relevant users precede this point in the lock order. Never add
        # an unanticipated account lock while holding the catalog prefix.
        list(ChallengeGoal.objects.select_for_update(no_key=True).filter(pk__in=[row[0] for row in bindings])
             .order_by("pk").values_list("pk", flat=True))
        source_id, canonical_id = ids
        _open_saved_one_time_windows(source_id, bindings)
        canonical_users = {row[1] for row in bindings if row[3] == canonical_id}
        for pk, user_id, _, definition_id, _, _ in bindings:
            if definition_id == source_id and user_id not in canonical_users:
                ChallengeGoal.objects.filter(pk=pk).update(catalog_definition_id=canonical_id)
                canonical_users.add(user_id)
        QuestDefinition.objects.filter(pk=source_id).update(superseded_by_id=canonical_id)
        published_at = timezone.now()
        result = deepcopy(original)
        result["source_definition"]["superseded_by_id"] = canonical_id
        result.update(published_at=published_at.isoformat(),
                      acknowledged_cooperative_transition=acknowledge_cooperative_transition)
        receipt.published_at = published_at
        receipt.stats = {**receipt.stats, "published_response": result}
        receipt.save(update_fields=["stats", "published_at", "updated_at"])
        return deepcopy(result)
