"""One-time backfill: record accounts migrations in django_migrations.

When the User model moved from projects to accounts, existing databases
already had admin.0001_initial applied (which now depends on
accounts.0001_initial via AUTH_USER_MODEL).  Running ``migrate`` on those
databases fails with InconsistentMigrationHistory because
accounts.0001_initial was never recorded.

This command inserts the missing records so ``migrate`` can proceed.
Both accounts migrations are state-only (no SQL), so fake-applying is safe.
The command is idempotent — safe to run on fresh databases or repeatedly.
"""

from django.core.management.base import BaseCommand
from django.db import connection


ACCOUNTS_MIGRATIONS = [
    ("accounts", "0001_initial"),
    ("accounts", "0002_alter_user_options_alter_user_managers"),
]


class Command(BaseCommand):
    help = "Backfill accounts migration records for databases that predate the User model move."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            for app, name in ACCOUNTS_MIGRATIONS:
                cursor.execute(
                    "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s",
                    [app, name],
                )
                if cursor.fetchone():
                    self.stdout.write(f"  {app}.{name} — already recorded, skipping.")
                else:
                    cursor.execute(
                        "INSERT INTO django_migrations (app, name, applied) "
                        "VALUES (%s, %s, NOW())",
                        [app, name],
                    )
                    self.stdout.write(self.style.SUCCESS(f"  {app}.{name} — inserted."))

        self.stdout.write(self.style.SUCCESS("Done."))
