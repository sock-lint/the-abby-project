"""Private database drafts and exact evaluated publication over the live catalog.

YAML remains the shipped baseline. Explicitly published overrides preserve the
selected database identities and take precedence when that baseline is loaded.
"""
from copy import deepcopy
from contextlib import nullcontext
from datetime import timedelta
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.mcp_server.catalog import audit_catalog_rows, catalog_queryset, catalog_row
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.quests.reward_items import freeze_legacy_quest_promises
from apps.rpg.authoring_archive import ensure_active_capacity, locked_author, require_writable
from apps.rpg.models import ContentPackEntry, ContentPackPublication, ItemDefinition, RPGContentDraft, RPGContentOverride

from .loader import ContentPack, ContentPackError, LoadStats
from .publication import _catalog_lock, _diff, _digest, _snapshot, _state_digest, receipt_payload
from .workbench_validation import (
    CREATE_ITEM_TYPES, ITEM_BEHAVIOR_FIELDS, ITEM_FIELDS, MODELS, QUEST_FIELDS, challenge_trigger_findings,
    challenge_trigger_status, editable_object, require_actor, supported_challenge_triggers,
    validate_changes, validate_item_runtime,
)


class WorkbenchConflict(ContentPackError):
    """A previously reviewed revision no longer grants publication authority."""


class WorkbenchNotFound(ContentPackError):
    """Keep another author's private draft indistinguishable from a missing one."""


def _draft(actor, draft_id, *, lock=False):
    require_actor(actor)
    queryset = RPGContentDraft.objects.select_related("preview")
    if lock:
        # Nullable joined preview rows cannot be included in PostgreSQL's lock.
        queryset = queryset.select_for_update(of=("self",))
    try:
        return queryset.get(pk=draft_id, actor=actor, family_id=actor.family_id)
    except (RPGContentDraft.DoesNotExist, ValidationError, ValueError, TypeError):
        raise WorkbenchNotFound("Content draft not found for this actor and family.") from None


def _revision(draft, revision, *, writable=True):
    require_writable(draft)
    if type(revision) is not int or revision != draft.revision:
        raise WorkbenchConflict("Draft revision changed; reload the draft before continuing.")
    if writable and draft.published_at:
        raise WorkbenchConflict("This draft is published; create a new draft for further changes.")


def draft_payload(draft):
    plan = receipt_payload(draft.preview) if draft.preview_id else None
    if plan:
        plan["audits"] = draft.preview.stats.get("audits", {"findings": [], "incomplete": False})
    return {"id": str(draft.pk), "name": draft.name, "revision": draft.revision, "is_archived": draft.is_archived, "changes": deepcopy(draft.changes),
            "preview": plan, "simulation": deepcopy(draft.simulation) or None,
            "published_at": draft.published_at.isoformat() if draft.published_at else None,
            "updated_at": draft.updated_at.isoformat()}


@transaction.atomic
def get_draft(actor, draft_id):
    actor = locked_author(actor)
    return draft_payload(_draft(actor, draft_id))


@transaction.atomic
def create_draft(actor, name):
    actor = locked_author(actor)
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ContentPackError("Draft name must be nonempty text of at most 100 characters.")
    ensure_active_capacity("content", actor)
    return draft_payload(RPGContentDraft.objects.create(actor=actor, family=actor.family, name=name.strip()))


@transaction.atomic
def save_draft(actor, draft_id, revision, changes, *, name=None):
    actor = locked_author(actor)
    draft = _draft(actor, draft_id, lock=True)
    _revision(draft, revision)
    validate_changes(actor, changes)
    if name is not None:
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ContentPackError("Draft name must be nonempty text of at most 100 characters.")
        draft.name = name.strip()
    draft.changes = deepcopy(changes)
    draft.revision += 1
    draft.preview = None
    draft.simulation = {}
    draft.save(update_fields=["name", "changes", "revision", "preview", "simulation", "updated_at"])
    return draft_payload(draft)


def _pack(draft):
    return f"wb-{draft.pk.hex}"


def _source(draft, *, revision=None):
    return _digest({"draft": str(draft.pk), "revision": draft.revision if revision is None else revision,
                    "changes": draft.changes})


