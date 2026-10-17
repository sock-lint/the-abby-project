"""Exercise discovery retries and preferences through real PostgreSQL locks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from config.tests.factories import make_family

from apps.reading.models import (
    ReadingBook, ReadingDailyReward, ReadingDiscoveryFeedback,
    ReadingFamilySuggestion, ReadingRewardCredit, ReadingSession,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingDiscoveryConcurrencyTests(TransactionTestCase):
    feedback_url = "/api/reading/discovery-feedback/"
    suggestions_url = "/api/reading-family-suggestions/"

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Discovery row-lock concurrency requires PostgreSQL.")
        family = make_family(
            "Concurrent discovery family",
            parents=[{"username": "concurrent-discovery-parent"}, {"username": "concurrent-discovery-coparent"}],
            children=[{"username": "concurrent-discovery-reader"}],
        )
        self.child = family.children[0]
        self.parent, self.coparent = family.parents

    def concurrent_posts(self, url, requests):
        """Start two separately authenticated requests on distinct connections."""
        barrier = Barrier(2)

        def post(request):
            user, payload = request
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait(timeout=10)
                response = client.post(url, payload, format="json")
                return response.status_code, response.data
            finally:
                # Persistent connections belong to their worker threads and
                # must be closed before Django destroys the disposable DB.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(post, requests, timeout=30))

    def assert_no_reading_or_reward_side_effects(self):
        from apps.achievements.models import SkillProgress
        from apps.activity.models import ActivityEvent
        from apps.rewards.models import CoinLedger

        for model in (ReadingBook, ReadingSession, ReadingDailyReward, ReadingRewardCredit, SkillProgress, CoinLedger, ActivityEvent):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.exists())

    def test_concurrent_same_parent_suggestion_retry_creates_exactly_once(self):
        request_id = str(uuid4())
        payload = {
            "catalog_id": "the-wild-robot", "message": "Try this together?",
            "client_request_id": request_id, "user_id": self.child.id,
        }
        results = self.concurrent_posts(self.suggestions_url, [(self.parent, payload), (self.parent, payload)])
        self.assertEqual(sorted(code for code, _ in results), [200, 201], results)
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        saved = ReadingFamilySuggestion.objects.get(user=self.child, client_request_id=request_id)
        self.assertEqual(saved.suggested_by_id, self.parent.id)
        self.assertEqual(saved.message, payload["message"])
        self.assertEqual(ReadingFamilySuggestion.objects.count(), 1)
        self.assert_no_reading_or_reward_side_effects()

    def test_concurrent_different_parent_same_uuid_rejects_one_request(self):
        request_id = str(uuid4())
        payload = {"catalog_id": "the-wild-robot", "client_request_id": request_id, "user_id": self.child.id}
        results = self.concurrent_posts(self.suggestions_url, [(self.parent, payload), (self.coparent, payload)])
        self.assertEqual(sorted(code for code, _ in results), [201, 400], results)
        saved = ReadingFamilySuggestion.objects.get(user=self.child, client_request_id=request_id)
        winner = next(data for code, data in results if code == 201)
        self.assertEqual(saved.suggested_by_id, winner["suggested_by"]["id"])
        self.assertEqual(ReadingFamilySuggestion.objects.count(), 1)
        self.assert_no_reading_or_reward_side_effects()

    def test_concurrent_conflicting_suggestion_payloads_do_not_duplicate_or_overwrite(self):
        request_id = str(uuid4())
        payload = {"catalog_id": "the-wild-robot", "message": "First idea", "client_request_id": request_id, "user_id": self.child.id}
        changed = {**payload, "message": "A different idea"}
        results = self.concurrent_posts(self.suggestions_url, [(self.parent, payload), (self.parent, changed)])
        self.assertEqual(sorted(code for code, _ in results), [201, 400], results)
        saved = ReadingFamilySuggestion.objects.get(user=self.child, client_request_id=request_id)
        winner = next(data for code, data in results if code == 201)
        self.assertEqual(saved.message, winner["message"])
        self.assertEqual(ReadingFamilySuggestion.objects.count(), 1)
        self.assert_no_reading_or_reward_side_effects()

    def test_concurrent_identical_feedback_returns_receipts_and_one_row(self):
        payload = {"catalog_id": "the-wild-robot", "choice": "not_interested"}
        results = self.concurrent_posts(self.feedback_url, [(self.child, payload), (self.child, payload)])
        self.assertEqual([code for code, _ in results], [200, 200], results)
        self.assertEqual([data for _, data in results], [payload, payload])
        saved = ReadingDiscoveryFeedback.objects.get(user=self.child, catalog_id=payload["catalog_id"])
        self.assertEqual(saved.choice, payload["choice"])
        self.assertEqual(ReadingDiscoveryFeedback.objects.count(), 1)
        self.assert_no_reading_or_reward_side_effects()

    def test_concurrent_feedback_choices_keep_each_receipt_and_last_saved_choice(self):
        first = {"catalog_id": "the-wild-robot", "choice": "not_interested"}
        second = {"catalog_id": "the-wild-robot", "choice": "already_read"}
        results = self.concurrent_posts(self.feedback_url, [(self.child, first), (self.child, second)])
        self.assertEqual([code for code, _ in results], [200, 200], results)
        self.assertEqual([data for _, data in results], [first, second])
        saved = ReadingDiscoveryFeedback.objects.get(user=self.child, catalog_id=first["catalog_id"])
        # Either transaction may acquire the owner lock first. Each request
        # reports its accepted choice; the persisted value is the later one.
        self.assertIn(saved.choice, (first["choice"], second["choice"]))
        self.assertEqual(ReadingDiscoveryFeedback.objects.count(), 1)
        self.assert_no_reading_or_reward_side_effects()

    def test_concurrent_clear_and_update_serialize_without_duplicate_feedback(self):
        ReadingDiscoveryFeedback.objects.create(user=self.child, catalog_id="the-wild-robot", choice="not_interested")
        clear = {"catalog_id": "the-wild-robot", "choice": ""}
        update = {"catalog_id": "the-wild-robot", "choice": "already_read"}
        results = self.concurrent_posts(self.feedback_url, [(self.child, clear), (self.child, update)])
        self.assertEqual([code for code, _ in results], [200, 200], results)
        self.assertEqual([data for _, data in results], [clear, update])
        remaining = list(ReadingDiscoveryFeedback.objects.filter(user=self.child).values_list("choice", flat=True))
        # Clear winning last removes the row; update winning last recreates it.
        self.assertIn(remaining, ([], ["already_read"]))
        self.assert_no_reading_or_reward_side_effects()
