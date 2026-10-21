"""Exact, expiring content plans and transactional publication receipts.

Previews exercise the real loader inside a rollback. Publication requires the
same actor, family, source bytes, catalog state and reviewed field-level diff.
"""
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import yaml

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from .loader import ContentPack, ContentPackError, FILES

CATALOG_MODELS = (
    "achievements.SkillCategory", "achievements.Subject", "achievements.Skill",
    "achievements.SkillPrerequisite", "achievements.Badge", "pets.PotionType",
    "pets.PetSpecies", "rpg.ItemDefinition", "rpg.DropTable", "quests.QuestDefinition",
    "quests.QuestRewardItem", "quests.QuestSkillTag", "rewards.Reward",
)
IGNORED_FIELDS = {"id", "created_at", "updated_at"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), cls=DjangoJSONEncoder).encode()).hexdigest()


def _read_source(path):
    inventory = {}
    parsed = {}
    for section, filename in FILES.items():
        file = Path(path) / filename
        if file.exists():
            if file.is_symlink() or not file.is_file():
                raise ContentPackError("Pack files must be ordinary files inside the pack directory.")
            if file.stat().st_size > 200000:
                raise ContentPackError("Pack file exceeds 200 KB.")
            data = file.read_bytes()
            inventory[filename] = hashlib.sha256(data).hexdigest()
            try:
                value = yaml.safe_load(data) or {}
            except yaml.YAMLError as error:
                raise ContentPackError(f"Invalid YAML in {filename}.") from error
            if not isinstance(value, dict):
                raise ContentPackError(f"{filename} must contain an object.")
            parsed[section] = value
    if not inventory:
        raise ContentPackError("Pack contains no content files.")
    return _digest(inventory), parsed


def _source_digest(path):
    return _read_source(path)[0]


def _models():
    models = [apps.get_model(name) for name in CATALOG_MODELS]
    models.append(apps.get_model("pets.PetSpecies").available_potions.through)
    return models


def _snapshot(family, *, lock=False):
    from apps.rpg.models import ContentPackEntry
    from django.db.models import Q
    visible_ownership = ContentPackEntry.objects.filter(~Q(model_label="rewards.reward") | Q(family=family))
    owners = {(e.model_label, e.object_id): f"{e.pack}/{e.kind}/{e.key}"
              for e in visible_ownership}
    models = _models()
    objects = {}
    for model in models:
        qs = model.objects.all()
        if model._meta.label_lower == "rewards.reward":
            qs = qs.filter(family=family)
        elif model._meta.label_lower == "quests.questdefinition":
            qs = qs.filter(is_system=True)
        elif model._meta.label_lower in {"quests.questrewarditem", "quests.questskilltag"}:
            qs = qs.filter(quest_definition__is_system=True)
        if lock:
            # Catalog table locks already serialize writes. Avoid blocking the
            # KEY SHARE checks performed when accepted work grants inventory.
            qs = qs.select_for_update(no_key=True)
        objects[model._meta.label_lower] = {o.pk: o for o in qs.order_by("pk")}

    def identity(model, pk):
        label = model._meta.label_lower
        if (label, pk) in owners:
            return owners[label, pk]
        obj = objects.get(label, {}).get(pk)
        if obj is None:
            return pk
        relations = [f for f in model._meta.concrete_fields if f.is_relation]
        if relations and not any(f.name in {"slug", "name"} for f in model._meta.concrete_fields):
            natural = {f.name: identity(f.remote_field.model, getattr(obj, f.attname)) for f in relations}
            if hasattr(obj, "trigger_type"):
                natural["trigger_type"] = obj.trigger_type
            return _digest(natural)
        return f"existing:{pk}"

    snapshot = {}
    for model in models:
        label = model._meta.label_lower
        for pk, obj in objects[label].items():
            values = {}
            for field in model._meta.concrete_fields:
                if field.primary_key or field.name in IGNORED_FIELDS:
                    continue
                value = getattr(obj, field.attname)
                if field.is_relation and value is not None:
                    value = identity(field.remote_field.model, value)
                if hasattr(value, "name"):
                    value = value.name
                values[field.name] = value
            key = f"{label}:{identity(model, pk)}"
            if key in snapshot:
                raise ContentPackError(f"Ambiguous duplicate catalog identity in {label}; reconcile it before publication.")
            snapshot[key] = json.loads(json.dumps(values, cls=DjangoJSONEncoder))
    # Include ownership changes even when row values are identical.
    snapshot["publication:ownership"] = sorted(
        [{"pack": e.pack, "kind": e.kind, "key": e.key, "model": e.model_label}
         for e in visible_ownership], key=lambda row: json.dumps(row, sort_keys=True))
    return snapshot


def _state_digest(snapshot):
    from apps.rpg.models import ContentPackEntry
    ownership = list(ContentPackEntry.objects.order_by("pack", "kind", "key").values(
        "pack", "family_id", "kind", "key", "model_label", "object_id"))
    return _digest({"catalog": snapshot, "ownership_bindings": ownership})


def _diff(before, after):
    changes = []
    for key in sorted(set(before) | set(after)):
        # Ownership remains in the private state binding. A full ownership
        # inventory is not part of another family's reviewable content diff.
        if key == "publication:ownership":
            continue
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        changes.append({"object": key, "action": "create" if old is None else "remove" if new is None else "update",
                        "before": old, "after": new})
    return changes