def _state(snapshot):
    overrides = list(RPGContentOverride.objects.order_by("pk").values(
        "model_label", "object_id", "family_id", "source_lookup", "values"))
    return _digest({"catalog_state": _state_digest(snapshot), "database_overrides": overrides})


def _values(section, obj):
    if section == "items":
        return {field: deepcopy(getattr(obj, field)) for field in ITEM_FIELDS}
    references = {"required_badge", "prerequisite_quest", "required_skill"}
    result = {field: deepcopy(getattr(obj, field)) for field in QUEST_FIELDS - references - {"reward_items", "skill_tags"}}
    result.update({field: getattr(obj, field + "_id") for field in references})
    result["reward_items"] = [{"item_id": r.item_id, "quantity": r.quantity}
                              for r in sorted(obj.reward_items.all(), key=lambda row: row.item_id)]
    result["skill_tags"] = [{"skill_id": tag.skill_id, "xp_weight": tag.xp_weight}
                           for tag in sorted(obj.skill_tags.all(), key=lambda row: row.skill_id)]
    return result


def _protect_legacy(obj, values):
    """Reuse the publication guard without translating exact IDs into names."""
    defaults = {field: value for field, value in values.items()
                if field not in {"reward_items", "skill_tags", "required_badge"}}
    if "required_badge" in values:
        defaults["required_badge"] = values["required_badge"]
    # The shared guard compares scalar promised rules. Tags use exact IDs here.
    guard = ContentPack.__new__(ContentPack)
    guard.stats = LoadStats()
    guard._protect_active_quest(obj, defaults, {})
    if "skill_tags" in values and obj.instances.filter(status="active").exists():
        current = sorted(obj.skill_tags.values_list("skill_id", "xp_weight"))
        proposed = sorted((row["skill_id"], row.get("xp_weight", 1)) for row in values["skill_tags"])
        if current != proposed:
            raise ContentPackError("Cannot change skill_tags while active legacy quests retain these rules and rewards.")


