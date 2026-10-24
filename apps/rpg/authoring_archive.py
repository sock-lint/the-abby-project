"""Reversible organization of private authoring work, never runtime retirement."""
import hashlib
import json
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.families.models import Family
from apps.rpg.content.errors import ContentAuthorPermissionDenied, ContentObjectNotFound
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.workbench_validation import require_actor
from apps.rpg.models import AuthoringArchiveReceipt, ProgressionExperiment, RPGContentDraft, RPGEditorialDraft


MAX_ARCHIVED = 100
KINDS = {"content": (RPGContentDraft, 30), "editorial": (RPGEditorialDraft, 30),
         "experiment": (ProgressionExperiment, 20)}


class AuthoringArchiveConflict(ContentPackError):
    pass


class AuthoringArchiveRequestConflict(AuthoringArchiveConflict):
    pass


def locked_author(actor):
    """Call within atomic, before catalog/authoring row locks.

    The shared Family -> user order serializes capacity and membership changes
    with native and MCP authoring, without holding locks through simulations.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Authoring authority requires an atomic transaction.")
    family = Family.objects.select_for_update(no_key=True).filter(pk=actor.family_id).first()
    fresh = get_user_model().objects.select_for_update(no_key=True).filter(pk=actor.pk).first()
    if family is None or fresh is None or fresh.family_id != actor.family_id:
        raise ContentAuthorPermissionDenied("The author is no longer available in this family.")
    require_actor(fresh)
    return fresh


def _model(kind):
    if kind not in KINDS:
        raise ContentPackError("Choose content, editorial or experiment authoring work.")
    return KINDS[kind]


def ensure_active_capacity(kind, actor, *, limit=None):
    model, default_limit = _model(kind)
    limit = default_limit if limit is None else limit
    rows = model.objects.filter(actor=actor, family_id=actor.family_id, is_archived=False)
    if kind != "experiment":
        rows = rows.filter(published_at__isnull=True)
    if rows.count() >= limit:
        raise ContentPackError(f"Active {kind} capacity is {limit}; archive another unfinished record before continuing.")


def require_writable(row):
    if row.is_archived:
        raise AuthoringArchiveConflict("This record is archived and read-only. Restore it before making changes.")


def _payload(kind, row, receipt, *, replayed):
    return {"kind": kind, "id": str(row.pk), "is_archived": row.is_archived,
            "revision": row.revision, "published_at": (row.published_at.isoformat()
                if kind != "experiment" and row.published_at else None),
            "request_id": str(receipt.request_id), "replayed": replayed,
            "operation": {"is_archived": receipt.result_is_archived, "revision": receipt.result_revision}}


@transaction.atomic
def set_archived(actor, kind, object_id, revision, is_archived, request_id, *, confirmation=False):
    """Replay an operation receipt without reapplying an old archive/restore.

    Current state and original operation metadata are deliberately separate:
    replaying archive after a later restore must never archive the record again.
    Receipts retain no draft, report or household observation payloads.
    """
    if confirmation is not True:
        raise ContentPackError("Explicit confirmation is required to archive or restore authoring work.")
    if type(revision) is not int or revision < 1 or type(is_archived) is not bool:
        raise ContentPackError("Supply a positive revision and a boolean is_archived.")
    try:
        object_id, request_id = UUID(str(object_id)), UUID(str(request_id))
    except (ValueError, TypeError, AttributeError):
        raise ContentPackError("Supply valid object and request UUIDs.") from None
    actor = locked_author(actor)
    model, _ = _model(kind)
    digest = hashlib.sha256(json.dumps({"id": str(object_id), "revision": revision,
        "is_archived": is_archived}, sort_keys=True).encode()).hexdigest()
    receipt = AuthoringArchiveReceipt.objects.filter(actor=actor, kind=kind, request_id=request_id).first()
    if receipt and (receipt.family_id != actor.family_id or receipt.request_digest != digest):
        raise AuthoringArchiveRequestConflict("This request UUID was already used with different details or family.")
    row = model.objects.select_for_update().filter(pk=object_id, actor=actor, family_id=actor.family_id).first()
    if row is None:
        raise ContentObjectNotFound("Authoring record not found for this author and family.")
    if receipt:
        return _payload(kind, row, receipt, replayed=True)
    if row.revision != revision:
        raise AuthoringArchiveConflict("Record revision changed; reload it before archiving or restoring.")
    if row.is_archived != is_archived:
        if is_archived:
            if model.objects.filter(actor=actor, family_id=actor.family_id, is_archived=True).count() >= MAX_ARCHIVED:
                raise AuthoringArchiveConflict(f"Archived {kind} retention is limited to {MAX_ARCHIVED}. Restore retained work or seek an explicit retention review; nothing was deleted.")
        elif kind == "experiment" or row.published_at is None:
            try:
                ensure_active_capacity(kind, actor)
            except ContentPackError as error:
                raise AuthoringArchiveConflict(str(error)) from error
        row.is_archived = is_archived
        row.revision += 1
        row.save(update_fields=["is_archived", "revision", "updated_at"])
    receipt = AuthoringArchiveReceipt.objects.create(actor=actor, family_id=actor.family_id, kind=kind,
        request_id=request_id, object_id=row.pk, request_digest=digest,
        result_revision=row.revision, result_is_archived=is_archived)
    return _payload(kind, row, receipt, replayed=False)


@transaction.atomic
def list_authoring(actor, kind, *, include_archived=False, after=None, limit=30, published=None):
    """Bounded UUID pages of summaries; exact reads retain full private evidence."""
    actor = locked_author(actor)
    model, _ = _model(kind)
    if type(include_archived) is not bool or type(limit) is not int or not 1 <= limit <= 100:
        raise ContentPackError("Choose a boolean include_archived and a limit from 1 to 100.")
    rows = model.objects.filter(actor=actor, family_id=actor.family_id)
    if not include_archived:
        rows = rows.filter(is_archived=False)
    if published is not None and kind != "experiment":
        rows = rows.filter(published_at__isnull=not published)
    total = rows.count()
    if after:
        try:
            rows = rows.filter(pk__gt=UUID(str(after)))
        except (ValueError, TypeError, AttributeError):
            raise ContentPackError("Supply a valid after UUID.") from None
    fields = ["id", "name", "revision", "is_archived", "updated_at"]
    if kind == "editorial":
        rows = rows.annotate(has_preview=~Q(preview={}))
        fields += ["section", "published_at", "has_preview"]
    elif kind == "content":
        fields.append("published_at")
    else:
        fields.append("hypothesis")
    selected = list(rows.order_by("pk").values(*fields)[:limit + 1])
    more = len(selected) > limit
    selected = selected[:limit]
    for row in selected:
        row["id"] = str(row["id"])
        row["updated_at"] = row["updated_at"].isoformat()
        if "published_at" in row:
            row["published_at"] = row["published_at"].isoformat() if row["published_at"] else None
    return {"rows": selected, "total": total, "has_more": more,
            "next_after": selected[-1]["id"] if more else None}
