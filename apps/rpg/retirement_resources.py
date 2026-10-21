"""Settle existing resources before the exact unused-content rows are removed.

This is retirement compensation, not an expedition claim or new reward event.
The caller must own an atomic transaction and delete the selected obsolete
receipts before committing it. No game-loop, boost, badge or activity hooks run.
"""
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.pets.models import MountExpedition, PetIncubation
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rpg.inventory import grant_item
from apps.rpg.models import ItemDefinition, UserInventory


RETURN_MARKER = "unused_catalog_ingredient_return_v1"
COSMETIC_TYPES = {
    ItemDefinition.ItemType.COSMETIC_FRAME, ItemDefinition.ItemType.COSMETIC_TITLE,
    ItemDefinition.ItemType.COSMETIC_THEME, ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
}


class RetirementResourceError(ValueError):
    """A malformed persisted receipt cannot safely be settled and deleted."""


def _ids(values):
    result = set(values)
    if any(type(value) is not int or value <= 0 for value in result):
        raise RetirementResourceError("Retirement resource IDs must be positive integers.")
    return result


def collect_retirement_resource_user_ids(*, redemption_ids=(), incubation_ids=(), mount_ids=()):
    """Read exact affected users so orchestration can lock them before catalog.

    Recheck candidates after the catalog lock. A new affected user must cause
    the caller to roll back rather than invert the normal user-first locks.
    """
    return (
        set(RewardRedemption.objects.filter(pk__in=_ids(redemption_ids)).values_list("user_id", flat=True))
        | set(PetIncubation.objects.filter(pk__in=_ids(incubation_ids)).values_list("user_id", flat=True))
        | set(MountExpedition.objects.filter(mount_id__in=_ids(mount_ids)).values_list("mount__user_id", flat=True))
    )


def _credit(user_id, amount, reason, description, *, redemption=None, source=""):
    # CoinService intentionally emits activity and may apply a current buff.
    # Retirement restores only the recorded resource, with its ordinary typed
    # ledger attribution and no new completion/effort signal.
    return CoinLedger.objects.create(
        user_id=user_id, amount=amount, reason=reason, description=description,
        redemption=redemption, source=source,
    )


def _expedition_loot(expedition):
    loot = expedition.loot
    if not isinstance(loot, dict):
        raise RetirementResourceError(f"Expedition {expedition.pk} has malformed saved loot.")
    coins, slots = loot.get("coins", 0), loot.get("items", [])
    if type(coins) is not int or coins < 0 or not isinstance(slots, list):
        raise RetirementResourceError(f"Expedition {expedition.pk} has malformed saved loot.")
    for slot in slots:
        if (not isinstance(slot, dict) or type(slot.get("item_id")) is not int or slot["item_id"] <= 0
                or type(slot.get("quantity", 1)) is not int or slot.get("quantity", 1) <= 0):
            raise RetirementResourceError(f"Expedition {expedition.pk} has a malformed saved item slot.")
    return coins, slots


