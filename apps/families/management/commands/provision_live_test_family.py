"""Provision only the reserved, separately owned deployed browser fixture."""
import json

from django.core.management.base import BaseCommand

from apps.families.live_tests import provision_live_test_family, read_private_credentials


class Command(BaseCommand):
    help = "Create or verify the separately owned Abby live-test family from a private mode-0600 file."

    def add_arguments(self, parser):
        parser.add_argument("--credentials-file", required=True)
        parser.add_argument("--rotate-passwords", action="store_true")

    def handle(self, *args, **options):
        receipt = provision_live_test_family(
            read_private_credentials(options["credentials_file"]),
            rotate_passwords=options["rotate_passwords"],
        )
        self.stdout.write(json.dumps(receipt, sort_keys=True))