def _apply(draft, *, publication=None):
    """The exact same bounded writers run inside preview rollback and publish."""
    validate_changes(draft.actor, draft.changes, lock=True)
    changes = sorted(draft.changes, key=lambda c: (c["section"] != "items", c["key"]))
    quest_ids = [c["object_id"] for c in changes if c["section"] == "quests" and c["object_id"]]
    # Freeze accepted presentation before a display edit. Existing item behavior
    # is immutable here; a new version receives its own inventory identity.
    item_ids = [c["object_id"] for c in changes if c["section"] == "items" and c["object_id"]]
    quest_ids += list(QuestRewardItem.objects.filter(item_id__in=item_ids).values_list("quest_definition_id", flat=True))
    frozen = freeze_legacy_quest_promises(definition_ids=quest_ids)
    stats = {"created": {}, "updated": {}, "skipped": {"accepted_promises_preserved": len(frozen)}, "retired": {}}
    new_items, result = {}, []
    for change in changes:
        section, values = change["section"], deepcopy(change["values"])
        model = MODELS[section]
        obj = editable_object(draft.actor, section, change["object_id"]) if change["object_id"] else model()
        existing = obj.pk is not None
        lookup = {"slug": obj.slug} if section == "items" else {"name": obj.name}
        if section == "quests" and existing:
            _protect_legacy(obj, values)
            if "name" in values and values["name"] != obj.name:
                from apps.achievements.models import Badge
                for badge in Badge.objects.filter(criteria_type="quest_completed"):
                    criteria = badge.criteria_value if isinstance(badge.criteria_value, dict) else {}
                    names = criteria.get("quest_names") or [criteria.get("quest_name")]
                    if obj.name in names:
                        raise ContentPackError("A badge refers to this challenge by name; retain its name or author a new challenge version.")
        for field, value in values.items():
            if field in {"reward_items", "skill_tags"}:
                continue
            setattr(obj, field + "_id" if field in {"required_badge", "prerequisite_quest", "required_skill"} else field, value)
        if not obj.icon:
            obj.icon = "🎁" if section == "items" else "⚔️"
        if section == "quests":
            obj.is_system = True
            # A quest name is also used by authored badge conditions. Retain
            # explicit IDs, refuse collisions, and surface named dependencies.
            if obj.superseded_by_id:
                raise ContentPackError("This challenge identity is a retained alias; edit its canonical definition.")
            from .authoring import validate_source_identity
            # Earlier changes in this same draft may have just retained a
            # source identity that was not present during preflight.
            validate_source_identity(obj)
            if QuestDefinition.objects.filter(name=obj.name, superseded_by__isnull=True).exclude(pk=obj.pk).exists():
                raise ContentPackError("Challenge name collides with existing content; choose a distinct name.")
        else:
            validate_item_runtime(obj)
        try:
            obj.full_clean()
        except ValidationError as error:
            raise ContentPackError("; ".join(error.messages)) from error
        obj.save()
        if not existing:
            ContentPackEntry.objects.create(pack=_pack(draft), family=draft.family,
                kind=model._meta.model_name, key=change["key"], model_label=model._meta.label_lower, object_id=obj.pk)
            if section == "items":
                new_items[change["key"]] = obj
        if section == "quests":
            if "reward_items" in values:
                desired = []
                for row in values["reward_items"]:
                    item_id = row.get("item_id") or new_items[row["item_key"]].pk
                    desired.append(item_id)
                    QuestRewardItem.objects.update_or_create(quest_definition=obj, item_id=item_id,
                        defaults={"quantity": row.get("quantity", 1)})
                deleted, _ = obj.reward_items.exclude(item_id__in=desired).delete()
                if deleted:
                    stats["retired"]["quest_reward"] = stats["retired"].get("quest_reward", 0) + deleted
            if "skill_tags" in values:
                obj.skill_tags.all().delete()
                QuestSkillTag.objects.bulk_create([QuestSkillTag(quest_definition=obj, skill_id=row["skill_id"],
                    xp_weight=row.get("xp_weight", 1)) for row in values["skill_tags"]])
        if not existing:
            lookup = {"slug": obj.slug} if section == "items" else {"name": obj.name}
        prior = RPGContentOverride.objects.filter(model_label=model._meta.label_lower, object_id=obj.pk).first()
        RPGContentOverride.objects.update_or_create(model_label=model._meta.label_lower, object_id=obj.pk,
            defaults={"family": draft.family, "source_lookup": prior.source_lookup if prior else lookup,
                      "values": _values(section, obj), "publication": publication})
        bucket = stats["updated" if existing else "created"]
        bucket[section] = bucket.get(section, 0) + 1
        result.append((section, obj.pk, change["key"]))
    findings = []
    for section in MODELS:
        ids = [pk for selected, pk, _ in result if selected == section]
        rows = list(catalog_queryset(section).filter(pk__in=ids).order_by("pk"))
        found, _ = audit_catalog_rows(section, rows)
        if section == "quests":
            found.extend(challenge_trigger_findings(rows))
        keys = {pk: key for selected, pk, key in result if selected == section}
        for finding in found:
            finding["draft_key"] = keys[finding["id"]]
        findings.extend(found)
    stats["audits"] = {"findings": findings, "incomplete": False}
    # Errors in existing untouched rows remain visible in the catalog audit;
    # this editor cannot publish new broken reward links or unknown effects.
    if any(row["severity"] == "error" for row in findings):
        raise ContentPackError("Draft audit failed: " + "; ".join(row["detail"] for row in findings if row["severity"] == "error"))
    return stats


@transaction.atomic
def preview_draft(actor, draft_id, revision):
    actor = locked_author(actor)
    _catalog_lock()
    draft = _draft(actor, draft_id, lock=True)
    _revision(draft, revision)
    if not draft.changes:
        raise ContentPackError("Add at least one item or challenge change before previewing.")
    before = _snapshot(actor.family, lock=True)
    state = _state(before)
    with transaction.atomic():
        stats = _apply(draft)
        changes = _diff(before, _snapshot(actor.family))
        transaction.set_rollback(True)
    if len(json.dumps(changes)) > 2000000:
        raise ContentPackError("Publication plan exceeds 2 MB; split the draft.")
    receipt = ContentPackPublication.objects.create(pack=_pack(draft), actor=actor, family=actor.family,
        content_digest=_source(draft), state_digest=state, changes=changes, stats=stats,
        expires_at=timezone.now() + timedelta(minutes=30))
    draft.preview = receipt
    draft.simulation = {}
    draft.save(update_fields=["preview", "simulation", "updated_at"])
    return draft_payload(draft)


