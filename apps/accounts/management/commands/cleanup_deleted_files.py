"""Retry due storage cleanup work without disclosing private object names."""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.file_cleanup import process_pending_file_deletions
from apps.accounts.models import PendingFileDeletion


class Command(BaseCommand):
    help = "Retry a bounded batch of due private file deletions; failures remain queued."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--status", action="store_true", help="Only show aggregate queue health; do not retry files.")

    def handle(self, *args, **options):
        if options["status"]:
            jobs = PendingFileDeletion.objects.all()
            oldest = jobs.order_by("created_at").values_list("created_at", flat=True).first()
            self.stdout.write(
                f"due={jobs.filter(retry_at__lte=timezone.now()).count()} pending={jobs.count()} "
                f"failed={jobs.filter(last_error='storage_error').count()} "
                f"referenced={jobs.filter(last_error='still_referenced').count()} "
                f"oldest_pending={oldest.isoformat() if oldest else 'none'}"
            )
            return
        try:
            result = process_pending_file_deletions(limit=options["limit"])
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(
            f"deleted={result['deleted']} failed={result['failed']} "
            f"referenced={result['referenced']} pending={PendingFileDeletion.objects.count()}"
        )
