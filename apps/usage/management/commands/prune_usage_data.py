import json

from django.core.management.base import BaseCommand

from apps.usage.services import prune_usage_data


class Command(BaseCommand):
    help = "Delete expired first-party usage events and daily visit buckets."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(prune_usage_data(), sort_keys=True))
