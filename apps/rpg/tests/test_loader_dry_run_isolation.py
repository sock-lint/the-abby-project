"""Regression test: loader's dry-run must not leak writes when called
outside a caller-managed transaction.

This was a live bug: MCP tool handlers invoked ``ContentPack.load(dry_run=True)``
directly without an outer ``atomic`` block. ``transaction.savepoint()``
is a no-op when there's no active transaction, so the dry-run's
"rollback" silently left rows in the DB. The fix is to wrap
``ContentPack.load`` in ``@transaction.atomic`` so the inner savepoint
always has an outer transaction to nest inside.

Uses ``TransactionTestCase`` rather than ``TestCase`` because Django's
default ``TestCase`` wraps each test in a transaction — which would mask
exactly this bug (the savepoint would accidentally work inside the
test's transaction). ``TransactionTestCase`` runs tests without the
wrapper, so the dry-run is called in the exact same transaction state
as a production MCP tool handler.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TransactionTestCase

from apps.rpg.content.loader import ContentPack
from apps.rpg.models import ItemDefinition


class DryRunIsolationTests(TransactionTestCase):
    """Dry-run must not persist writes, with or without caller transaction."""

    def _write_pack(self, tmp: Path, slug: str) -> Path:
        pack_dir = tmp / "testpack"
        pack_dir.mkdir()
        (pack_dir / "items.yaml").write_text(
            f"items:\n"
            f"  - slug: {slug}\n"
            f"    name: Test Item\n"
            f"    item_type: food\n"
            f"    rarity: common\n"
            f"    coin_value: 1\n",
            encoding="utf-8",
        )
        return pack_dir

    def test_dry_run_does_not_persist_outside_transaction(self) -> None:
        """With no caller-managed transaction, dry_run must still roll back.

        Before the fix, this leaked two writes — validate_content_pack
        created rows in production even though the stats reported dry_run.
        """
        slug = "dryrun-regression-item"
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._write_pack(Path(tmp), slug)
            stats = ContentPack(pack_dir, namespace="drregr-").load(
                dry_run=True,
            )

        # The stats might say "created" in the counts — that's fine,
        # counts are accumulated before rollback. What matters is the
        # DB state afterwards.
        self.assertIn("item_food", stats.created, msg="dry-run still counts work")
        self.assertFalse(
            ItemDefinition.objects.filter(slug=f"drregr-{slug}").exists(),
            "dry-run leaked an ItemDefinition into the DB — "
            "savepoint_rollback didn't actually roll back. Is "
            "ContentPack.load wrapped in @transaction.atomic?",
        )

    def test_real_load_persists(self) -> None:
        """Sanity check: with dry_run=False, writes DO persist."""
        slug = "realload-regression-item"
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._write_pack(Path(tmp), slug)
            ContentPack(pack_dir, namespace="realregr-").load(dry_run=False)

        self.assertTrue(
            ItemDefinition.objects.filter(slug=f"realregr-{slug}").exists(),
        )

    def test_validate_then_load_creates_not_updates(self) -> None:
        """After validate (dry-run), a real load must create rows fresh.

        This is the end-to-end MCP flow that surfaced the bug: Claude
        Desktop calls validate_content_pack, then load_content_pack.
        Before the fix, validate persisted writes, so load saw them
        as existing rows and reported them as ``updated`` instead of
        ``created``.
        """
        slug = "vthenl-regression-item"
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._write_pack(Path(tmp), slug)
            ContentPack(pack_dir, namespace="vthenl-").load(dry_run=True)
            real_stats = ContentPack(pack_dir, namespace="vthenl-").load(
                dry_run=False,
            )
        # If dry-run correctly rolls back, the real load creates fresh.
        self.assertEqual(
            real_stats.created.get("item_food", 0), 1,
            "Real load after validate should report created=1, not updated=1. "
            "If this is 0, validate's dry-run leaked into production.",
        )
        self.assertEqual(
            real_stats.updated.get("item_food", 0), 0,
        )
