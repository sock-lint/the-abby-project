"""An operator's read-only aggregate weekly usage summary."""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.usage.reporting import build_usage_report


class Command(BaseCommand):
    help = "Print a weekly aggregate usage summary without sending messages."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Staff parent whose access scope is used.")
        parser.add_argument("--scope", choices=["family", "deployment"], default="family")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"], is_active=True, role="parent", is_staff=True).first()
        if user is None or (options["scope"] == "deployment" and not user.is_superuser):
            raise CommandError("An active staff parent is required; deployment scope also requires a superuser.")
        report = build_usage_report(user, scope=options["scope"], days=7)
        self.stdout.write(json.dumps({"scope": report["scope"], "collection": report["collection"], "weekly_summary": report["weekly_summary"]}, sort_keys=True))
