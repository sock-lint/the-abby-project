"""Upgrade real saved daily notes without changing privacy or paying again."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from urllib.parse import quote

from django.db import connection


ROLLBACK_SCRIPT = r'''
    import django
    django.setup()
    from datetime import date
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    old_targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "chronicle"]
    old_targets.append(("chronicle", "0007_grade_entries"))
    executor.migrate(old_targets)
    old_apps = executor.loader.project_state(old_targets).apps
    Family = old_apps.get_model("families", "Family")
    User = old_apps.get_model("accounts", "User")
    Wellbeing = old_apps.get_model("wellbeing", "DailyWellbeingEntry")
    family = Family.objects.create(name="Rollback notes", slug="rollback-notes")
    child = User.objects.create(username="rollback-author", role="child", family=family)
    note = Wellbeing.objects.create(
        user=child, date=date(2026, 7, 31), affirmation_slug="old-affirmation",
        gratitude_lines=["Only mine."],
    )
    source_before = list(Wellbeing.objects.order_by("pk").values())

    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(leaves)
    Entry = executor.loader.project_state(leaves).apps.get_model("chronicle", "ChronicleEntry")
    assert Entry.objects.filter(kind="daily_note").count() == 1

    executor = MigrationExecutor(connection)
    executor.migrate(old_targets)
    back_apps = executor.loader.project_state(old_targets).apps
    assert back_apps.get_model("chronicle", "ChronicleEntry").objects.filter(kind="daily_note").count() == 0
    assert list(back_apps.get_model("wellbeing", "DailyWellbeingEntry").objects.order_by("pk").values()) == source_before

    executor = MigrationExecutor(connection)
    executor.migrate(leaves)
    Entry = executor.loader.project_state(leaves).apps.get_model("chronicle", "ChronicleEntry")
    notes = list(Entry.objects.filter(kind="daily_note"))
    assert len(notes) == 1, len(notes)
    assert notes[0].daily_note_source_id == note.pk and notes[0].summary == "Only mine."
    assert notes[0].is_private
'''


class DailyNoteMigrationTests(unittest.TestCase):
    def test_real_upgrade_keeps_all_text_and_sources_separate_from_shared_journal(self):
        code = r'''
            import django
            django.setup()
            from datetime import date, datetime, timezone
            from importlib import import_module
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            from unittest.mock import patch
            assert connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            old_targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "chronicle"]
            old_targets.append(("chronicle", "0007_grade_entries"))
            executor.migrate(old_targets)
            old_apps = executor.loader.project_state(old_targets).apps
            Family = old_apps.get_model("families", "Family")
            User = old_apps.get_model("accounts", "User")
            Wellbeing = old_apps.get_model("wellbeing", "DailyWellbeingEntry")
            Entry = old_apps.get_model("chronicle", "ChronicleEntry")
            family = Family.objects.create(name="Note history", slug="note-history")
            child = User.objects.create(username="note-author", role="child", family=family)
            shared = Entry.objects.create(
                user=child, kind="journal", occurred_on=date(2026, 7, 31), chapter_year=2025,
                title="A shared memory", summary="This is deliberately shared.", is_private=False,
            )
            paid_at = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
            first = Wellbeing.objects.create(
                user=child, date=date(2026, 7, 31), affirmation_slug="old-affirmation",
                gratitude_lines=["My private thought.", "A second thought."], coin_paid_at=paid_at,
            )
            Wellbeing.objects.filter(pk=first.pk).update(created_at=paid_at)
            second = Wellbeing.objects.create(
                user=child, date=date(2026, 8, 1), affirmation_slug="old-affirmation",
                gratitude_lines=["An unpaid saved note."],
            )
            Wellbeing.objects.create(
                user=child, date=date(2026, 8, 2), affirmation_slug="old-affirmation", gratitude_lines=[],
            )
            Wellbeing.objects.create(
                user=child, date=date(2026, 8, 3), affirmation_slug="old-affirmation", gratitude_lines=[" ", ""],
            )
            source_before = list(Wellbeing.objects.order_by("pk").values())
            shared_before = list(Entry.objects.filter(pk=shared.pk).values())
            rewards_before = {
                (app, model): list(old_apps.get_model(app, model).objects.order_by("pk").values())
                for app, model in [("rewards", "CoinLedger"), ("achievements", "SkillProgress"),
                                   ("notifications", "Notification"), ("activity", "ActivityEvent")]
            }
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes()
            with patch("apps.rewards.services.CoinService.award_coins") as coins, patch(
                "apps.achievements.services.AwardService.grant",
            ) as xp, patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
                executor.migrate(targets)
                coins.assert_not_called()
                xp.assert_not_called()
                game.assert_not_called()
            new_apps = executor.loader.project_state(targets).apps
            Entry = new_apps.get_model("chronicle", "ChronicleEntry")
            notes = list(Entry.objects.filter(kind="daily_note").order_by("occurred_on"))
            assert len(notes) == 2
            assert notes[0].daily_note_source_id == first.pk and notes[1].daily_note_source_id == second.pk
            assert notes[0].occurred_on == date(2026, 7, 31) and notes[0].chapter_year == 2025
            assert notes[1].occurred_on == date(2026, 8, 1) and notes[1].chapter_year == 2026
            assert notes[0].summary == "My private thought.\n\nA second thought."
            assert notes[1].summary == "An unpaid saved note."
            assert notes[0].created_at == paid_at
            assert all(note.is_private for note in notes)
            assert all(note.metadata["reward_receipt"] == {
                "status": "unavailable", "xp_awarded": 0, "skills": [],
                "coins_awarded": 0, "coin_status": "unavailable",
            } for note in notes)
            assert list(new_apps.get_model("wellbeing", "DailyWellbeingEntry").objects.order_by("pk").values()) == source_before
            shared_after = list(Entry.objects.filter(pk=shared.pk).values())
            assert [{key: value for key, value in row.items() if key != "daily_note_source_id"}
                    for row in shared_after] == shared_before
            for (app, model), before in rewards_before.items():
                assert list(new_apps.get_model(app, model).objects.order_by("pk").values()) == before
            migration = import_module("apps.chronicle.migrations.0008_daily_notes_in_journal")
            state = list(Entry.objects.order_by("pk").values())
            with connection.schema_editor() as editor:
                migration.import_daily_notes(new_apps, editor)
                migration.import_daily_notes(new_apps, editor)
            assert list(Entry.objects.order_by("pk").values()) == state
        '''
        self.run_migration_script(code)

    def test_rollback_removes_private_projections_and_reapply_does_not_duplicate(self):
        # Earlier access rules only hide private journals and grades, so a
        # daily_note left behind by a rollback would become parent-readable.
        self.run_migration_script(ROLLBACK_SCRIPT)

    @unittest.skipUnless(connection.vendor == "postgresql", "PostgreSQL defers foreign-key checks until commit")
    def test_rollback_on_postgresql(self):
        # Production runs PostgreSQL, where the reverse's deletes queue deferred
        # foreign-key checks before the column is dropped in the same transaction.
        db = connection.settings_dict
        name = f"daily_note_rollback_{os.getpid()}"
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{name}"')
        try:
            credentials = quote(db["USER"] or "", safe="") + (":" + quote(db["PASSWORD"], safe="") if db["PASSWORD"] else "")
            self.run_migration_script(ROLLBACK_SCRIPT, database_url=(
                f"postgres://{credentials}@{db['HOST'] or 'localhost'}:{db['PORT'] or 5432}/{name}"
            ))
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP DATABASE IF EXISTS "{name}"')

    def run_migration_script(self, code, database_url="sqlite:///:memory:"):
        bootstrap = ("PATH", "HOME", "LD_LIBRARY_PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        env = {key: os.environ[key] for key in bootstrap if key in os.environ}
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings_test", "DATABASE_URL": database_url,
            "SECRET_KEY": "daily-note-upgrade-synthetic", "DEBUG": "True",
        })
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)], cwd=Path(__file__).resolve().parents[3],
            env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

