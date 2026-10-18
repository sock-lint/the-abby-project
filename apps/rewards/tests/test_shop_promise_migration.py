"""Run the real historical shop upgrade without awarding or rewriting history."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class ShopPromiseMigrationTests(unittest.TestCase):
    def test_upgrade_freezes_recoverable_promises_and_preserves_saved_state(self):
        code = r'''
            import django
            django.setup()
            from importlib import import_module
            from django.conf import settings
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            assert not getattr(settings, "MIGRATION_MODULES", {})
            assert connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            old_targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "rewards"]
            old_targets.append(("rewards", "0011_add_expedition_reason"))
            executor.migrate(old_targets)
            old_apps = executor.loader.project_state(old_targets).apps
            models = {name: old_apps.get_model(app, name) for app, name in [
                ("families", "Family"), ("accounts", "User"), ("rewards", "Reward"),
                ("rewards", "RewardRedemption"), ("rewards", "CoinLedger"),
                ("rpg", "ItemDefinition"), ("rpg", "UserInventory"),
            ]}
            family = models["Family"].objects.create(name="Upgrade household", slug="shop-upgrade")
            child = models["User"].objects.create(username="upgrade-child", role="child", family=family)
            parent = models["User"].objects.create(username="upgrade-parent", role="parent", family=family)
            item = models["ItemDefinition"].objects.create(slug="upgrade-frame", name="Saved frame", item_type="cosmetic_frame")
            models["CoinLedger"].objects.create(user=child, amount=333, reason="adjustment")
            models["UserInventory"].objects.create(user=child, item=item, quantity=7)
            cases = [
                ("pending", "both", item.pk, 2),
                ("fulfilled", "digital_item", item.pk, 0),
                ("denied", "real_world", item.pk, None),
                ("pending", "digital_item", None, None),
                ("pending", "real_world", None, 5),
            ]
            ids = []
            for index, (status, kind, item_id, stock) in enumerate(cases):
                reward = models["Reward"].objects.create(
                    name=f"Saved reward {index}", family=family, cost_coins=123,
                    fulfillment_kind=kind, item_definition_id=item_id, stock=stock,
                )
                row = models["RewardRedemption"].objects.create(
                    user=child, reward=reward, coin_cost_snapshot=17, status=status,
                    parent_notes="Original decision notes", decided_by=parent if status != "pending" else None,
                )
                ids.append(row.pk)
            before = {name: list(model.objects.order_by("pk").values()) for name, model in models.items()}
            executor = MigrationExecutor(connection)
            latest = executor.loader.graph.leaf_nodes()
            executor.migrate(latest)
            new_apps = executor.loader.project_state(latest).apps
            for name, rows in before.items():
                upgraded = new_apps.get_model(models[name]._meta.app_label, name)
                assert list(upgraded.objects.order_by("pk").values(*rows[0])) == rows, name
            Redemption = new_apps.get_model("rewards", "RewardRedemption")
            assert list(Redemption.objects.order_by("pk").values_list(
                "delivered_at", "delivered_by_id",
            )) == [(None, None)] * len(cases), "Historical delivery dates must remain unknown"
            snapshots = list(Redemption.objects.order_by("pk").values_list(
                "fulfillment_kind_snapshot", "item_definition_snapshot_id", "stock_reserved",
            ))
            assert snapshots == [
                ("both", item.pk, True), ("digital_item", item.pk, True),
                ("real_world", None, False), ("digital_item", None, False), ("real_world", None, True),
            ], snapshots
            # Re-running the backfill cannot rewrite already frozen identities.
            new_apps.get_model("rewards", "Reward").objects.update(fulfillment_kind="real_world", item_definition_id=None)
            migration = import_module("apps.rewards.migrations.0012_freeze_redemption_promises")
            with connection.schema_editor() as editor:
                migration.freeze_existing_promises(new_apps, editor)
            assert list(Redemption.objects.order_by("pk").values_list(
                "fulfillment_kind_snapshot", "item_definition_snapshot_id", "stock_reserved",
            )) == snapshots
        '''
        bootstrap = ("PATH", "HOME", "LD_LIBRARY_PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        env = {key: os.environ[key] for key in bootstrap if key in os.environ}
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings_test", "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "shop-upgrade-synthetic", "DEBUG": "True",
        })
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)], cwd=Path(__file__).resolve().parents[3],
            env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