def _reviewed(draft, preview_id, *, content_digest=None, published_revision=None):
    plan = draft.preview
    if plan is None or str(plan.pk) != str(preview_id) or plan.actor_id != draft.actor_id or plan.family_id != draft.family_id:
        raise WorkbenchConflict("Publication preview not found for this draft, actor and family.")
    if content_digest is not None and content_digest != plan.content_digest:
        raise WorkbenchConflict("Content digest does not match the reviewed preview.")
    if published_revision is not None and not (draft.published_at and plan.published_at):
        raise WorkbenchConflict("Only a completed publication may use its original preview revision.")
    if _source(draft, revision=published_revision) != plan.content_digest:
        raise WorkbenchConflict("Draft content changed; preview it again.")
    if not plan.published_at and plan.expires_at <= timezone.now():
        raise WorkbenchConflict("Publication preview expired; preview it again.")
    return plan


def _current(draft, plan):
    before = _snapshot(draft.family, lock=True)
    if _state(before) != plan.state_digest:
        raise WorkbenchConflict("Catalog state changed; preview and simulate the draft again.")
    return before


def _same_plan(stats, changes, plan):
    # New rows receive fresh PostgreSQL sequence values after preview rollback;
    # only audit identity hints use those transient IDs. The reviewed diff uses
    # stable authoring claims for every new row and relation instead.
    def stable_stats(value):
        result = deepcopy(value)
        for finding in result.get("audits", {}).get("findings", []):
            finding.pop("id", None)
        return result
    if changes != plan.changes or stable_stats(stats) != stable_stats(plan.stats):
        raise WorkbenchConflict("Publication no longer matches the reviewed changes; preview it again.")


def simulate_draft(actor, draft_id, revision, preview_id, config=None, *, authorize=None):
    from apps.rpg.progression import normalize_config, simulate_progression
    from apps.rpg.progression.catalog import snapshot_catalog
    from apps.rpg.progression.engine import pet_incubation_policy
    config = normalize_config(config)
    incubation_policy = pet_incubation_policy()
    # Snapshot only global definitions while serialized against publication.
    # Roll back every candidate write before running either bounded simulation.
    # Transports may need fresh household/member authority. Reacquire it for
    # each short database phase, before catalog admission, never around the
    # detached calculation. An outer atomic would retain PostgreSQL locks even
    # after these inner blocks exit.
    with (authorize() if authorize else nullcontext(actor)) as current_actor, transaction.atomic():
        current_actor = locked_author(current_actor)
        _catalog_lock()
        draft = _draft(current_actor, draft_id, lock=True)
        _revision(draft, revision)
        plan = _reviewed(draft, preview_id)
        before = _current(draft, plan)
        baseline = snapshot_catalog()
        with transaction.atomic():
            stats = _apply(draft)
            _same_plan(stats, _diff(before, _snapshot(draft.family)), plan)
            proposed = snapshot_catalog()
            transaction.set_rollback(True)
    comparison = {"baseline": simulate_progression(config, catalog=baseline, incubation_policy=incubation_policy),
                  "proposed": simulate_progression(config, catalog=proposed, incubation_policy=incubation_policy)}
    with (authorize() if authorize else nullcontext(actor)) as current_actor, transaction.atomic():
        current_actor = locked_author(current_actor)
        _catalog_lock()
        draft = _draft(current_actor, draft_id, lock=True)
        _revision(draft, revision)
        plan = _reviewed(draft, preview_id)
        _current(draft, plan)
        draft.simulation = {"preview_id": str(plan.pk), "revision": draft.revision, "content_digest": plan.content_digest,
            "config_digest": _digest(config), "baseline_fingerprint": baseline.fingerprint,
            "proposed_fingerprint": proposed.fingerprint, "completed_at": timezone.now().isoformat(),
            "rules_fingerprint": comparison["proposed"]["rules_fingerprint"],
            "engine_version": comparison["proposed"]["engine_version"]}
        draft.save(update_fields=["simulation", "updated_at"])
    return {**comparison, "preview_id": str(plan.pk), "revision": draft.revision, "simulation": draft.simulation}


