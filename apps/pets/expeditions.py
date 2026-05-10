"""Mount expedition service — Finch-inspired offline play loop.

A user sends their mount on a 2/4/8h expedition. Loot (coins + 1-3 items) is
rolled at *start* and locked to the row's ``loot`` JSONField — slow-claim
users get the same payout regardless of when they tap through. On claim,
the loot is materialized into ``CoinLedger`` + ``UserInventory`` and the
single ``GameLoopService`` orchestrator is invoked with ``drops_allowed=False``
so streak/quest credit fires once without double-dipping the drop roll.

Daily cap: each mount can run one expedition per local day. The check is on
``created_at`` (start time), not ``returns_at`` — preserves "ran today"
intent even if the long-tier expedition crosses midnight.
"""
from __future__ import annotations

import logging
import random
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

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
        "base_coins": 15,
        "item_slots": 1,
        "rarity_weights": {"common": 70, "uncommon": 25, "rare": 5},
    },
    "standard": {
        "duration_minutes": 240,   # 4h
        "base_coins": 35,
        "item_slots": 2,
        "rarity_weights": {"common": 50, "uncommon": 35, "rare": 13, "epic": 2},
    },
    "long": {
        "duration_minutes": 480,   # 8h
        "base_coins": 75,
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


class ExpeditionService:
    """Lifecycle manager for ``MountExpedition`` rows."""

    @staticmethod
    @transaction.atomic
    def start(user, mount_id, tier):
        """Send a mount on an expedition. Raises ``ExpeditionError`` on failure.

        Returns the new ``MountExpedition`` row.
        """
        from apps.pets.models import MountExpedition, UserMount

        if tier not in TIER_CONFIG:
            raise ExpeditionError(
                f"Unknown tier {tier!r} — must be one of {sorted(TIER_CONFIG)}"
            )

        try:
            mount = UserMount.objects.select_for_update().get(
                pk=mount_id, user=user,
            )
        except UserMount.DoesNotExist:
            # Typed exception — view turns this into a 404 without leaking
            # whether a mount with that pk exists in another household.
            raise ExpeditionNotFound("Mount not found")

        # One active expedition per mount (DB constraint also enforces this,
        # but we surface a friendly error before the IntegrityError).
        active = MountExpedition.objects.filter(
            mount=mount, status=MountExpedition.Status.ACTIVE,
        ).first()
        if active is not None:
            raise ExpeditionError(
                f"{mount.species.name} is already out — "
                f"returning in {max(0, active.seconds_remaining)} seconds"
            )

        # Daily cap: one expedition per mount per local day.
        today = timezone.localdate()
        already_today = MountExpedition.objects.filter(
            mount=mount, started_at__date=today,
        ).exists()
        if already_today:
            raise ExpeditionError(
                f"{mount.species.name} has already been out today — "
                "they need rest before another run"
            )

        config = TIER_CONFIG[tier]
        now = timezone.now()
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
        from apps.pets.models import MountExpedition

        try:
            expedition = (
                MountExpedition.objects
                .select_for_update()
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
                    link="/bestiary?tab=mounts",
                )
                notify_parents(
                    title=f"{display_name}'s mount returned",
                    message=msg,
                    notification_type="expedition_returned",
                    about_user=user,
                    link="/bestiary?tab=mounts",
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
        from apps.rpg.models import CharacterProfile, DropTable, ItemDefinition

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

        entries = list(
            DropTable.objects
            .filter(trigger_type=TriggerType.EXPEDITION_RETURNED, min_level__lte=user_level)
            .select_related("item")
        )
        if not entries:
            # Fallback: borrow from clock_out + chore_complete pools so a
            # fresh deployment without expedition-specific drops still
            # produces sensible loot. Cosmetic items dominate those pools
            # by design — they're the "feels like an adventure" payoff.
            entries = list(
                DropTable.objects
                .filter(
                    trigger_type__in=[
                        TriggerType.CLOCK_OUT,
                        TriggerType.CHORE_COMPLETE,
                    ],
                    min_level__lte=user_level,
                )
                .select_related("item")
            )

        items = []
        if entries:
            # Bias by tier rarity weights — recompute weights to favour
            # rarer items in longer-tier expeditions. Fall back to the
            # authored DropTable.weight when the item's rarity isn't in
            # the tier's rarity_weights map.
            rarity_w = config["rarity_weights"]
            biased_weights = []
            for entry in entries:
                # Use authored weight as a secondary multiplier so high-
                # weight commons still beat low-weight legendaries on
                # short expeditions. The intent is subtle bias, not a
                # rarity steamroller.
                rarity_factor = rarity_w.get(entry.item.rarity, 1)
                biased_weights.append(max(1, entry.weight * rarity_factor))

            for _ in range(config["item_slots"]):
                selected = random.choices(entries, weights=biased_weights, k=1)[0]
                item = selected.item
                items.append({
                    "item_id": item.pk,
                    "quantity": 1,
                    # Snapshot display fields so the loot row reads
                    # the same even if the item is renamed later.
                    "name": item.name,
                    "icon": item.icon,
                    "rarity": item.rarity,
                    "item_type": item.item_type,
                    "sprite_key": item.sprite_key,
                })

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

        coins_planned = int(expedition.loot.get("coins") or 0)
        coins_awarded = 0
        if coins_planned > 0:
            entry = CoinService.award_coins(
                user, coins_planned, CoinLedger.Reason.EXPEDITION,
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

            if is_cosmetic and existing is not None and item.coin_value > 0:
                # Salvage to coins.
                CoinService.award_coins(
                    user, item.coin_value, CoinLedger.Reason.ADJUSTMENT,
                    description=f"Salvaged duplicate from expedition: {item.name}",
                )
                slot["salvaged_to_coins"] = item.coin_value
                loot_changed = True
                continue

            # Otherwise: stack into inventory. Use the same get-or-create
            # pattern as the breeding flow so concurrent claims don't double.
            inv, created = UserInventory.objects.get_or_create(
                user=user, item=item, defaults={"quantity": qty},
            )
            if not created:
                inv.quantity += qty
                inv.save(update_fields=["quantity", "updated_at"])

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
