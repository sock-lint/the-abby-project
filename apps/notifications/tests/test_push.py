"""Tests for Web Push — the out-of-app channel for the approve loop.

The load-bearing property is that push is *additive*: with no VAPID keypair
configured, or a push service having a bad day, every existing notification
path behaves exactly as it did before push existed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.notifications.models import Notification, PushSubscription
from apps.notifications.push import push_enabled, send_to_user
from apps.notifications.services import notify
from config.tests.factories import make_family

KEYS = {
    "VAPID_PUBLIC_KEY": "test-public",
    "VAPID_PRIVATE_KEY": "test-private",
    "VAPID_SUBJECT": "mailto:test@example.com",
}


def make_subscription(user, endpoint="https://push.example/abc"):
    return PushSubscription.objects.create(
        user=user, endpoint=endpoint, p256dh="p256dh-key", auth="auth-key",
    )


class PushEnabledTests(TestCase):
    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_disabled_without_keys(self):
        self.assertFalse(push_enabled())

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="")
    def test_disabled_with_only_half_a_keypair(self):
        self.assertFalse(push_enabled())

    @override_settings(**KEYS)
    def test_enabled_with_a_full_keypair(self):
        # pywebpush ships in requirements; if it were missing this would be
        # False rather than raising at notification time.
        self.assertTrue(push_enabled())


class NotifyIntegrationTests(TestCase):
    def setUp(self):
        self.family = make_family(
            "Push House",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.child = self.family.children[0]

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_notify_works_unchanged_when_push_is_unconfigured(self):
        notification = notify(self.child, "Chore approved", "Dishes", "chore_approved")
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(notification.title, "Chore approved")

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_no_task_is_queued_when_push_is_unconfigured(self):
        # An unconfigured deployment shouldn't pay to enqueue a task per
        # notification just to have the worker no-op on it.
        with patch("apps.notifications.tasks.send_push_notification.delay") as delay:
            notify(self.child, "Hi", "", "chore_approved")
        delay.assert_not_called()

    @override_settings(**KEYS)
    def test_notification_is_handed_to_the_push_task(self):
        with patch("apps.notifications.tasks.send_push_notification.delay") as delay:
            notify(self.child, "Chore approved", "Dishes", "chore_approved", link="/x")
        delay.assert_called_once_with(
            self.child.id, "Chore approved", "Dishes", "/x", "chore_approved",
        )

    @override_settings(**KEYS)
    def test_a_dead_broker_never_breaks_the_in_app_notification(self):
        with patch(
            "apps.notifications.tasks.send_push_notification.delay",
            side_effect=OSError("broker unreachable"),
        ):
            notify(self.child, "Still works", "", "chore_approved")
        self.assertEqual(Notification.objects.count(), 1)


@override_settings(**KEYS)
class SendToUserTests(TestCase):
    def setUp(self):
        self.family = make_family(
            "Push House", parents=[{"username": "p"}], children=[{"username": "k"}],
        )
        self.child = self.family.children[0]

    def test_returns_zero_with_no_registered_devices(self):
        self.assertEqual(send_to_user(self.child, title="Hi"), 0)

    def test_delivers_to_each_device_and_stamps_success(self):
        make_subscription(self.child, "https://push.example/one")
        make_subscription(self.child, "https://push.example/two")
        with patch("pywebpush.webpush") as webpush:
            sent = send_to_user(self.child, title="Chore approved", body="Dishes")
        self.assertEqual(sent, 2)
        self.assertEqual(webpush.call_count, 2)
        self.assertEqual(
            PushSubscription.objects.filter(last_success_at__isnull=False).count(), 2,
        )

    def test_payload_carries_title_body_url_and_type(self):
        make_subscription(self.child)
        with patch("pywebpush.webpush") as webpush:
            send_to_user(
                self.child, title="T", body="B", url="/quests", notification_type="x",
            )
        import json
        payload = json.loads(webpush.call_args.kwargs["data"])
        self.assertEqual(
            payload, {"title": "T", "body": "B", "url": "/quests", "type": "x"},
        )

    def test_url_defaults_so_the_service_worker_always_has_somewhere_to_go(self):
        make_subscription(self.child)
        with patch("pywebpush.webpush") as webpush:
            send_to_user(self.child, title="T")
        import json
        self.assertEqual(json.loads(webpush.call_args.kwargs["data"])["url"], "/")

    def test_dead_subscription_is_pruned(self):
        make_subscription(self.child)
        from pywebpush import WebPushException

        response = MagicMock()
        response.status_code = 410  # Gone — the browser dropped it.
        with patch(
            "pywebpush.webpush",
            side_effect=WebPushException("gone", response=response),
        ):
            sent = send_to_user(self.child, title="T")
        self.assertEqual(sent, 0)
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_transient_failure_keeps_the_subscription(self):
        make_subscription(self.child)
        from pywebpush import WebPushException

        response = MagicMock()
        response.status_code = 500  # Push service hiccup — try again later.
        with patch(
            "pywebpush.webpush",
            side_effect=WebPushException("boom", response=response),
        ):
            sent = send_to_user(self.child, title="T")
        self.assertEqual(sent, 0)
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_unexpected_errors_are_swallowed(self):
        make_subscription(self.child)
        with patch("pywebpush.webpush", side_effect=RuntimeError("kaboom")):
            self.assertEqual(send_to_user(self.child, title="T"), 0)

    def test_long_bodies_are_truncated(self):
        make_subscription(self.child)
        with patch("pywebpush.webpush") as webpush:
            send_to_user(self.child, title="T", body="x" * 500)
        import json
        self.assertEqual(len(json.loads(webpush.call_args.kwargs["data"])["body"]), 200)


class PushAPITests(TestCase):
    def setUp(self):
        self.family = make_family(
            "Push House", parents=[{"username": "p"}], children=[{"username": "k"}],
        )
        self.child = self.family.children[0]
        self.other = make_family(
            "Elsewhere", parents=[{"username": "p2"}], children=[{"username": "k2"}],
        ).children[0]
        self.client = APIClient()

    def body(self, endpoint="https://push.example/abc"):
        return {
            "endpoint": endpoint,
            "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
        }

    def test_config_requires_authentication(self):
        self.assertEqual(self.client.get(reverse("push-config")).status_code, 401)

    @override_settings(**KEYS)
    def test_config_exposes_only_the_public_key(self):
        self.client.force_authenticate(user=self.child)
        data = self.client.get(reverse("push-config")).data
        self.assertTrue(data["enabled"])
        self.assertEqual(data["public_key"], "test-public")
        self.assertNotIn("private", str(data).lower())

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_config_reports_disabled_without_keys(self):
        self.client.force_authenticate(user=self.child)
        data = self.client.get(reverse("push-config")).data
        self.assertFalse(data["enabled"])
        self.assertEqual(data["public_key"], "")

    @override_settings(**KEYS)
    def test_subscribe_registers_the_browser(self):
        self.client.force_authenticate(user=self.child)
        response = self.client.post(reverse("push-subscribe"), self.body(), format="json")
        self.assertEqual(response.status_code, 201)
        subscription = PushSubscription.objects.get()
        self.assertEqual(subscription.user, self.child)
        self.assertEqual(subscription.p256dh, "p256dh-key")

    @override_settings(**KEYS)
    def test_subscribe_is_idempotent_on_endpoint(self):
        self.client.force_authenticate(user=self.child)
        self.client.post(reverse("push-subscribe"), self.body(), format="json")
        self.client.post(reverse("push-subscribe"), self.body(), format="json")
        # Re-subscribing the same browser must not double-notify.
        self.assertEqual(PushSubscription.objects.count(), 1)

    @override_settings(**KEYS)
    def test_resubscribing_a_shared_device_reassigns_it(self):
        # A shared family tablet: whoever signed in last owns the endpoint,
        # otherwise the previous user keeps getting the new user's pushes.
        self.client.force_authenticate(user=self.child)
        self.client.post(reverse("push-subscribe"), self.body(), format="json")
        self.client.force_authenticate(user=self.family.parents[0])
        self.client.post(reverse("push-subscribe"), self.body(), format="json")
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.assertEqual(PushSubscription.objects.get().user, self.family.parents[0])

    @override_settings(**KEYS)
    def test_subscribe_rejects_an_incomplete_payload(self):
        self.client.force_authenticate(user=self.child)
        response = self.client.post(
            reverse("push-subscribe"), {"endpoint": "https://x/"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PushSubscription.objects.count(), 0)

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_subscribe_refuses_when_the_server_cannot_send(self):
        self.client.force_authenticate(user=self.child)
        response = self.client.post(reverse("push-subscribe"), self.body(), format="json")
        self.assertEqual(response.status_code, 503)

    @override_settings(**KEYS)
    def test_unsubscribe_removes_the_row(self):
        make_subscription(self.child)
        self.client.force_authenticate(user=self.child)
        response = self.client.post(
            reverse("push-unsubscribe"),
            {"endpoint": "https://push.example/abc"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 0)

    @override_settings(**KEYS)
    def test_unsubscribe_cannot_silence_someone_elses_device(self):
        make_subscription(self.other, "https://push.example/theirs")
        self.client.force_authenticate(user=self.child)
        self.client.post(
            reverse("push-unsubscribe"),
            {"endpoint": "https://push.example/theirs"},
            format="json",
        )
        self.assertEqual(PushSubscription.objects.count(), 1)
