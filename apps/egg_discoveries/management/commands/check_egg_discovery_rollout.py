import json

from django.core.management.base import BaseCommand, CommandError

from apps.egg_discoveries.rollout import readiness


class Command(BaseCommand):
    help = "Inspect egg-discovery catalog readiness without accepting targets or granting rewards."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        report = readiness()
        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
        else:
            self.stdout.write("Catalog ready." if report["catalog_ready"] else "Catalog needs attention.")
            for problem in report["problems"]:
                self.stdout.write(problem)
            self.stdout.write(report["scope"])
        if not report["catalog_ready"]:
            raise CommandError("Egg-discovery catalog is not ready.")
