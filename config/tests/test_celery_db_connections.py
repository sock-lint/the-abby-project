"""Inline tasks must preserve their caller's transaction and connection."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from config.celery import (
    _close_stale_db_connections_after_task,
    _close_stale_db_connections_before_task,
)


class CeleryConnectionLifecycleTests(SimpleTestCase):
    def assert_lifecycle(self, callback, *, eager, expected_cleanup):
        task = SimpleNamespace(request=SimpleNamespace(is_eager=eager))
        with patch("django.db.close_old_connections") as close:
            callback(sender=task)
        self.assertEqual(close.call_count, expected_cleanup)

    def test_eager_prerun_preserves_callers_transaction(self):
        self.assert_lifecycle(_close_stale_db_connections_before_task, eager=True, expected_cleanup=0)

    def test_eager_postrun_preserves_callers_transaction(self):
        self.assert_lifecycle(_close_stale_db_connections_after_task, eager=True, expected_cleanup=0)

    def test_worker_prerun_still_cleans_stale_connections(self):
        self.assert_lifecycle(_close_stale_db_connections_before_task, eager=False, expected_cleanup=1)

    def test_worker_postrun_still_cleans_stale_connections(self):
        self.assert_lifecycle(_close_stale_db_connections_after_task, eager=False, expected_cleanup=1)
