"""One-time backfill: record state-only extraction migrations in django_migrations.

When models moved between apps (projects → accounts/notifications/ingestion/
achievements, rpg → habits), existing databases already had downstream
migrations applied (e.g. admin.0001_initial) that now depend on the new
app-extraction migrations via AUTH_USER_MODEL or direct dependencies.

Running ``migrate`` on those databases fails with
InconsistentMigrationHistory because the state-only extraction migrations
were never recorded.

This command inserts the missing records so ``migrate`` can proceed.
Every migration listed here is state-only (SeparateDatabaseAndState with
empty database_operations), so fake-applying is safe.
The command is idempotent — safe to run on fresh databases or repeatedly.
"""

from django.core.management.base import BaseCommand
from django.db import connection


# State-only extraction migrations, in dependency order.
# Each is a SeparateDatabaseAndState with zero SQL — safe to fake-apply
# on any database where the physical tables already exist.
BACKFILL_MIGRATIONS = [
    # Notification model move: projects → notifications
    ("notifications", "0001_initial"),
    ("projects", "0013_move_notification_out"),
    # ProjectIngestionJob model move: projects → ingestion
    ("ingestion", "0001_initial"),
    ("projects", "0014_move_ingestion_out"),
    # SkillCategory model move: projects → achievements
    ("achievements", "0005_receive_skillcategory"),
    ("projects", "0015_move_skillcategory_out"),
    # User model move: projects → accounts
    ("accounts", "0001_initial"),
    ("accounts", "0002_alter_user_options_alter_user_managers"),
    ("projects", "0016_move_user_out"),
    # Habit/HabitLog model move: rpg → habits
    ("habits", "0001_initial"),
    ("rpg", "0008_move_habits_to_habits_app"),
]


class Command(BaseCommand):
    help = "Backfill state-only extraction migration records for databases that predate the app-boundary refactors."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            for app, name in BACKFILL_MIGRATIONS:
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
