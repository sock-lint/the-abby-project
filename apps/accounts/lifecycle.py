"""Account departure and family closure, with authorization checked under locks.

The family lock is the lifecycle serialization boundary. Member-management
writers use the same family → members → request credential order. Private
journals are deleted with their author, never handed to a successor.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import DatabaseError, connections, models, transaction
from django.db.models import Q
from django.db.models.deletion import Collector, ProtectedError, RestrictedError
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException, AuthenticationFailed, PermissionDenied, ValidationError

from apps.activity.models import ActivityEvent
from apps.families.models import Family


class LifecycleConflict(APIException):
    status_code = 409
    default_detail = "This account has inconsistent family links. Contact support before deleting it."
    default_code = "lifecycle_conflict"


class LifecycleBusy(APIException):
    status_code = 409
    default_detail = "Family work is being saved. Wait for it to finish, then review and retry."
    default_code = "lifecycle_busy"


@contextmanager
def _dependent_deletion_work(using):
    # Existing approval/completion services lock their work row before the
    # award user's row. We already hold members, so never wait in the opposite
    # order. A savepoint restores transaction usability before returning 409.
    try:
        with transaction.atomic(using=using):
            yield connections[using].features.has_select_for_update_nowait
    except DatabaseError as exc:
        cause = exc.__cause__
        if (getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)) == "55P03":
            raise LifecycleBusy() from None
        raise


@contextmanager
def locked_family_members(request, *, require_token=True):
    """Yield ``(family, fresh_actor, members)`` inside the lifecycle transaction.

    A request authenticated before logout, rotation, deactivation, or deletion
    cannot carry its old authorization through a wait for this lock. NO KEY
    UPDATE lets unrelated FK checks complete without taking a stronger user
    lock before a concurrent notification writer can finish.
    """
    User = get_user_model()
    with transaction.atomic():
        try:
            family = Family.objects.select_for_update(no_key=True).get(pk=request.user.family_id)
        except Family.DoesNotExist:
            raise AuthenticationFailed("Your account is no longer available.")
        members = list(User.objects.select_for_update(no_key=True).filter(family=family).order_by("pk"))
        actor = next((member for member in members if member.pk == request.user.pk), None)
        if actor is None or not actor.is_active:
            raise AuthenticationFailed("Your account is no longer available.")
        credential = request.auth
        if credential is None and not require_token:
            pass  # Existing internal/test callers may use a forced user.
        elif not isinstance(credential, Token) or not Token.objects.select_for_update().filter(
                key=credential.key, user_id=actor.pk,
            ).exists():
            raise AuthenticationFailed("Your sign-in has changed. Sign in again.")
        yield family, actor, members


def require_parent(actor):
    if actor.role != "parent":
        raise PermissionDenied("Parents only.")


def require_current_password(actor, password):
    # Do not use authenticate(): a wrong confirmation is a form error, not a
    # signal for clients to discard an otherwise valid authenticated session.
    if not actor.has_usable_password() or not actor.check_password(password):
        raise ValidationError({"password": "Enter your current password. If you do not have one, ask for a password reset first."})


def _successor(actor, members, successor_id):
    successor = next((
        member for member in members
        if member.pk == successor_id and member.pk != actor.pk
        and member.role == "parent" and member.is_active
    ), None)
    if successor is None:
        raise ValidationError({"successor_id": "Choose another active parent in your family."})
    return successor


def _shared_work(actor):
    """Only author pointers change; personal assignment/ownership never does."""
    from apps.chores.models import Chore
    from apps.habits.models import Habit
    from apps.homework.models import HomeworkAssignment, HomeworkTemplate
    from apps.projects.models import Project, ProjectTemplate

    if actor.role != "parent":
        return {}
    return {
        "projects": Project.objects.filter(created_by=actor).exclude(assigned_to=actor).filter(
            Q(assigned_to__isnull=True) | Q(assigned_to__family_id=actor.family_id),
        ),
        "project_templates": ProjectTemplate.objects.filter(created_by=actor, family_id=actor.family_id),
        "homework_assignments": HomeworkAssignment.objects.filter(
            created_by=actor, assigned_to__family_id=actor.family_id,
        ).exclude(assigned_to=actor),
        "homework_templates": HomeworkTemplate.objects.filter(created_by=actor),
        "chores": Chore.objects.filter(created_by=actor, family_id=actor.family_id).exclude(assigned_to=actor),
        "habits": Habit.objects.filter(created_by=actor, user__family_id=actor.family_id).exclude(user=actor),
    }


def lifecycle_preview(family, actor, members):
    successors = [member for member in members if member.pk != actor.pk and member.role == "parent" and member.is_active]
    shared = _shared_work(actor)
    return {
        "user": {"id": actor.pk, "username": actor.username},
        "family": {"id": family.pk, "name": family.name, "slug": family.slug, "primary_parent_id": family.primary_parent_id},
        "family_members": {
            "parents": sum(member.role == "parent" for member in members),
            "children": sum(member.role == "child" for member in members),
        },
        "family_version": family_review_version(family, members),
        "successors": [{"id": member.pk, "display_name": member.display_label} for member in successors] if actor.role == "parent" else [],
        "shared_work": {name: shared[name].count() if name in shared else 0 for name in (
            "projects", "project_templates", "homework_assignments", "homework_templates", "chores", "habits",
        )},
        "can_delete_account": actor.role == "child" or bool(successors),
        "can_close_family": actor.role == "parent" and not successors,
    }


def family_review_version(family, members):
    """Review freshness, not authorization or a secret: bind closure to members."""
    state = [family.pk, family.primary_parent_id, [
        [member.pk, member.role, member.is_active] for member in sorted(members, key=lambda member: member.pk)
    ]]
    return hashlib.sha256(json.dumps(state, separators=(",", ":")).encode()).hexdigest()


@lru_cache(maxsize=None)
def _has_family_owner(model, seen=frozenset()):
    """Distinguish household records from global catalogs with SET_NULL authors."""
    if model in {get_user_model(), Family}:
        return True
    if model in seen:
        return False
    seen = seen | {model}
    return any(
        isinstance(field, (models.ForeignKey, models.OneToOneField))
        and field.remote_field.on_delete in {models.CASCADE, models.RESTRICT, models.PROTECT}
        and _has_family_owner(field.related_model, seen)
        for field in model._meta.concrete_fields
    )


def _assert_object_family(obj, family_id, checked):
    identity = (type(obj), obj.pk)
    if identity in checked:
        return
    checked.add(identity)
    if isinstance(obj, Family):
        if obj.pk != family_id:
            raise LifecycleConflict()
    elif isinstance(obj, get_user_model()):
        if obj.family_id != family_id:
            raise LifecycleConflict()
        return
    # Follow ownership links, including SET_NULL links on an owned record.
    # A catalog's optional creator does not make its global content private.
    for field in obj._meta.concrete_fields:
        if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
            continue
        if getattr(obj, field.attname) is None or not _has_family_owner(field.related_model):
            continue
        if field.related_model._meta.label_lower == "oauth2_provider.application":
            # A grant's client registration may legitimately serve unrelated
            # families. Deleting the grant does not change that registration.
            # If a departing user owns the client itself, Collector includes
            # it and all affected grants; their user ownership is still checked.
            continue
        # FK descriptors cache only on each individual row. Consult the
        # traversal's validated identities before fetching a repeated parent,
        # so years of ledger/history rows do not each SELECT the same user.
        # A non-PK to_field cannot be compared to our primary-key identities.
        if field.target_field.primary_key and (
            field.related_model, getattr(obj, field.attname),
        ) in checked:
            continue
        related = getattr(obj, field.name)
        _assert_object_family(related, family_id, checked)


def collect_safe_deletion(instance, family):
    """Preflight the actual cascade and nullable updates, failing closed.

    A malformed old/imported link must not let account deletion remove or
    modify a different household's records. Fast-delete querysets need this
    check too; they are not included in Collector.data. This check reveals no
    object IDs, private body text, storage paths, or credential material.
    """
    collector = Collector(using=instance._state.db or "default")
    try:
        collector.collect([instance])
    except (ProtectedError, RestrictedError):
        raise LifecycleConflict() from None
    checked = set()
    groups = [(model, model.objects.filter(pk__in=[obj.pk for obj in rows])) for model, rows in collector.data.items()]
    groups.extend((query.model, query) for query in collector.fast_deletes)
    for (field, _value), batches in collector.field_updates.items():
        if field.model is ActivityEvent or not _has_family_owner(field.model):
            continue
        for batch in batches:
            query = batch if isinstance(batch, models.QuerySet) else field.model.objects.filter(pk__in=[obj.pk for obj in batch])
            groups.append((field.model, query))
    with _dependent_deletion_work(collector.using) as nowait:
        for model, query in sorted(groups, key=lambda item: item[0]._meta.label_lower):
            for obj in query.select_for_update(no_key=True, nowait=nowait).order_by("pk"):
                _assert_object_family(obj, family.pk, checked)
    return collector


def delete_related_activity(collector, users):
    """Remove linked household activity; redact mixed-household anomalies.

    Unattributed text with no surviving structural link cannot safely be
    identified by matching names. It remains subject to operational retention.
    """
    user_ids = [user.pk for user in users]
    family_id = users[0].family_id
    events = [ActivityEvent.objects.filter(Q(actor_id__in=user_ids) | Q(subject_id__in=user_ids))]
    # Work in per-model batches rather than a giant OR expression/parameter list.
    groups = [(model, model.objects.filter(pk__in=[obj.pk for obj in rows])) for model, rows in collector.data.items()]
    groups.extend((query.model, query) for query in collector.fast_deletes)
    # Deletion must not create metadata for models that have never had a
    # generic activity target. Resolve existing types in one read, without
    # warming Django's process cache with rows a rollback could discard.
    content_types = {
        (app_label, model): pk for app_label, model, pk
        in ContentType.objects.values_list("app_label", "model", "pk")
    }
    for model, query in groups:
        if not isinstance(model._meta.pk, models.IntegerField):
            continue
        concrete = model._meta.concrete_model._meta
        ct_id = content_types.get((concrete.app_label, concrete.model_name))
        if ct_id is not None:
            events.append(ActivityEvent.objects.filter(target_ct_id=ct_id, target_id__in=query.values("pk")))
    deletions, redactions = [], []
    redacted_fields = (
        "summary", "context", "correlation_id", "target_ct", "target_id",
        "event_type", "category", "coins_delta", "money_delta", "xp_delta", "actor", "subject",
    )

    def flush_activity_batch():
        if deletions:
            ActivityEvent.objects.filter(pk__in=deletions).delete()
            deletions.clear()
        if redactions:
            ActivityEvent.objects.bulk_update(redactions, redacted_fields, batch_size=100)
            redactions.clear()

    with _dependent_deletion_work(collector.using) as nowait:
        for query in events:
            for event in query.select_for_update(of=("self",), nowait=nowait).select_related("actor", "subject").order_by("pk"):
                if any(user is not None and user.family_id != family_id for user in (event.actor, event.subject)):
                    # Preserve the other household's row identity/attribution,
                    # while removing text and pointers linked to this departure.
                    event.summary = "Account activity removed"
                    event.context = {}
                    event.correlation_id = None
                    event.target_ct = None
                    event.target_id = None
                    event.event_type = "account.removed"
                    event.category = ActivityEvent.Category.SYSTEM
                    event.coins_delta = event.money_delta = event.xp_delta = None
                    if event.actor_id in user_ids:
                        event.actor = None
                    if event.subject_id in user_ids:
                        event.subject = None
                    redactions.append(event)
                else:
                    deletions.append(event.pk)
                # The selected rows remain locked through the surrounding
                # transaction. Bulk writes retain the same privacy decisions
                # without a network round trip for every historical event.
                if len(deletions) >= 500 or len(redactions) >= 100:
                    flush_activity_batch()
            flush_activity_batch()


def transfer_contact(family, actor, members, *, password, successor_id):
    require_parent(actor)
    require_current_password(actor, password)
    successor = _successor(actor, members, successor_id)
    family.primary_parent = successor
    family.save(update_fields=["primary_parent"])


def delete_self(family, actor, members, *, password, confirm_username, successor_id=None):
    require_current_password(actor, password)
    if confirm_username != actor.username:
        raise ValidationError({"confirm_username": "Type your username exactly to confirm account deletion."})
    successor = _successor(actor, members, successor_id) if actor.role == "parent" else None
    # Check before transfer so a malformed creator/assignee link cannot be
    # hidden by handing its author pointer to a different parent.
    collect_safe_deletion(actor, family)
    if successor is not None:
        for query in _shared_work(actor).values():
            query.update(created_by=successor)
        if family.primary_parent_id == actor.pk:
            family.primary_parent = successor
            family.save(update_fields=["primary_parent"])
    collector = collect_safe_deletion(actor, family)
    delete_related_activity(collector, [actor])
    actor.delete()


def close_family(family, actor, members, *, password, confirm_family_slug, family_version):
    require_parent(actor)
    require_current_password(actor, password)
    if confirm_family_slug != family.slug:
        raise ValidationError({"confirm_family_slug": "Type the family identifier exactly to confirm family closure."})
    if family_version != family_review_version(family, members):
        raise LifecycleConflict("Your family changed after this review. Reload and review its members before closing it.")
    if any(member.pk != actor.pk and member.role == "parent" and member.is_active for member in members):
        raise ValidationError({"detail": "Other active parents remain. Each must leave or be deactivated before the last parent can close the family."})
    collector = collect_safe_deletion(family, family)
    delete_related_activity(collector, members)
    family.delete()
