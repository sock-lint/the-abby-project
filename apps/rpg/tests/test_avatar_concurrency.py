"""PostgreSQL acceptance for concurrent appearance and progression writes."""

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier
from time import monotonic, sleep

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.rpg.avatar import AVATAR_DEFAULTS
from apps.rpg.models import CharacterProfile, ItemDefinition
from config.tests.factories import make_family


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AvatarConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family(
            "Avatar concurrency family", children=[{"username": "avatar-concurrency-child"}],
        ).children[0]
        self.profile = CharacterProfile.objects.get(user=self.child)
        self.profile.level = 3
        self.profile.login_streak = 4
        self.profile.save()

    def save_avatar(self, preferences, *, backend_pids=None, start=None):
        close_old_connections()
        try:
            # A regression should fail boundedly instead of hanging CI forever.
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            if backend_pids is not None:
                backend_pids.put(pid)
            client = APIClient()
            client.force_authenticate(self.child)
            if start is not None:
                start.wait(timeout=5)
            response = client.post(
                "/api/character/avatar/", {"avatar_preferences": preferences}, format="json",
            )
            return response.status_code, response.json()
        finally:
            connection.close()

    def assert_waiting_for_row_lock(self, backend_pid):
        deadline = monotonic() + 3
        while monotonic() < deadline:
            # Read another connection's actual database wait, not a guessed
            # sleep duration or a mocked select_for_update call.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [backend_pid],
                )
                row = cursor.fetchone()
            if row and row[0] == "Lock":
                return
            sleep(0.02)
        self.fail("Avatar save did not wait for the locked character row.")

    def test_avatar_waits_for_progression_write_and_preserves_latest_earned_state(self):
        frame = ItemDefinition.objects.create(name="Concurrent earned frame", item_type="cosmetic_frame")
        preferences = {**AVATAR_DEFAULTS, "outfit": "fire", "hair_style": "hair-04"}
        backend_pids = Queue()
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                locked = CharacterProfile.objects.select_for_update().get(pk=self.profile.pk)
                future = executor.submit(self.save_avatar, preferences, backend_pids=backend_pids)
                self.assert_waiting_for_row_lock(backend_pids.get(timeout=5))
                locked.level = 8
                locked.login_streak = 12
                locked.active_frame = frame
                locked.save(update_fields=["level", "login_streak", "active_frame", "updated_at"])
            status, body = future.result(timeout=10)
        self.assertEqual(status, 200)
        self.assertEqual(body["avatar_preferences"], preferences)
        self.assertEqual(body["level"], 8)
        self.assertEqual(body["login_streak"], 12)
        self.assertEqual(body["active_frame"]["id"], frame.pk)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, preferences)
        self.assertEqual(self.profile.level, 8)
        self.assertEqual(self.profile.login_streak, 12)
        self.assertEqual(self.profile.active_frame_id, frame.pk)

    def test_concurrent_full_replacements_return_their_own_confirmed_choices(self):
        choices = [
            {"hair_style": "hair-01", "hair_color": "dark", "skin_tone": "fair", "outfit": "nature"},
            {"hair_style": "hair-02", "hair_color": "light", "skin_tone": "tan", "outfit": "aqua"},
            {"hair_style": "hair-03", "hair_color": "dark", "skin_tone": "tan", "outfit": "fire"},
            {"hair_style": "hair-04", "hair_color": "light", "skin_tone": "fair", "outfit": "dark"},
        ]
        start = Barrier(len(choices))
        with ThreadPoolExecutor(max_workers=len(choices)) as executor:
            futures = [executor.submit(self.save_avatar, preferences, start=start) for preferences in choices]
            results = [future.result(timeout=15) for future in futures]
        for preferences, (status, body) in zip(choices, results):
            self.assertEqual(status, 200)
            self.assertEqual(body["avatar_preferences"], preferences)
        self.profile.refresh_from_db()
        self.assertIn(self.profile.avatar_preferences, choices)
        self.assertEqual(self.profile.level, 3)
        self.assertEqual(self.profile.login_streak, 4)
