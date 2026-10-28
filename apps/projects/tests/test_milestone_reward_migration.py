"""Upgrade real historical milestone rows without replaying their rewards."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class MilestoneRewardMigrationTests(unittest.TestCase):
    def test_real_upgrade_protects_only_identifiable_history_without_payouts(self):
        code = r'''
            import django
            django.setup()
            from importlib import import_module
            from django.conf import settings
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            from django.utils import timezone
            from unittest.mock import patch
            assert not getattr(settings, "MIGRATION_MODULES", {})
            assert connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            old_targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "projects"]
            old_targets.append(("projects", "0022_project_is_homework_plan"))
            executor.migrate(old_targets)
            old_apps = executor.loader.project_state(old_targets).apps
            Family = old_apps.get_model("families", "Family")
            User = old_apps.get_model("accounts", "User")
            Project = old_apps.get_model("projects", "Project")
            Milestone = old_apps.get_model("projects", "ProjectMilestone")
            ContentType = old_apps.get_model("contenttypes", "ContentType")
            Activity = old_apps.get_model("activity", "ActivityEvent")
            Payment = old_apps.get_model("payments", "PaymentLedger")
            family = Family.objects.create(name="Milestone history", slug="milestone-history")
            child = User.objects.create(username="history-child", role="child", family=family)
            parent = User.objects.create(username="history-parent", role="parent", family=family)
            project = Project.objects.create(title="Historical phases", created_by=parent, assigned_to=child)
            unassigned_project = Project.objects.create(title="Unassigned phases", created_by=parent)
            Project.objects.create(title="Historical parent zero", created_by=parent, assigned_to=parent,
                                   hourly_rate_override="0.00")
            cases = {
                "completed": {"is_completed": True},
                "reopened": {"completed_at": timezone.now()},
                "typed_activity": {}, "fresh": {}, "untyped_payment": {},
                "wrong_event": {}, "wrong_type": {},
                "unassigned_completed": {"project": unassigned_project, "is_completed": True},
            }
            rows = {key: Milestone.objects.create(**{"project": project, "title": key, **fields})
                    for key, fields in cases.items()}
            milestone_type = ContentType.objects.create(app_label="projects", model="projectmilestone")
            project_type = ContentType.objects.create(app_label="projects", model="project")
            for key, event_type, target_type in [
                ("typed_activity", "milestone.complete", milestone_type),
                ("wrong_event", "project.complete", milestone_type),
                ("wrong_type", "milestone.complete", project_type),
            ]:
                Activity.objects.create(
                    category="approval", event_type=event_type, summary="Historical event",
                    subject=child, target_ct=target_type, target_id=rows[key].pk,
                )
            Payment.objects.create(project=project, user=child, amount="7.00", entry_type="milestone_bonus")
            historical_fields = {
                (app, name): tuple(field.attname for field in old_apps.get_model(app, name)._meta.concrete_fields)
                for app, name in [
                    ("projects", "Project"), ("projects", "ProjectMilestone"),
                    ("payments", "PaymentLedger"), ("rewards", "CoinLedger"),
                    ("achievements", "SkillProgress"), ("notifications", "Notification"),
                    ("activity", "ActivityEvent"),
                ]
            }
            before = {
                (app, name): list(old_apps.get_model(app, name).objects.order_by("pk").values(*fields))
                for (app, name), fields in historical_fields.items()
            }
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes()
            with patch("apps.achievements.services.SkillService.award_xp") as xp, patch(
                "apps.payments.services.PaymentService.record_entry",
            ) as money, patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
                executor.migrate(targets)
                xp.assert_not_called()
                money.assert_not_called()
                game.assert_not_called()
            new_apps = executor.loader.project_state(targets).apps
            Receipt = new_apps.get_model("projects", "MilestoneCompletionRewardReceipt")
            assert set(Receipt.objects.values_list("milestone_id", "user_id", "historical")) == {
                (rows[key].pk, child.pk, True) for key in ("completed", "reopened", "typed_activity")
            } | {(rows["unassigned_completed"].pk, None, True)}
            for (app, name), saved in before.items():
                actual = list(new_apps.get_model(app, name).objects.order_by("pk").values(
                    *historical_fields[(app, name)],
                ))
                assert actual == saved, (app, name, actual, saved)
            # Additive schema fields are checked separately; preserve every
            # historical value, including an explicit parent-owned zero rate.
            defaults = list(new_apps.get_model("projects", "Project").objects.order_by("pk").values_list(
                "hourly_rate_is_personal_default", flat=True,
            ))
            assert len(defaults) == 3 and all(value is False for value in defaults), defaults
            live = Receipt.objects.create(milestone_id=rows["fresh"].pk, user_id=parent.pk)
            receipt_state = list(Receipt.objects.order_by("pk").values())
            migration = import_module("apps.projects.migrations.0023_milestone_completion_reward_receipt")
            with connection.schema_editor() as editor:
                migration.backfill_milestone_completion_receipts(new_apps, editor)
                migration.backfill_milestone_completion_receipts(new_apps, editor)
            assert list(Receipt.objects.order_by("pk").values()) == receipt_state
            # The runtime path must respect migrated history even when only
            # an old correctly typed completion event survived a reopening.
            from apps.projects.models import ProjectMilestone as RuntimeMilestone
            reopened = RuntimeMilestone.objects.get(pk=rows["typed_activity"].pk)
            reopened.is_completed = True
            with patch("apps.achievements.services.SkillService.award_xp") as xp, patch(
                "apps.payments.services.PaymentService.record_entry",
            ) as money, patch("apps.rpg.services.GameLoopService.on_task_completed") as game:
                reopened.save()
                xp.assert_not_called()
                money.assert_not_called()
                game.assert_not_called()
            for app, name in [
                ("payments", "PaymentLedger"), ("rewards", "CoinLedger"),
                ("achievements", "SkillProgress"), ("notifications", "Notification"),
                ("activity", "ActivityEvent"),
            ]:
                assert list(new_apps.get_model(app, name).objects.order_by("pk").values(
                    *historical_fields[(app, name)],
                )) == before[(app, name)]
        '''
        bootstrap = ("PATH", "HOME", "LD_LIBRARY_PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        env = {key: os.environ[key] for key in bootstrap if key in os.environ}
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings_test", "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "milestone-upgrade-synthetic", "DEBUG": "True",
        })
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)], cwd=Path(__file__).resolve().parents[3],
            env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