@transaction.atomic
def publish_draft(actor, draft_id, revision, preview_id, content_digest):
    actor = locked_author(actor)
    _catalog_lock()
    draft = _draft(actor, draft_id, lock=True)
    if draft.published_at:
        # Archive/restore changes organization and its revision, not the
        # completed publication. Prove the exact original operation before
        # returning its current saved state; never apply catalog changes here.
        if type(revision) is not int or revision < 1:
            raise WorkbenchConflict("Supply the original reviewed publication revision.")
        _reviewed(draft, preview_id, content_digest=content_digest, published_revision=revision)
        return draft_payload(draft)
    _revision(draft, revision, writable=False)
    plan = _reviewed(draft, preview_id, content_digest=content_digest)
    before = _current(draft, plan)
    expected = {"preview_id": str(plan.pk), "revision": draft.revision, "content_digest": plan.content_digest}
    if any(draft.simulation.get(key) != value for key, value in expected.items()):
        raise WorkbenchConflict("Simulate this exact reviewed draft before publishing it.")
    from apps.rpg.progression.engine import ENGINE_VERSION, rules_fingerprint
    if (draft.simulation.get("rules_fingerprint") != rules_fingerprint()
            or draft.simulation.get("engine_version") != ENGINE_VERSION):
        raise WorkbenchConflict("Simulation rules changed; simulate this reviewed draft again before publication.")
    stats = _apply(draft, publication=plan)
    _same_plan(stats, _diff(before, _snapshot(actor.family)), plan)
    plan.published_at = timezone.now()
    plan.save(update_fields=["published_at", "updated_at"])
    draft.published_at = plan.published_at
    draft.save(update_fields=["published_at", "updated_at"])
    return draft_payload(draft)


def preserved_loader_entry(model_label, lookup, *, pack_key=None, entry=None):
    """Honor explicit database authoring when a shipped pack is loaded again.

    No JSON is written back to YAML. Exact pack claims or the originally
    reviewed natural key select the persisted identity; names never adopt rows.
    """
    overrides = RPGContentOverride.objects.filter(model_label=model_label)
    if pack_key:
        kind = model_label.split(".", 1)[1]
        ids = ContentPackEntry.objects.filter(pack=pack_key, kind=kind).values_list("object_id", flat=True)
        overrides = overrides.filter(object_id__in=ids)
    for override in overrides:
        matched = override.source_lookup == lookup
        if pack_key and entry and entry.get("id"):
            matched = matched or ContentPackEntry.objects.filter(pack=pack_key, model_label=model_label,
                    object_id=override.object_id, key=entry["id"]).exists()
        # Also recognize a bundle brought up to date with the published name.
        matched = matched or ("name" in lookup and override.values.get("name") == lookup["name"])
        if matched:
            from django.apps import apps
            if not apps.get_model(model_label).objects.filter(pk=override.object_id).exists():
                # An intentionally deleted baseline row must not prevent app
                # startup. Retain this exact orphan as historical evidence;
                # never apply it to the replacement or silently move its claim.
                # Pack-owned missing identities still fail in _upsert's guard.
                continue
            return override
    return None


def _bounded_rows(section, limit):
    queryset = catalog_queryset(section)
    if section == "skills":
        queryset = queryset.select_related("category")
    rows = list(queryset.order_by("pk")[:limit + 1])
    if len(rows) > limit:
        raise ContentPackError(f"The {section} catalog exceeds the editor limit ({limit}); use a paged catalog audit.")
    return rows