def _actor(actor, pack):
    if actor.role != "parent" or not actor.is_staff or actor.family_id is None:
        raise ContentPackError("Content publication requires a staff parent with an explicit family.")
    from apps.rpg.models import ContentPackEntry, ContentPackPublication
    if (ContentPackPublication.objects.filter(pack=pack).exclude(family=actor.family).exists()
            or ContentPackEntry.objects.filter(pack=pack).exclude(family=actor.family).exists()):
        raise ContentPackError("Pack is owned by another family; choose a new pack identity.")


def _catalog_lock():
    # Serialize competing pack publications, including creation of new rows.
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [584680271])
            # Row locks cannot prevent a legacy writer inserting a new natural
            # key after the state check. Lock the bounded catalog tables against
            # concurrent writes, including writers outside this publication path.
            from apps.rpg.models import ContentPackEntry
            tables = sorted({model._meta.db_table for model in [*_models(), ContentPackEntry]})
            cursor.execute("LOCK TABLE " + ", ".join(connection.ops.quote_name(table) for table in tables)
                           + " IN SHARE ROW EXCLUSIVE MODE")
            # Admission readers share every current category in this same PK
            # order. Take the writer prefix AFTER catalog-table admission but
            # BEFORE any target rows: raw loaders may otherwise update HIGH
            # then LOW in YAML order, opposite a reader's category scan.
            # NO KEY UPDATE keeps ordinary saved-reference FK checks compatible.
            category = apps.get_model("achievements.SkillCategory")
            table = connection.ops.quote_name(category._meta.db_table)
            key = connection.ops.quote_name(category._meta.pk.column)
            cursor.execute(f"SELECT {key} FROM {table} ORDER BY {key} FOR NO KEY UPDATE")
            cursor.fetchall()


def _run(path, pack, actor, parsed):
    loader = ContentPack(path, namespace=f"{pack}-", pack_key=pack, family=actor.family, parsed_content=parsed)
    stats = asdict(loader.load())
    return stats


def receipt_payload(receipt):
    return {"dry_run": receipt.published_at is None, **receipt.stats, "preview_id": str(receipt.pk), "pack": receipt.pack,
            "family_id": receipt.family_id, "content_digest": receipt.content_digest,
            "state_digest": receipt.state_digest, "expires_at": receipt.expires_at.isoformat(),
            "published_at": receipt.published_at.isoformat() if receipt.published_at else None,
            "changes": receipt.changes, "stats": receipt.stats,
            "retention_policy": "Removed offers retire; saved definitions, ownership and accepted promises remain."}


@transaction.atomic
def preview_content_pack(path, pack, actor):
    from apps.rpg.models import ContentPackPublication
    _catalog_lock()
    _actor(actor, pack)
    source, parsed = _read_source(path)
    before = _snapshot(actor.family, lock=True)
    with transaction.atomic():
        stats = _run(path, pack, actor, parsed)
        after = _snapshot(actor.family)
        transaction.set_rollback(True)
    if _source_digest(path) != source:
        raise ContentPackError("Pack source changed during preview; preview it again.")
    changes = _diff(before, after)
    if len(json.dumps(changes, cls=DjangoJSONEncoder)) > 2000000:
        raise ContentPackError("Publication plan exceeds 2 MB; split the content pack.")
    receipt = ContentPackPublication.objects.create(pack=pack, actor=actor, family=actor.family,
        content_digest=source, state_digest=_state_digest(before), changes=changes, stats=stats,
        expires_at=timezone.now() + timedelta(minutes=30))
    return receipt_payload(receipt)


@transaction.atomic
def publish_content_pack(path, pack, actor, preview_id, content_digest):
    from apps.rpg.models import ContentPackPublication
    _catalog_lock()
    _actor(actor, pack)
    try:
        receipt = ContentPackPublication.objects.select_for_update().get(pk=preview_id, actor=actor, family=actor.family, pack=pack)
    except (ContentPackPublication.DoesNotExist, ValueError, TypeError):
        raise ContentPackError("Publication preview not found for this actor, family and pack.") from None
    if receipt.content_digest != content_digest:
        raise ContentPackError("Content digest does not match the reviewed preview.")
    if receipt.published_at:
        return receipt_payload(receipt)
    if receipt.expires_at <= timezone.now():
        raise ContentPackError("Publication preview expired; preview it again.")
    source, parsed = _read_source(path)
    if source != receipt.content_digest:
        raise ContentPackError("Pack source changed; preview it again.")
    before = _snapshot(actor.family, lock=True)
    if _state_digest(before) != receipt.state_digest:
        raise ContentPackError("Catalog state changed; preview it again.")
    stats = _run(path, pack, actor, parsed)
    changes = _diff(before, _snapshot(actor.family))
    if changes != receipt.changes or stats != receipt.stats or _source_digest(path) != receipt.content_digest:
        raise ContentPackError("Publication no longer matches the reviewed field changes; preview it again.")
    receipt.published_at = timezone.now()
    receipt.save(update_fields=["published_at", "updated_at"])
    return receipt_payload(receipt)
