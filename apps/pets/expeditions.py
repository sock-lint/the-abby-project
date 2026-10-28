"""Mount expedition service — Finch-inspired offline play loop.

A user sends their mount on a 2/4/8h expedition. Loot (coins + 1-3 items) is
rolled at *start* and locked to the row's ``loot`` JSONField — slow-claim
users get the same payout regardless of when they tap through. On claim,
the loot is materialized into ``CoinLedger`` + ``UserInventory`` and the
single ``GameLoopService`` orchestrator is invoked with ``drops_allowed=False``
so streak/quest credit fires once without double-dipping the drop roll.

Daily cap: each child shares two expeditions per family-local day, and each
species shares one across potion appearances. The check is on ``started_at``, not ``returns_at``, so
an overnight trip uses its launch day's allowance. An unclaimed trip also
blocks other appearances until it is explicitly collected.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.quests.activity import household_timezone
from apps.rpg.coin_policy import EXPEDITION_DAILY_LIMIT, random_cosmetic_salvage_coins

logger = logging.getLogger(__name__)


# Tier definitions: duration, base coin payout, item slots.
#
# Coin scaling is roughly linear with duration but slightly favours longer
# tiers so a kid who plans ahead is rewarded for the patience. Items are
# ALSO drawn from the existing DropTable rows for the EXPEDITION_RETURNED
# trigger when present, falling back to a sensible default pool when the
# content seed hasn't authored expedition-specific tables yet.
TIER_CONFIG = {
    "short": {
        "duration_minutes": 120,   # 2h
        "base_coins": 3,
        "item_slots": 1,
        "rarity_weights": {"common": 70, "uncommon": 25, "rare": 5},
    },
    "standard": {
        "duration_minutes": 240,   # 4h
        "base_coins": 7,
        "item_slots": 2,
        "rarity_weights": {"common": 50, "uncommon": 35, "rare": 13, "epic": 2},
    },
    "long": {
        "duration_minutes": 480,   # 8h
        "base_coins": 15,
        "item_slots": 3,
        "rarity_weights": {"common": 35, "uncommon": 35, "rare": 22, "epic": 7, "legendary": 1},
    },
}


class ExpeditionError(ValueError):
    """Surface-level expedition errors — start/claim/cooldown failures."""


class ExpeditionNotFound(ExpeditionError):
    """Raised when a mount or expedition lookup fails (cross-user or stale id).

    Carved off ``ExpeditionError`` so views can branch on exception class
    instead of fragile message-prefix matching — a typo in the human-readable
    message used to silently downgrade 404 to 400 and leak existence.
    """


def expedition_day_bounds(user, as_of=None):
    """Bind launch receipts to their owner's actual family-local day."""
    zone = household_timezone(user)
    day = timezone.localdate(as_of or timezone.now(), timezone=zone)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


