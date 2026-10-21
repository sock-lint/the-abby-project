"""The cooperative marker changes future routing, never accepted history."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class CooperativeCatalogMigrationTests(unittest.TestCase):
    def test_real_upgrade_preserves_legacy_and_automatic_promises_without_awards(self):
        code = r'''
            from datetime import timedelta
            import django
            django.setup()
            from django.conf import settings
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            from django.utils import timezone
            assert not getattr(settings, "MIGRATION_MODULES", {})
            assert connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            old_targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "quests"]
            old_targets.append(("quests", "0010_reconcile_catalog_definitions"))
            executor.migrate(old_targets)
            old_apps = executor.loader.project_state(old_targets).apps
            models = {name: old_apps.get_model(app, name) for app, name in [
                ("families", "Family"), ("accounts", "User"), ("quests", "QuestDefinition"),
                ("quests", "Quest"), ("quests", "QuestParticipant"), ("quests", "ChallengeGoal"),
                ("quests", "ChallengeOccurrence"), ("quests", "ChallengeActivity"),
                ("quests", "ChallengeContribution"), ("quests", "ChallengePin"),
                ("rewards", "CoinLedger"), ("rpg", "UserInventory"),
            ]}
            family = models["Family"].objects.create(name="Shared upgrade", slug="shared-upgrade")
            first = models["User"].objects.create(username="upgrade-first", role="child", family=family)
            second = models["User"].objects.create(username="upgrade-second", role="child", family=family)
            parent = models["User"].objects.create(username="upgrade-parent", role="parent", family=family)
            name = "Family Co-op — Spring Cleaning"
            definition = models["QuestDefinition"].objects.create(
                name=name, is_system=True, quest_type="collection", target_value=20,
                duration_days=14, coin_reward=100, xp_reward=100,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            alias = models["QuestDefinition"].objects.create(
                name=name, is_system=True, quest_type="collection", target_value=20,
                superseded_by_id=definition.pk,
            )
            private = models["QuestDefinition"].objects.create(
                name=name, is_system=False, created_by=parent, quest_type="collection", target_value=3,
            )
            owned_system = models["QuestDefinition"].objects.create(
                name=name, is_system=True, created_by=parent, quest_type="collection", target_value=20,
                duration_days=14, coin_reward=100, xp_reward=100,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            other = models["QuestDefinition"].objects.create(
                name="Another catalog goal", is_system=True, quest_type="collection", target_value=3,
            )
            now = timezone.now()
            legacy = models["Quest"].objects.create(
                definition=definition, start_date=now-timedelta(days=1), end_date=now+timedelta(days=13),
                current_progress=7, reward_items_snapshot=[],
            )
            for child in (first, second):
                models["QuestParticipant"].objects.create(quest=legacy, user=child, contribution=3 if child == first else 4)
                start = now-timedelta(days=15 if child == first else 1)
                end = start+timedelta(days=14)
                goal = models["ChallengeGoal"].objects.create(
                    user=child, family=family, catalog_definition=definition, is_catalog=True,
                    name=name, metric="count", target=20, unit="actions", timezone_name="America/Phoenix",
                    starts_at=start, ends_at=end, coin_reward=100,
                    trigger_filter={"allowed_triggers": ["chore_complete"]},
                )
                paid = child == first
                occurrence = models["ChallengeOccurrence"].objects.create(
                    goal=goal, starts_at=start, ends_at=end, progress=20 if paid else 7,
                    status="completed" if paid else "active", completed_at=now if paid else None,
                    awarded_at=now if paid else None,
                    snapshot={"name": name, "metric": "count", "target": "20", "coins": 100},
                    reward_receipt={"coins": 100, "xp": 0, "items": []} if paid else {},
                )
                activity = models["ChallengeActivity"].objects.create(
                    user=child, source_type="chore_complete", source_id="saved-source", trigger_type="chore_complete",
                    occurred_at=now, occurred_on=now.date(), context={}, processed_at=now,
                )
                models["ChallengeContribution"].objects.create(occurrence=occurrence, activity=activity, amount=1)
                models["ChallengePin"].objects.create(user=child, occurrence=occurrence)
            owned_goal = models["ChallengeGoal"].objects.create(
                user=first, family=family, catalog_definition=owned_system, is_catalog=True,
                name="Accepted owner-authored promise", metric="count", target=20, unit="actions",
                timezone_name="America/Phoenix", starts_at=now-timedelta(days=1),
                ends_at=now+timedelta(days=13), coin_reward=17,
            )
            models["ChallengeOccurrence"].objects.create(
                goal=owned_goal, starts_at=owned_goal.starts_at, ends_at=owned_goal.ends_at, progress=3,
                snapshot={"name": owned_goal.name, "target": "20", "coins": 17},
            )
            models["CoinLedger"].objects.create(user=first, amount=100, reason="adjustment", description="Saved payout")
            before = {name: list(model.objects.order_by("pk").values()) for name, model in models.items()}
            executor = MigrationExecutor(connection)
            latest = executor.loader.graph.leaf_nodes()
            executor.migrate(latest)
            new_apps = executor.loader.project_state(latest).apps
            for name, rows in before.items():
                upgraded = new_apps.get_model(models[name]._meta.app_label, name)
                if rows:
                    assert list(upgraded.objects.order_by("pk").values(*rows[0])) == rows, name
                else:
                    assert not upgraded.objects.exists(), name
            Definition = new_apps.get_model("quests", "QuestDefinition")
            assert list(Definition.objects.order_by("pk").values_list("id", "is_cooperative")) == [
                (definition.pk, True), (alias.pk, True), (private.pk, False),
                (owned_system.pk, False), (other.pk, False),
            ]
            # The follow-up schema adds explicit attempts and future setup,
            # without turning any historical window into a retry or schedule.
            Goal = new_apps.get_model("quests", "ChallengeGoal")
            Occurrence = new_apps.get_model("quests", "ChallengeOccurrence")
            assert set(Goal.objects.values_list("schedule_revision", flat=True)) == {0}
            assert not Occurrence.objects.filter(retry_of__isnull=False).exists()
            assert set(Occurrence.objects.values_list("closed_reason", flat=True)) == {""}
            assert not new_apps.get_model("quests", "ChallengeSchedule").objects.exists()
        '''
        bootstrap = ("PATH", "HOME", "LD_LIBRARY_PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        env = {key: os.environ[key] for key in bootstrap if key in os.environ}
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings_test", "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "cooperative-upgrade-synthetic", "DEBUG": "True", "PYTHONDONTWRITEBYTECODE": "1",
        })
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)], cwd=Path(__file__).resolve().parents[3],
            env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
