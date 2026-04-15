"""Prune pack-scoped DropTable + Reward rows ahead of a re-load.

Context: ``ContentPack.load`` is upsert-only — removing a drop rule or
shop reward from a pack's YAML and re-loading does NOT delete the stale
row. This command lets an operator wipe the pack's drop + reward surface
clean so the next ``loadrpgcontent`` call re-materializes exactly what
the current YAML declares.

Pack-scoping uses ``ItemDefinition.slug.startswith(namespace)`` where
``namespace`` is derived from the pack name (``<pack>-`` by convention).
Rewards are matched via ``Reward.item_definition`` FK and by name-prefix
fallback for rewards without an item link.

Does NOT prune:
  - ``ItemDefinition`` rows (deleting them would cascade to UserInventory)
  - ``QuestDefinition`` or ``QuestRewardItem`` rows (owned by quests; the
    loader re-upserts them, so stale reward-items DO linger but that's a
    separate concern)
  - ``Badge`` rows (no slug; name is display-facing — operator should
    rename/delete via admin if needed)

Usage::

    python manage.py prune_pack_content --pack sleep-prep-2026
    python manage.py prune_pack_content --pack sleep-prep-2026 --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def prune_pack(pack_name: str, *, dry_run: bool = False) -> dict[str, int]:
    """Delete pack-scoped DropTable + Reward rows.

    Returns a count dict like ``{"drops": 3, "rewards": 2}``.
    When ``dry_run`` is True, the counts reflect what WOULD be deleted
    but nothing persists (wrapped in a rolled-back savepoint).
    """
    from apps.rewards.models import Reward
    from apps.rpg.models import DropTable, ItemDefinition

    if not pack_name:
        raise ValueError("pack_name is required")
    prefix = pack_name if pack_name.endswith("-") else f"{pack_name}-"

    counts = {"drops": 0, "rewards": 0}

    with transaction.atomic():
        sid = transaction.savepoint()
        try:
            # Find every item belonging to this pack
            pack_item_ids = list(
                ItemDefinition.objects.filter(
                    slug__startswith=prefix,
                ).values_list("id", flat=True)
            )

            # Prune drops that reference any pack item
            drops_qs = DropTable.objects.filter(item_id__in=pack_item_ids)
            counts["drops"] = drops_qs.count()
            drops_qs.delete()

            # Prune rewards linked to pack items via FK
            rewards_qs = Reward.objects.filter(
                item_definition_id__in=pack_item_ids,
            )
            counts["rewards"] = rewards_qs.count()
            rewards_qs.delete()

            if dry_run:
                transaction.savepoint_rollback(sid)
            else:
                transaction.savepoint_commit(sid)
        except Exception:
            transaction.savepoint_rollback(sid)
            raise

    return counts


class Command(BaseCommand):
    help = "Prune pack-scoped DropTable + Reward rows before a re-load."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pack",
            required=True,
            help="Pack name (e.g. 'sleep-prep-2026'). Used as slug prefix.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts without deleting anything.",
        )

    def handle(self, *args, **options):
        pack_name = options["pack"]
        dry_run = options["dry_run"]

        try:
            counts = prune_pack(pack_name, dry_run=dry_run)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        mode = "[dry-run] would delete" if dry_run else "deleted"
        self.stdout.write(
            f"{mode} {counts['drops']} DropTable rows, "
            f"{counts['rewards']} Reward rows (pack={pack_name!r})"
        )