class ExpeditionService:
    """Lifecycle manager for ``MountExpedition`` rows."""

    @staticmethod
    @transaction.atomic
    def start(user, mount_id, tier):
        """Send a mount on an expedition. Raises ``ExpeditionError`` on failure.

        Returns the new ``MountExpedition`` row.
        """
        from apps.achievements.services import _lock_award_user
        from apps.pets.models import MountExpedition, UserMount

        if tier not in TIER_CONFIG:
            raise ExpeditionError(
                f"Unknown tier {tier!r} — must be one of {sorted(TIER_CONFIG)}"
            )

        # Different potion appearances have different mount rows. Serialize
        # them on the existing user gate before locking any mount, matching
        # care/claim lock order and making the shared species check atomic.
        _lock_award_user(user)

        try:
            mount = UserMount.objects.select_for_update().get(
                pk=mount_id, user=user,
            )
        except UserMount.DoesNotExist:
            # Typed exception — view turns this into a 404 without leaking
            # whether a mount with that pk exists in another household.
            raise ExpeditionNotFound("Mount not found")

        species_trips = MountExpedition.objects.filter(
            mount__user=user, mount__species_id=mount.species_id,
        )
        # An unclaimed trip occupies the species slot even across midnight.
        # Existing overlapping accepted trips keep their individual receipts.
        active = species_trips.filter(status=MountExpedition.Status.ACTIVE).first()
        if active is not None:
            raise ExpeditionError(
                f"{mount.species.name} is already out — "
                f"returning in {max(0, active.seconds_remaining)} seconds"
            )

        # One clock snapshot binds this allowance to the saved launch day.
        now = timezone.now()
        day_start, next_day = expedition_day_bounds(user, now)
        day_filter = {"started_at__gte": day_start, "started_at__lt": next_day}
        already_today = species_trips.filter(**day_filter).exists()
        if already_today:
            raise ExpeditionError(
                f"{mount.species.name} has already been out today — "
                "they need rest before another run"
            )

        # Existing accepted launches count toward today's allowance too; they
        # are never canceled, repriced or denied their own later claims.
        launches = MountExpedition.objects.filter(mount__user=user, **day_filter).count()
        if launches >= EXPEDITION_DAILY_LIMIT:
            raise ExpeditionError(
                f"You have used today's {EXPEDITION_DAILY_LIMIT} expedition starts — try again tomorrow"
            )

        config = TIER_CONFIG[tier]
        returns_at = now + timedelta(minutes=config["duration_minutes"])
        loot = ExpeditionService._roll_loot(user, tier)

        # Wrap the create in IntegrityError → ExpeditionError. Two concurrent
        # start calls that both pass the pre-checks collide on the partial
        # unique index; without this guard the loser raises IntegrityError
        # and surfaces as a 500. The pre-check catches the common case;
        # this catches the race.
        try:
            expedition = MountExpedition.objects.create(
                mount=mount,
                tier=tier,
                status=MountExpedition.Status.ACTIVE,
                started_at=now,
                returns_at=returns_at,
                loot=loot,
            )
        except IntegrityError as exc:
            raise ExpeditionError(
                f"{mount.species.name} is already on an expedition"
            ) from exc
        logger.info(
            "User %s sent %s on a %s expedition — returns at %s",
            user.username, mount, tier, returns_at,
        )
        return expedition

    @staticmethod
    @transaction.atomic
    def claim(user, expedition_id):
        """Materialize loot into the user's coin ledger + inventory.

        Idempotent in the harmless direction: a second claim returns the
        first claim's result without re-awarding. Raises ``ExpeditionError``
        when claimed too early or when the expedition belongs to another
        user (404-shape).

        Returns a dict suitable for the claim modal::

            {
                "expedition_id": int,
                "coins_awarded": int,
                "items": [{"item_id", "name", "icon", "rarity", "quantity"}],
                "tier": str,
                "mount": {"id", "species_name", "potion_name", ...},
            }
        """
        from apps.achievements.services import _lock_award_user
        from apps.pets.models import MountExpedition

        # Care and consumables take this gate before inventory/pet writes.
        # Take it before the receipt lock too, so a claim cannot own catalog
        # or inventory locks while waiting for a concurrent evolution.
        _lock_award_user(user)

        try:
            expedition = (
                MountExpedition.objects
                # Joined species/potions are shared by every family. Only the
                # expedition receipt needs a lock for an idempotent claim.
                .select_for_update(of=("self",))
                .select_related("mount__species", "mount__potion")
                .get(pk=expedition_id, mount__user=user)
            )
        except MountExpedition.DoesNotExist:
            # Typed exception — the view maps this to 404. Cross-user pks
            # must NEVER leak existence (the same shape we use for the
            # mount lookup above).
            raise ExpeditionNotFound("Expedition not found")

        # Already claimed: return the recorded result, no rewards.
        if expedition.status == MountExpedition.Status.CLAIMED:
            return ExpeditionService._serialize_claim_result(
                expedition, coins_awarded=0, freshly_claimed=False,
            )

        if expedition.status == MountExpedition.Status.EXPIRED:
            raise ExpeditionError("This expedition expired without being claimed")

        if not expedition.is_ready:
            raise ExpeditionError(
                f"{expedition.mount.species.name} is still out — "
                f"{max(0, expedition.seconds_remaining)} seconds to go"
            )

        # Materialize loot. ``_materialize_loot`` may annotate the loot
        # JSON in-memory (e.g. ``salvaged_to_coins``); we persist those
        # writes alongside the status transition so a re-fetch shows the
        # same shape the claim modal rendered.
        coins_awarded, loot_changed = ExpeditionService._materialize_loot(user, expedition)

        expedition.status = MountExpedition.Status.CLAIMED
        expedition.claimed_at = timezone.now()
        update_fields = ["status", "claimed_at", "updated_at"]
        if loot_changed:
            update_fields.append("loot")
        expedition.save(update_fields=update_fields)

        # Post-claim fanout runs AFTER the DB commit via ``on_commit`` so
        # a downstream rollback can never produce a "claimed" response
        # whose ledger row got reverted. Both helpers are explicitly
        # best-effort — failures log via Sentry but don't surface to
        # the caller.
        mount = expedition.mount
        expedition_pk = expedition.pk
        tier = expedition.tier
        item_count = len(expedition.loot.get("items") or [])
        display_name = user.display_name or user.username

        def _post_claim_hooks():
            try:
                from apps.rpg.services import GameLoopService
                from apps.rpg.constants import TriggerType
                GameLoopService.on_task_completed(
                    user,
                    TriggerType.EXPEDITION_RETURNED,
                    {"drops_allowed": False, "expedition_id": expedition_pk, "tier": tier},
                )
            except Exception:
                logger.exception("Game-loop hook failed in expedition claim")

            try:
                from apps.notifications.services import notify, notify_parents
                title = f"{mount.species.name} is back from an expedition!"
                msg = (
                    f"{coins_awarded} coins and {item_count} item(s) "
                    "landed in your stash."
                )
                notify(
                    user, title=title, message=msg,
                    notification_type="expedition_returned",
                    link="/bestiary?tab=mounts&space=personal" if user.role == "parent" else "/bestiary?tab=mounts",
                )
                notify_parents(
                    title=f"{display_name}'s mount returned",
                    message=msg,
                    notification_type="expedition_returned",
                    about_user=user,
                    link=f"/family?child={user.pk}" if user.role == "child" else "/bestiary?tab=mounts",
                )
            except Exception:
                logger.exception("Notification hook failed in expedition claim")

        transaction.on_commit(_post_claim_hooks)

        return ExpeditionService._serialize_claim_result(
            expedition, coins_awarded=coins_awarded, freshly_claimed=True,
        )

    @staticmethod
    def list_for_user(user, *, ready_only=False):
        """All expedition rows for the user, newest first.

        ``ready_only=True`` filters to active expeditions whose ``returns_at``
        has passed — used by the toast-stack poll to surface unclaimed loot.
        """
        from apps.pets.models import MountExpedition

        qs = (
            MountExpedition.objects
            .filter(mount__user=user)
            .select_related("mount__species", "mount__potion")
            .order_by("-started_at")
        )
        if ready_only:
            qs = qs.filter(
                status=MountExpedition.Status.ACTIVE,
                returns_at__lte=timezone.now(),
            )
        return list(qs)

    # ---------------------------------------------------------- internals --

    @staticmethod
    def _roll_loot(user, tier):
        """Pre-roll the expedition's payout. Returns the JSON-serializable shape."""
        from apps.rpg.constants import TriggerType
        from apps.rpg.models import CharacterProfile, DropTable
        from apps.rpg.catalog_support import random_item_is_available
        from apps.rpg.catalog_icons import item_catalog_icon
        from apps.rpg.coin_policy import resolve_random_pouch

        config = TIER_CONFIG[tier]

        # Coins: base × small jitter so two runs of the same tier feel slightly
        # different. Range: 0.85x – 1.15x of base, rounded to int.
        coin_jitter = 0.85 + random.random() * 0.30
        coins = max(1, int(config["base_coins"] * coin_jitter))

        # Items: pull from DropTable rows scoped to expedition_returned;
        # fall back to the union of generic-pool tables (clock_out + chore_complete)
        # if no expedition-specific entries are seeded yet.
        profile = CharacterProfile.objects.filter(user=user).first()
        user_level = profile.level if profile else 0

        entries = [entry for entry in (
            DropTable.objects
            .filter(trigger_type=TriggerType.EXPEDITION_RETURNED, min_level__lte=user_level)
            .select_related("item")
        ) if random_item_is_available(entry.item)]
        if not entries:
            # Fallback: borrow from clock_out + chore_complete pools so a
            # fresh deployment without expedition-specific drops still
            # produces the available supplies from those activity pools.
            entries = [entry for entry in (
                DropTable.objects
                .filter(
                    trigger_type__in=[
                        TriggerType.CLOCK_OUT,
                        TriggerType.CHORE_COMPLETE,
                    ],
                    min_level__lte=user_level,
                )
                .select_related("item")
            ) if random_item_is_available(entry.item)]

        items = []
        if entries:
            # Fixed tier budgets, followed by authored weights within each
            # eligible tier. Missing tiers are excluded; absent eligible tiers
            # renormalize. Pre-rolls retain their result until claim.
            from apps.rpg.companion_catalog import companion_drop_weights
            from apps.rpg.rarity import COSMETIC_TYPES, owned_cosmetic_ids, tier_balanced_weights
            authored_weights = companion_drop_weights(entries)
            owned = owned_cosmetic_ids(user)

            for _ in range(config["item_slots"]):
                biased_weights = tier_balanced_weights(entries, config["rarity_weights"],
                    authored_weights=authored_weights, owned_item_ids=owned)
                if not any(biased_weights):
                    break
                selected = random.choices(entries, weights=biased_weights, k=1)[0]
                item = resolve_random_pouch(selected.item)
                if item.item_type in COSMETIC_TYPES:
                    owned.add(item.pk)
                slot = {
                    "item_id": item.pk,
                    "quantity": 1,
                    # Snapshot display fields so the loot row reads
                    # the same even if the item is renamed later.
                    "name": item.display_name,
                    "icon": item.icon,
                    "rarity": item.rarity,
                    "item_type": item.item_type,
                    "sprite_key": item.sprite_key,
                    "catalog_icon": item_catalog_icon(item),
                }
                if item.item_type in COSMETIC_TYPES:
                    slot["salvage_coins_snapshot"] = random_cosmetic_salvage_coins(item)
                items.append(slot)

        return {"coins": coins, "items": items}

    @staticmethod
    def _materialize_loot(user, expedition):
        """Convert the locked ``loot`` JSON into real ledger + inventory rows.

        Returns ``(coins_awarded, loot_changed)`` — ``coins_awarded`` is
        the actual coin amount after the Lucky Coin boost; ``loot_changed``
        is True when the cosmetic-dupe salvage path annotated the loot JSON
        in-memory and the caller needs to include ``loot`` in
        ``save(update_fields=...)`` so the annotation survives a refresh.
        """
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService
        from apps.rpg.models import ItemDefinition, UserInventory
        from apps.rpg.inventory import grant_item

        coins_planned = int(expedition.loot.get("coins") or 0)
        coins_awarded = 0
        if coins_planned > 0:
            entry = CoinService.award_coins(
                user, coins_planned, CoinLedger.Reason.EXPEDITION,
                source=CoinLedger.Source.EXPEDITION,
                description=(
                    f"{expedition.mount.species.name} returned from a "
                    f"{expedition.tier} expedition"
                ),
            )
            if entry is not None:
                coins_awarded = int(entry.amount)

        # Items — same cosmetic-dupe salvage path DropService uses, so
        # players who own a cosmetic don't accumulate dupes.
        cosmetic_types = {
            ItemDefinition.ItemType.COSMETIC_FRAME,
            ItemDefinition.ItemType.COSMETIC_TITLE,
            ItemDefinition.ItemType.COSMETIC_THEME,
            ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
        }
        loot_changed = False
        for slot in expedition.loot.get("items") or []:
            item_id = slot.get("item_id")
            qty = int(slot.get("quantity") or 1)
            if not item_id or qty <= 0:
                continue
            try:
                item = ItemDefinition.objects.get(pk=item_id)
            except ItemDefinition.DoesNotExist:
                # Item was archived between roll and claim — skip silently;
                # the kid still got the coin payout.
                continue

            is_cosmetic = item.item_type in cosmetic_types
            existing = (
                UserInventory.objects.filter(user=user, item=item).first()
                if is_cosmetic else None
            )

            # Only newly accepted trips carry the smaller frozen salvage quote.
            # A legacy slot without this key retains its original claim path.
            salvage_coins = slot.get("salvage_coins_snapshot", item.coin_value)
            if is_cosmetic and existing is not None and salvage_coins > 0:
                # Salvage to coins.
                CoinService.award_coins(
                    user, salvage_coins, CoinLedger.Reason.ADJUSTMENT,
                    source=CoinLedger.Source.EXPEDITION_SALVAGE,
                    description=f"Salvaged duplicate from expedition: {item.display_name}",
                )
                slot["salvaged_to_coins"] = salvage_coins
                loot_changed = True
                continue

            grant_item(user, item, qty)

        return coins_awarded, loot_changed

    @staticmethod
    def _serialize_claim_result(expedition, *, coins_awarded, freshly_claimed):
        mount = expedition.mount
        return {
            "expedition_id": expedition.pk,
            "tier": expedition.tier,
            "coins_awarded": coins_awarded,
            "items": list(expedition.loot.get("items") or []),
            "freshly_claimed": freshly_claimed,
            "mount": {
                "id": mount.pk,
                "species_name": mount.species.name,
                "species_slug": mount.species.slug,
                "species_sprite_key": mount.species.sprite_key,
                "species_icon": mount.species.icon,
                "potion_name": mount.potion.name,
                "potion_slug": mount.potion.slug,
            },
        }