def describe_workbench(actor):
    from apps.rpg.progression import describe_progression
    from apps.rewards.models import Reward
    require_actor(actor)
    rows = {section: _bounded_rows(section, limit) for section, limit in
            (("items", 4096), ("quests", 256), ("skills", 2048), ("badges", 512))}
    claims = {(row.model_label, row.object_id): row.family_id for row in ContentPackEntry.objects.all()}
    overrides = {(row.model_label, row.object_id): row.family_id for row in RPGContentOverride.objects.all()}
    quest_uses, drop_uses, shop_uses = {}, {}, {}
    for quest in rows["quests"]:
        for reward in quest.reward_items.all():
            quest_uses.setdefault(reward.item_id, []).append({"id": quest.pk, "name": quest.name, "quantity": reward.quantity})
    drops = _bounded_rows("drops", 16384)
    for drop in drops:
        drop_uses.setdefault(drop.item_id, []).append({"id": drop.pk, "trigger_type": drop.trigger_type,
            "weight": drop.weight, "min_level": drop.min_level})
    offers = list(Reward.objects.filter(family=actor.family, item_definition_id__isnull=False).order_by("pk")[:4097])
    if len(offers) > 4096:
        raise ContentPackError("The family shop exceeds the editor limit (4096).")
    for offer in offers:
        shop_uses.setdefault(offer.item_definition_id, []).append({"id": offer.pk, "name": offer.name,
            "cost_coins": offer.cost_coins, "is_active": offer.is_active})
    catalog, findings, any_incomplete = {}, [], False
    for section, objects in rows.items():
        catalog[section] = []
        for obj in objects:
            data = catalog_row(section, obj)
            if section in MODELS:
                key = (obj._meta.label_lower, obj.pk)
                editable = all(mapping.get(key, actor.family_id) == actor.family_id for mapping in (claims, overrides))
                data.update({"editable": editable, "edit_reason": "" if editable else "Authored by another family.",
                             "values": _values(section, obj), "has_database_override": key in overrides})
                if section == "items":
                    data["used_by"] = {"quests": quest_uses.get(obj.pk, []), "drops": drop_uses.get(obj.pk, []),
                                       "shop_offers": shop_uses.get(obj.pk, [])}
                else:
                    status = challenge_trigger_status(obj.quest_type, obj.trigger_filter)
                    data["automatic_tracking_available"] = status["available"]
                    data["unsupported_triggers"] = status["unsupported"]
                    data["available_for_new_user"] = data["available_for_new_user"] and status["available"]
            if section == "skills":
                data["category_name"] = obj.category.name
            catalog[section].append(data)
        found, incomplete = audit_catalog_rows(section, objects)
        if section == "quests":
            found.extend(challenge_trigger_findings(objects))
        findings.extend(found)
        any_incomplete = any_incomplete or incomplete
    drafts = RPGContentDraft.objects.filter(actor=actor, family=actor.family, is_archived=False).only(
        "id", "name", "revision", "is_archived", "published_at", "updated_at")
    visible_drafts = [*drafts.filter(published_at__isnull=True).order_by("-updated_at")[:30],
                      *drafts.filter(published_at__isnull=False).order_by("-updated_at")[:70]]
    return {"catalog": catalog,
            "rules": {"item_types": sorted(CREATE_ITEM_TYPES), "rarities": list(ItemDefinition.Rarity.values),
                "triggers": supported_challenge_triggers(), "boss_triggers": supported_challenge_triggers("boss"),
                "editable_item_fields": sorted(ITEM_FIELDS),
                "existing_item_behavior_fields": sorted(ITEM_BEHAVIOR_FIELDS),
                "editable_quest_fields": sorted(QUEST_FIELDS), "max_changes": 100,
                "publication_scope": "Published catalog changes are global; drafts are private to their author and family.",
                "storage": "Bundled YAML supplies defaults; published database overrides survive content reloads."},
            "audits": {"findings": findings, "incomplete": any_incomplete},
            "simulation": describe_progression(),
            "drafts": [{"id": str(draft.pk), "name": draft.name, "revision": draft.revision, "is_archived": draft.is_archived,
                "published_at": draft.published_at.isoformat() if draft.published_at else None,
                "updated_at": draft.updated_at.isoformat()} for draft in visible_drafts]}
