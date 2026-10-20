"""Bounded copy editing with private revisions and exact global publication.

This surface edits prose and affirmation selection. Reward rules, Lorebook
unlock conditions and interactive trial handlers remain reviewed source code.
"""
from copy import deepcopy
from datetime import timedelta
import re
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.families.models import Family
from apps.rpg.models import RPGEditorialDraft, RPGEditorialOverride

from .loader import ContentPackError
from .publication import _digest
from .workbench_validation import require_actor

SECTIONS = {"lorebook", "affirmations"}
LORE_FIELDS = {"title": 100, "audience_title": 150, "summary": 500, "kid_voice": 10000}
AFFIRMATION_FIELDS = {"text": 90, "tone": 40}


def apply_editorial_overrides(section, baseline, *, include_retired=False):
    """Overlay current database copy on cached source, without caching writes."""
    entries = {row["slug"]: deepcopy(row) for row in baseline}
    overrides = list(RPGEditorialOverride.objects.filter(section=section).order_by("pk")[:501])
    if len(overrides) > 500:
        raise ContentPackError("Editorial catalog exceeds 500 published entries.")
    for override in overrides:
        if section == "lorebook" and override.slug not in entries:
            continue  # A retired source handler cannot be recreated with prose.
        row = {**entries.get(override.slug, {"slug": override.slug}), **deepcopy(override.values)}
        row["slug"] = override.slug
        if include_retired or override.is_active:
            entries[override.slug] = row
        else:
            entries.pop(override.slug, None)
    return list(entries.values())


def _baseline(section):
    if section == "lorebook":
        from apps.lorebook.services import load_lorebook_source
        return load_lorebook_source()
    if section == "affirmations":
        from apps.wellbeing.services import _load_affirmation_source
        return _load_affirmation_source()
    raise ContentPackError("Unknown editorial section.")


def editorial_catalog(section):
    baseline = _baseline(section)
    rows = apply_editorial_overrides(section, baseline, include_retired=True)
    active = {row["slug"] for row in apply_editorial_overrides(section, baseline)}
    return [{**row, "is_active": row["slug"] in active} for row in rows]


def _lock():
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [584680272])


def _actor(actor):
    family = Family.objects.select_for_update(no_key=True).filter(pk=actor.family_id).first()
    if family is None:
        raise ContentPackError("The author family is no longer available.")
    fresh = get_user_model().objects.select_for_update(no_key=True).filter(pk=actor.pk).first()
    if fresh is None or fresh.family_id != actor.family_id:
        raise ContentPackError("The author is no longer available in this family.")
    require_actor(fresh)
    return fresh


def _draft(actor, draft_id, revision=None):
    fresh = _actor(actor)
    row = RPGEditorialDraft.objects.select_for_update().filter(pk=draft_id, actor=fresh, family_id=fresh.family_id).first()
    if row is None:
        raise ContentPackError("Editorial draft not found for this author and family.")
    if revision is not None and (type(revision) is not int or row.revision != revision):
        raise ContentPackError("Editorial draft revision changed; reload before continuing.")
    return row


def _payload(draft):
    return {"id": str(draft.pk), "section": draft.section, "name": draft.name, "revision": draft.revision,
            "changes": deepcopy(draft.changes), "preview": deepcopy(draft.preview) or None,
            "published_at": draft.published_at.isoformat() if draft.published_at else None}


@transaction.atomic
def create_editorial_draft(actor, section, name):
    actor = _actor(actor)
    if section not in SECTIONS or not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ContentPackError("Choose an editorial section and a nonempty name of at most 100 characters.")
    if RPGEditorialDraft.objects.filter(actor=actor, family=actor.family, published_at__isnull=True).count() >= 30:
        raise ContentPackError("At most 30 unpublished editorial drafts may be kept per author.")
    return _payload(RPGEditorialDraft.objects.create(actor=actor, family=actor.family, section=section, name=name.strip()))


@transaction.atomic
def get_editorial_draft(actor, draft_id):
    return _payload(_draft(actor, draft_id))


@transaction.atomic
def list_editorial_drafts(actor, *, after=None, limit=30):
    from django.db.models import Q

    actor = _actor(actor)
    rows = RPGEditorialDraft.objects.filter(actor=actor, family=actor.family).annotate(
        has_preview=~Q(preview={}),
    ).values("id", "section", "name", "revision", "published_at", "has_preview").order_by("pk")
    if after:
        rows = rows.filter(pk__gt=after)
    selected = list(rows[:limit + 1])
    more = len(selected) > limit
    selected = selected[:limit]
    return {"drafts": [{**row, "id": str(row["id"]),
                       "published_at": row["published_at"].isoformat() if row["published_at"] else None}
                      for row in selected],
            "next_after": str(selected[-1]["id"]) if more else None}


