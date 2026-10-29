"""User-serialized activity credit, bounded searches and exact reward receipts."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import random
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.families.models import Family
from apps.quests.activity import household_timezone
from apps.quests.availability import RetryCatalogBusy, lock_retry_reward_catalog
from apps.rpg.inventory import grant_item
from apps.rpg.models import ItemDefinition

from .catalog import offers_for
from .engine import CATEGORIES, ordinary_complete, rare_search_capacity
from .models import DiscoveryActivityCredit, DiscoveryRequest, DiscoverySearch, EggDiscovery, PracticeSession


class DiscoveryConflict(APIException):
    status_code = 409
    default_code = "egg_discovery_conflict"


def enabled():
    return getattr(settings, "EGG_DISCOVERY_ENABLED", False) is True


def _require_enabled():
    if not enabled():
        raise DiscoveryConflict("Egg discoveries are not enabled.")


def _lock_user(user):
    return get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)


def _catalog_fence():
    # Reuse the bounded PostgreSQL SHARE/NOWAIT fence protecting ingredient
    # identities and species/potion compatibility in explicit challenge retries.
    # New acceptance reports a busy catalog. Reward delivery isolates that
    # conflict in a savepoint so ordinary source logging can still commit.
    try:
        lock_retry_reward_catalog()
    except RetryCatalogBusy as error:
        raise DiscoveryConflict(str(error)) from error


@contextmanager
def authorized_owner(requester):
    """Recheck current self authority in the account-lifecycle lock order."""
    with transaction.atomic():
        family = Family.objects.select_for_update(no_key=True).filter(pk=requester.family_id).first()
        if family is None:
            raise NotFound("Account not found.")
        owner = get_user_model().objects.select_for_update(no_key=True).filter(pk=requester.pk, family=family).first()
        if (owner is None or not owner.is_active or owner.role not in {"parent", "child"}
                or (owner.role, owner.is_staff) != (requester.role, requester.is_staff)):
            raise NotFound("Account not found.")
        owner.family = family
        yield owner


def _request(user, action, request_id, payload):
    try:
        request_id = UUID(str(request_id))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"client_request_id": ["A valid request UUID is required."]}) from None
    previous = DiscoveryRequest.objects.filter(user=user, client_request_id=request_id).first()
    if previous is not None and (previous.action != action or previous.payload != payload):
        raise DiscoveryConflict("This request was already saved with different details.")
    return request_id, previous


def discovery_payload(discovery):
    snapshot = discovery.snapshot
    searches = [{"number": search.number, "found": search.found, "guaranteed": search.guaranteed} for search in discovery.searches.all()]
    guarantee = snapshot["requirements"]["guaranteed_search"]
    found = any(search["found"] for search in searches)
    delivery_pending = discovery.status in {"active", "paused"} and discovery.reward_receipt is None and (
        ordinary_complete(discovery.minutes, snapshot["requirements"]) if snapshot["tier"] == "ordinary" else found
    )
    return {
        "id": discovery.pk, "offer_key": discovery.offer_key,
        **{key: deepcopy(snapshot[key]) for key in ("name", "tier", "egg_item", "potion_name", "season", "requirements")},
        "status": discovery.status, "minutes": {category: discovery.minutes.get(category, 0) for category in CATEGORIES},
        "searches": searches, "receipt": deepcopy(discovery.reward_receipt),
        "delivery_pending": delivery_pending,
        "remaining_searches": (0 if discovery.status == "completed" or found else max(0, guarantee - len(searches))) if guarantee else None,
        "can_resume": discovery.status == "paused", "unavailable_reason": None,
    }


def envelope(user):
    """A projection only: no acceptance, retries, rolls or reward processing."""
    if not enabled():
        return {"enabled": False, "offers": [], "discoveries": [], "active_id": None}
    rows = list(EggDiscovery.objects.filter(user=user).prefetch_related("searches"))
    return {
        "enabled": True, "offers": [offer.public() for offer in offers_for(user)],
        "discoveries": [discovery_payload(row) for row in rows],
        "active_id": next((row.pk for row in rows if row.status == "active"), None),
    }


@transaction.atomic
def select_discovery(user, *, offer_key, client_request_id):
    _require_enabled()
    user = _lock_user(user)
    request_id, previous = _request(user, "select", client_request_id, {"offer_key": offer_key})
    if previous is not None:
        return False
    saved = EggDiscovery.objects.filter(user=user, offer_key=offer_key).first()
    if saved is not None:
        if saved.status == "completed":
            raise DiscoveryConflict("You have already earned this discovery.")
        # An accepted promise remains selectable after its seasonal start
        # window or catalog availability changes. Never reprice the snapshot.
        EggDiscovery.objects.filter(user=user, status="active").exclude(pk=saved.pk).update(status="paused")
        saved.status = "active"
        saved.save(update_fields=["status", "updated_at"])
        # An explicit selection/resume may retry an already earned delivery.
        # UUID recovery above remains inert, as do ordinary catalog reads.
        _advance(saved)
    else:
        _catalog_fence()
        offer = next((offer for offer in offers_for(user) if offer.key == offer_key), None)
        if offer is None:
            raise NotFound("Egg discovery not found.")
        if offer.unavailable_reason:
            raise DiscoveryConflict(offer.unavailable_reason)
        EggDiscovery.objects.filter(user=user, status="active").update(status="paused")
        EggDiscovery.objects.create(
            user=user, offer_key=offer.key, species=offer.egg.pet_species, potion_type=offer.potion.potion_type,
            egg_item=offer.egg, potion_item=offer.potion, food_item=offer.food,
            snapshot=offer.snapshot(), minutes={category: 0 for category in CATEGORIES},
        )
    DiscoveryRequest.objects.create(user=user, client_request_id=request_id, action="select", payload={"offer_key": offer_key})
    return True


@transaction.atomic
def pause_discovery(user, *, discovery_id, client_request_id):
    _require_enabled()
    user = _lock_user(user)
    payload = {"discovery_id": discovery_id}
    request_id, previous = _request(user, "pause", client_request_id, payload)
    if previous is not None:
        return False
    saved = EggDiscovery.objects.filter(user=user, pk=discovery_id).first()
    if saved is None:
        raise NotFound("Egg discovery not found.")
    if saved.status == "completed":
        raise DiscoveryConflict("This discovery is already completed.")
    saved.status = "paused"
    saved.save(update_fields=["status", "updated_at"])
    DiscoveryRequest.objects.create(user=user, client_request_id=request_id, action="pause", payload=payload)
    return True


def _complete(discovery):
    if discovery.reward_receipt is not None:
        return
    _catalog_fence()
    # Fresh reads after admission: select_related objects loaded before the
    # fence could otherwise conceal a concurrent rebinding of an ingredient.
    catalog = ItemDefinition.objects.in_bulk([discovery.egg_item_id, discovery.potion_item_id, discovery.food_item_id])
    egg, potion, food = (catalog.get(item_id) for item_id in (discovery.egg_item_id, discovery.potion_item_id, discovery.food_item_id))
    binding = discovery.snapshot["bindings"]
    if (egg is None or potion is None or food is None or not isinstance(egg.metadata, dict) or not isinstance(potion.metadata, dict)
            or egg.item_type != "egg" or egg.pet_species_id != discovery.species_id or egg.slug != binding["egg_slug"]
            or egg.metadata.get("species") != binding["egg_species"]
            or potion.item_type != "potion" or potion.potion_type_id != discovery.potion_type_id
            or potion.slug != binding["potion_slug"] or potion.metadata.get("variant") != binding["potion_variant"]
            or food.item_type != "food"):
        raise DiscoveryConflict("An accepted reward identity changed. This discovery needs catalog repair.")
    items = {item.pk: item for item in (egg, potion, food)}
    for reward in discovery.snapshot["reward_items"]:
        grant_item(discovery.user, items[reward["item_id"]], reward["quantity"])
    discovery.status = "completed"
    discovery.completed_at = timezone.now()
    discovery.reward_receipt = {"items": deepcopy(discovery.snapshot["reward_items"])}


def _try_complete(discovery):
    """Keep earned progress when a known catalog conflict prevents delivery.

    Inventory and any inventory-badge consequences stay inside this savepoint.
    Unexpected failures keep their original strict rollback behavior; only the
    domain conflict describing unavailable/changed catalog proof is deferred.
    """
    original = (discovery.status, discovery.completed_at, discovery.reward_receipt)
    try:
        with transaction.atomic():
            _complete(discovery)
    except DiscoveryConflict:
        discovery.status, discovery.completed_at, discovery.reward_receipt = original


def _advance(discovery):
    rules = discovery.snapshot["requirements"]
    if discovery.snapshot["tier"] == "ordinary":
        if ordinary_complete(discovery.minutes, rules):
            _try_complete(discovery)
    elif discovery.searches.filter(found=True).exists():
        # A saved winning roll is final even if its supplies could not yet be
        # delivered. Later activity or explicit selection never rolls again.
        _try_complete(discovery)
    else:
        capacity = min(rare_search_capacity(discovery.minutes, rules), rules["guaranteed_search"])
        count = discovery.searches.count()
        for number in range(count + 1, capacity + 1):
            guaranteed = number == rules["guaranteed_search"]
            roll = None if guaranteed else random.random()
            found = guaranteed or roll < rules["chance_percent"] / 100
            DiscoverySearch.objects.create(discovery=discovery, number=number, guaranteed=guaranteed, roll=roll, found=found)
            if found:
                _try_complete(discovery)
                break
    discovery.save(update_fields=["minutes", "status", "completed_at", "reward_receipt", "updated_at"])


@transaction.atomic
def credit_activity(user, *, category, source_kind, source_key, minutes, occurred_on):
    """Credit a genuinely inserted source once; never scan or replay history.

    Source adapters supply immutable UUID identities, saved minutes and dates.
    Tombstones include zero-credit/no-active/historical facts so deleting a log
    cannot move its original activity into another egg. Existing source writes
    already hold their account gate; this same lock never reverses that order.
    """
    feature_enabled = enabled()
    if (category not in CATEGORIES or type(minutes) is not int or not 0 <= minutes <= 600
            or type(occurred_on) is not date or not isinstance(source_kind, str) or not 0 < len(source_kind) <= 50
            or not isinstance(source_key, str) or not 0 < len(source_key) <= 100):
        raise ValueError("A bounded saved activity identity, category, minutes and date are required.")
    user = _lock_user(user)
    previous = DiscoveryActivityCredit.objects.filter(user=user, source_kind=source_kind, source_key=source_key).first()
    if previous is not None:
        return previous
    day = timezone.localdate(timezone=household_timezone(user))
    discovery = None
    if feature_enabled and user.is_active and occurred_on == day and minutes:
        discovery = EggDiscovery.objects.filter(user=user, status="active").select_related("egg_item", "potion_item", "food_item").first()
    credit = DiscoveryActivityCredit.objects.create(
        user=user, discovery=discovery, category=category, source_kind=source_kind, source_key=source_key,
        minutes=minutes, occurred_on=occurred_on, credited_minutes=minutes if discovery else 0,
    )
    if discovery is not None:
        discovery.minutes = {key: discovery.minutes.get(key, 0) for key in CATEGORIES}
        discovery.minutes[category] += minutes
        _advance(discovery)
    return credit


@transaction.atomic
def log_practice(user, *, name, minutes, client_request_id):
    _require_enabled()
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValidationError({"name": ["Enter an activity name of at most 100 characters."]})
    if type(minutes) is not int or not 1 <= minutes <= 240:
        raise ValidationError({"minutes": ["Enter between 1 and 240 minutes."]})
    name = name.strip()
    user = _lock_user(user)
    payload = {"name": name, "minutes": minutes}
    request_id, previous = _request(user, "practice", client_request_id, payload)
    if previous is not None:
        return False
    day = timezone.localdate(timezone=household_timezone(user))
    PracticeSession.objects.create(user=user, name=name, minutes=minutes, occurred_on=day, client_request_id=request_id)
    credit_activity(user, category="practice", source_kind="practice", source_key=str(request_id), minutes=minutes, occurred_on=day)
    DiscoveryRequest.objects.create(user=user, client_request_id=request_id, action="practice", payload=payload)
    return True