def settle_retirement_resources(*, redemption_ids=(), incubation_ids=(), mount_ids=(), retired_item_ids=()):
    """Refund net holds and settle accepted ingredients/loot exactly once.

    Inputs are exact IDs selected by the retirement owner, never policy-driven
    discovery. The receipt status/marker and all grants share the caller's
    transaction with deletion. A nested savepoint also prevents partial grants
    if validation fails before the caller handles the expected hold.
    """
    if not connection.in_atomic_block:
        raise RetirementResourceError("Retirement resource settlement requires an outer atomic transaction.")
    redemption_ids, incubation_ids, mount_ids, retired_item_ids = map(
        _ids, (redemption_ids, incubation_ids, mount_ids, retired_item_ids),
    )
    with transaction.atomic():
        users = {
            user.pk: user for user in get_user_model().objects.select_for_update(no_key=True).filter(
                pk__in=collect_retirement_resource_user_ids(
                    redemption_ids=redemption_ids, incubation_ids=incubation_ids, mount_ids=mount_ids,
                ),
            ).order_by("pk")
        }
        report = {"refunds": [], "redemption_cancellations": [], "ingredient_returns": [], "potion_returns": [], "expeditions": []}

        for receipt in RewardRedemption.objects.select_for_update().filter(pk__in=redemption_ids).order_by("pk"):
            if receipt.status not in {RewardRedemption.Status.PENDING, RewardRedemption.Status.APPROVED} or receipt.delivered_at is not None:
                continue
            # A price is not evidence of a debit: synthetic or migrated rows
            # without an actual hold receive no invented currency. Partial and
            # earlier refunds reduce only this same user's recorded debit.
            ledger = CoinLedger.objects.filter(redemption=receipt, user_id=receipt.user_id)
            spent = -(ledger.filter(reason=CoinLedger.Reason.REDEMPTION, amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0)
            refunded = ledger.filter(reason=CoinLedger.Reason.REFUND, amount__gt=0).aggregate(total=Sum("amount"))["total"] or 0
            held = max(0, spent - refunded)
            if held:
                entry = _credit(receipt.user_id, held, CoinLedger.Reason.REFUND,
                                f"Unused catalog retirement refund: redemption {receipt.pk}", redemption=receipt)
                report["refunds"].append({"redemption_id": receipt.pk, "user_id": receipt.user_id,
                                          "coins": held, "ledger_id": entry.pk})
            # Match ordinary rejection's reserved-stock restoration. The
            # receiving offer may survive after its frozen item changed.
            if receipt.stock_reserved:
                Reward.objects.filter(pk=receipt.reward_id, stock__isnull=False).update(stock=F("stock") + 1)
            RewardRedemption.objects.filter(pk=receipt.pk).update(status=RewardRedemption.Status.CANCELED, stock_reserved=False)
            report["redemption_cancellations"].append(receipt.pk)

        for incubation in PetIncubation.objects.select_for_update().filter(pk__in=incubation_ids).order_by("pk"):
            if incubation.hatched_at is not None or incubation.pet_id is not None:
                continue
            pair = incubation.accepted_pair
            if not isinstance(pair, dict):
                raise RetirementResourceError(f"Incubation {incubation.pk} has a malformed accepted pair.")
            returned = pair.get(RETURN_MARKER, {})
            if not isinstance(returned, dict):
                raise RetirementResourceError(f"Incubation {incubation.pk} has a malformed ingredient-return marker.")
            for kind, value in returned.items():
                if (kind not in {"egg", "potion"} or not isinstance(value, dict)
                        or type(value.get("item_id")) is not int
                        or value["item_id"] != getattr(incubation, f"{kind}_item_id") or value.get("quantity") != 1):
                    raise RetirementResourceError(f"Incubation {incubation.pk} has a mismatched ingredient-return marker.")
            marker = dict(returned)
            for kind, item_id, binding in (
                ("egg", incubation.egg_item_id, {"pet_species_id": incubation.species_id}),
                ("potion", incubation.potion_item_id, {"potion_type_id": incubation.potion_type_id}),
            ):
                if item_id is None or item_id in retired_item_ids or kind in marker:
                    continue
                snapshot = pair.get(kind)
                if (not isinstance(snapshot, dict) or type(snapshot.get("id")) is not int
                        or snapshot["id"] != item_id or snapshot.get("item_type", kind) != kind):
                    raise RetirementResourceError(f"Incubation {incubation.pk} has no matching consumed-{kind} receipt.")
                item = ItemDefinition.objects.filter(pk=item_id, item_type=kind, **binding).first()
                if item is None or (snapshot.get("slug") is not None and snapshot["slug"] != item.slug):
                    raise RetirementResourceError(f"Incubation {incubation.pk} has a changed consumed-{kind} identity.")
                grant_item(users[incubation.user_id], item, 1)
                marker[kind] = {"item_id": item.pk, "quantity": 1}
                returned_item = {"incubation_id": incubation.pk, "user_id": incubation.user_id,
                                 "item_id": item.pk, "item_type": kind, "quantity": 1}
                report["ingredient_returns"].append(returned_item)
                if kind == "potion":
                    report["potion_returns"].append(returned_item)
            if marker != returned:
                PetIncubation.objects.filter(pk=incubation.pk).update(accepted_pair={**pair, RETURN_MARKER: marker})

        expeditions = MountExpedition.objects.select_for_update(of=("self",)).filter(
            mount_id__in=mount_ids, status=MountExpedition.Status.ACTIVE, claimed_at__isnull=True,
        ).select_related("mount").order_by("pk")
        for expedition in expeditions:
            coins, slots = _expedition_loot(expedition)
            user = users[expedition.mount.user_id]
            settled = {"expedition_id": expedition.pk, "user_id": user.pk, "coins": coins,
                       "items": [], "salvage_coins": 0, "missing_item_ids": []}
            if coins:
                _credit(user.pk, coins, CoinLedger.Reason.EXPEDITION,
                        f"Unused catalog retirement: expedition {expedition.pk}", source=CoinLedger.Source.EXPEDITION)
            saved_slots = []
            for slot in slots:
                saved_slot = dict(slot)
                saved_slots.append(saved_slot)
                if slot["item_id"] in retired_item_ids:
                    continue
                item = ItemDefinition.objects.filter(pk=slot["item_id"]).first()
                if item is None:
                    settled["missing_item_ids"].append(slot["item_id"])
                    continue
                quantity = slot.get("quantity", 1)
                if item.item_type in COSMETIC_TYPES and item.coin_value > 0 and UserInventory.objects.filter(user=user, item=item).exists():
                    # This is exactly the normal claim's deterministic dupe
                    # salvage rule, including one item value per saved slot.
                    _credit(user.pk, item.coin_value, CoinLedger.Reason.ADJUSTMENT,
                            f"Unused catalog retirement salvage: expedition {expedition.pk}", source=CoinLedger.Source.EXPEDITION_SALVAGE)
                    settled["salvage_coins"] += item.coin_value
                    saved_slot["salvaged_to_coins"] = item.coin_value
                else:
                    grant_item(user, item, quantity)
                    settled["items"].append({"item_id": item.pk, "quantity": quantity})
            MountExpedition.objects.filter(pk=expedition.pk).update(
                status=MountExpedition.Status.CLAIMED, claimed_at=timezone.now(),
                loot={**expedition.loot, "items": saved_slots},
            )
            report["expeditions"].append(settled)
        return report
