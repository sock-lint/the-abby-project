"""Exercise the real historical schema upgrade and safe rollback."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from urllib.parse import quote

from django.db import connection


UPGRADE_SCRIPT = r'''
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    assert not getattr(settings, "MIGRATION_MODULES", {})
    assert (connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:") or (
        connection.vendor == "postgresql" and connection.settings_dict["NAME"].startswith("starter_habit_upgrade_")
    )
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [node for node in latest if node[0] != "habits"]
    previous.append(("habits", "0006_habit_last_decay_date"))
    executor.migrate(previous)
    old_apps = executor.loader.project_state(previous).apps
    Family = old_apps.get_model("families", "Family")
    User = old_apps.get_model("accounts", "User")
    Habit = old_apps.get_model("habits", "Habit")
    HabitLog = old_apps.get_model("habits", "HabitLog")
    children = []
    for index in range(2):
        family = Family.objects.create(name=f"Migration family {index}", slug=f"starter-upgrade-{index}")
        User.objects.create(username=f"upgrade-parent-{index}", role="parent", family=family)
        children.append(User.objects.create(username=f"upgrade-child-{index}", role="child", family=family))
    legacy = Habit.objects.create(
        name="Brush teeth", user=children[0], created_by=children[0],
        max_taps_per_day=2, xp_reward=13, strength=8, is_active=False,
    )
    old_log = HabitLog.objects.create(habit=legacy, user=children[0], direction=1)
    before = list(Habit.objects.filter(pk=legacy.pk).values())[0]

    executor = MigrationExecutor(connection)
    executor.migrate(latest)
    new_apps = executor.loader.project_state(latest).apps
    NewHabit = new_apps.get_model("habits", "Habit")
    NewLog = new_apps.get_model("habits", "HabitLog")
    for child in children:
        assert NewHabit.objects.filter(user_id=child.pk, starter_key="brush_teeth").count() == 1
    assert not NewHabit.objects.filter(user__role="parent").exists()
    assert NewHabit.objects.filter(pk=legacy.pk).values(*before).get() == before
    new_habit = NewHabit.objects.get(user_id=children[1].pk, starter_key="brush_teeth")
    new_log = NewLog.objects.create(habit=new_habit, user_id=children[1].pk, direction=1)

    executor = MigrationExecutor(connection)
    executor.migrate(previous)
    rollback_apps = executor.loader.project_state(previous).apps
    OldHabit = rollback_apps.get_model("habits", "Habit")
    OldLog = rollback_apps.get_model("habits", "HabitLog")
    assert OldHabit.objects.filter(pk=legacy.pk).values(*before).get() == before
    assert OldHabit.objects.filter(pk=new_habit.pk).exists()
    assert set(OldLog.objects.values_list("pk", flat=True)) == {old_log.pk, new_log.pk}

    # A rollback retains habits and logs. Reapplying adopts both twice-daily
    # routines instead of adding duplicates.
    executor = MigrationExecutor(connection)
    executor.migrate(latest)
    NewHabit = executor.loader.project_state(latest).apps.get_model("habits", "Habit")
    assert NewHabit.objects.count() == 2
    assert NewHabit.objects.filter(starter_key="brush_teeth").count() == 2
'''


class StarterHabitMigrationTests(unittest.TestCase):
    def test_upgrade_and_rollback_preserve_existing_and_new_completion_history(self):
        self.run_migration_script()

    @unittest.skipUnless(connection.vendor == "postgresql", "PostgreSQL schema and transaction behavior")
    def test_upgrade_and_rollback_on_postgresql(self):
        db = connection.settings_dict
        name = f"starter_habit_upgrade_{os.getpid()}"
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{name}"')
        try:
            credentials = quote(db["USER"] or "", safe="")
            if db["PASSWORD"]:
                credentials += ":" + quote(db["PASSWORD"], safe="")
            self.run_migration_script(database_url=(
                f"postgres://{credentials}@{db['HOST'] or 'localhost'}:{db['PORT'] or 5432}/{name}"
            ))
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP DATABASE IF EXISTS "{name}"')

    def run_migration_script(self, database_url="sqlite:///:memory:"):
        bootstrap = ("PATH", "HOME", "LD_LIBRARY_PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        env = {key: os.environ[key] for key in bootstrap if key in os.environ}
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings_test", "DATABASE_URL": database_url,
            "SECRET_KEY": "starter-upgrade-synthetic", "DEBUG": "True",
        })
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(UPGRADE_SCRIPT)],
            cwd=Path(__file__).resolve().parents[3], env=env,
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