def _proposal(actor, section, changes):
    if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
        raise ContentPackError("Supply between 1 and 100 editorial changes.")
    current = {row["slug"]: row for row in editorial_catalog(section)}
    owners = {row.slug: row.family_id for row in RPGEditorialOverride.objects.filter(section=section)}
    seen, diff = set(), []
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"slug", "values"}:
            raise ContentPackError("Each editorial change requires exactly slug and values.")
        slug, values = change["slug"], change["values"]
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", slug) or slug in seen:
            raise ContentPackError("Editorial slugs must be unique bounded lowercase identities.")
        seen.add(slug)
        if slug in owners and owners[slug] != actor.family_id:
            raise ContentPackError("This editorial entry is owned by another family or needs reconciliation.")
        fields = LORE_FIELDS if section == "lorebook" else AFFIRMATION_FIELDS
        allowed = set(fields) | ({"mechanics"} if section == "lorebook" else {"is_active"})
        if not isinstance(values, dict) or not values or set(values) - allowed:
            raise ContentPackError("Only supported textual editorial fields can be changed.")
        if section == "lorebook" and slug not in current:
            raise ContentPackError("New Lorebook handlers require reviewed source; select an existing entry.")
        for field, maximum in fields.items():
            if field in values and (not isinstance(values[field], str) or not values[field].strip() or len(values[field]) > maximum):
                raise ContentPackError(f"{field} must be nonempty text of at most {maximum} characters.")
        if "text" in values and ("\n" in values["text"] or "\r" in values["text"]):
            raise ContentPackError("Affirmations must be a single line.")
        if "mechanics" in values and (not isinstance(values["mechanics"], list) or not 1 <= len(values["mechanics"]) <= 30
                or any(not isinstance(line, str) or not line.strip() or len(line) > 1000 for line in values["mechanics"])):
            raise ContentPackError("Mechanics copy requires 1 to 30 nonempty lines of at most 1000 characters.")
        if "is_active" in values and type(values["is_active"]) is not bool:
            raise ContentPackError("is_active must be a boolean.")
        before = deepcopy(current.get(slug))
        after = {**(before or {"slug": slug, "is_active": True, "tone": ""}), **deepcopy(values)}
        if section == "affirmations" and not after.get("text"):
            raise ContentPackError("A new affirmation needs text.")
        current[slug] = after
        diff.append({"slug": slug, "before": before, "after": after})
    if section == "affirmations" and not any(row["is_active"] for row in current.values()):
        raise ContentPackError("Retain at least one active affirmation.")
    if len(current) > 500:
        raise ContentPackError("Editorial catalog exceeds 500 entries.")
    return diff


def _state(section):
    return _digest({"baseline": _baseline(section), "overrides": list(RPGEditorialOverride.objects.filter(
        section=section).order_by("slug").values("slug", "family_id", "values", "is_active"))})


@transaction.atomic
def save_editorial_draft(actor, draft_id, revision, changes):
    draft = _draft(actor, draft_id, revision)
    if draft.published_at:
        raise ContentPackError("Create a new draft to revise published editorial content.")
    _proposal(actor, draft.section, changes)
    draft.changes, draft.preview = deepcopy(changes), {}
    draft.revision += 1
    draft.save(update_fields=["changes", "preview", "revision", "updated_at"])
    return _payload(draft)


@transaction.atomic
def preview_editorial_draft(actor, draft_id, revision):
    _lock()
    draft = _draft(actor, draft_id, revision)
    if draft.published_at:
        raise ContentPackError("This editorial draft is already published.")
    changes = _proposal(actor, draft.section, draft.changes)
    draft.preview = {"id": str(uuid4()), "revision": draft.revision, "changes": changes,
        "content_digest": _digest({"section": draft.section, "changes": draft.changes}),
        "state_digest": _state(draft.section), "expires_at": (timezone.now() + timedelta(minutes=30)).isoformat()}
    draft.save(update_fields=["preview", "updated_at"])
    return _payload(draft)


@transaction.atomic
def publish_editorial_draft(actor, draft_id, revision, preview_id, content_digest):
    _lock()
    draft = _draft(actor, draft_id, revision)
    plan = draft.preview
    if (not plan or plan["id"] != str(preview_id) or plan["content_digest"] != content_digest):
        raise ContentPackError("Supply this draft's exact reviewed preview and digest.")
    if draft.published_at:
        return _payload(draft)
    if parse_datetime(plan["expires_at"]) <= timezone.now() or plan["state_digest"] != _state(draft.section):
        raise ContentPackError("Editorial preview expired or catalog changed; preview again.")
    changes = _proposal(actor, draft.section, draft.changes)
    if changes != plan["changes"]:
        raise ContentPackError("Editorial content differs from the reviewed plan; preview again.")
    for change in changes:
        row, _ = RPGEditorialOverride.objects.get_or_create(section=draft.section, slug=change["slug"],
            defaults={"family": actor.family})
        authored = next(value["values"] for value in draft.changes if value["slug"] == row.slug)
        row.values = {**row.values, **{key: value for key, value in authored.items() if key != "is_active"}}
        row.is_active = change["after"]["is_active"]
        row.publication = draft
        row.save()
    draft.published_at = timezone.now()
    draft.save(update_fields=["published_at", "updated_at"])
    return _payload(draft)
