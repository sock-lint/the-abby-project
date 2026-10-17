"""Retire stale companion offers without touching saved content or promises."""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.rpg.companion_catalog import CompanionCatalogCollision, reconcile_companion_offers


class Command(BaseCommand):
    help = "Remove unsupported egg/potion drop configuration and deactivate digital shop offers."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Inventory affected rows without writing.")
        parser.add_argument("--json", action="store_true", help="Print the exact affected identity/configuration report.")

    def handle(self, *args, **options):
        try:
            report = reconcile_companion_offers(dry_run=options["dry_run"])
        except CompanionCatalogCollision as exc:
            raise CommandError(str(exc)) from exc
        if options["json"]:
            self.stdout.write(json.dumps(report, sort_keys=True))
        else:
            mode = "[dry-run] would retire" if options["dry_run"] else "retired"
            self.stdout.write(
                f"{mode}: {report['drops_removed']} drop rows, "
                f"{report['rewards_deactivated']} digital offers; "
                f"{report['retained_quest_reward_links']} quest reward links retained"
            )
