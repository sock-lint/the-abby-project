"""Real PostgreSQL transactions fence account administration and late logins."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, local
from unittest.mock import patch

from django.core.cache import cache
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chores.models import Chore, ChoreCompletion
from apps.families.models import Family
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


_worker = local()


@skipUnlessDBFeature("has_select_for_update")
class AccountLifecycleConcurrencyTests(TransactionTestCase):
    """Each request uses its own connection; events select the actual interleaving."""

    password = "Lifecycle-test-password-73!"
    close_url = "/api/account/lifecycle/close-family/"

    def setUp(self):
        cache.clear()
        self.household = make_family(
            "Lifecycle concurrency household",
            parents=[{"username": "lifecycle-parent", "password": self.password}],
            children=[{"username": "lifecycle-child"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.token = Token.objects.create(user=self.parent)
        self._refresh_closure_version()

    def _refresh_closure_version(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        response = client.get("/api/account/lifecycle/")
        self.assertEqual(response.status_code, 200, response.data)
        self.family_version = response.data["family_version"]

    def _request(self, label, method, url, *, token=None, data=None, family_lock=None):
        close_old_connections()
        _worker.label = label
        try:
            # A failed locking implementation must fail boundedly instead of
            # leaving CI workers or the test database occupied indefinitely.
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")

            def observe_family_lock(execute, sql, params, many, context):
                if family_lock is not None and '"families_family"' in sql and "FOR " in sql:
                    family_lock.set()
                return execute(sql, params, many, context)

            client = APIClient()
            if token is not None:
                client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
            with connection.execute_wrapper(observe_family_lock):
                response = getattr(client, method)(url, data=data, format="json")
            return response.status_code, getattr(response, "data", None)
        finally:
            connection.close()
            _worker.label = None

    def _closure_data(self):
        return {
            "password": self.password,
            "confirm_family_slug": self.household.family.slug,
            "family_version": self.family_version,
        }

    def _hold_authenticated(self, label, arrived, release):
        original = TokenAuthentication.authenticate_credentials

        def authenticate(authenticator, key):
            result = original(authenticator, key)
            if getattr(_worker, "label", None) == label:
                arrived.set()
                if not release.wait(10):
                    raise TimeoutError("Authenticated request was not released")
            return result

        return patch.object(TokenAuthentication, "authenticate_credentials", authenticate)

    def test_concurrent_parents_cannot_delete_each_other_and_leave_no_parent(self):
        other = User.objects.create_user(
            username="lifecycle-coparent", password=self.password,
            family=self.household.family, role="parent",
        )
        other_token = Token.objects.create(user=other)
        authenticated = Barrier(2, timeout=10)
        original = TokenAuthentication.authenticate_credentials

        def authenticate(authenticator, key):
            result = original(authenticator, key)
            authenticated.wait()
            return result

        with patch.object(TokenAuthentication, "authenticate_credentials", authenticate), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                self._request, "first", "delete", f"/api/parents/{other.pk}/", token=self.token.key,
            )
            second = pool.submit(
                self._request, "second", "delete", f"/api/parents/{self.parent.pk}/", token=other_token.key,
            )
            statuses = sorted([first.result(timeout=15)[0], second.result(timeout=15)[0]])
        self.assertEqual(statuses, [204, 401])
        survivors = list(User.objects.filter(family=self.household.family, role="parent", is_active=True))
        self.assertEqual(len(survivors), 1)
        self.household.family.refresh_from_db()
        self.assertEqual(self.household.family.primary_parent_id, survivors[0].pk)

    def test_revocation_after_authentication_prevents_delayed_member_patch(self):
        authenticated, release = Event(), Event()
        with self._hold_authenticated("patch", authenticated, release), ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                self._request, "patch", "patch", f"/api/children/{self.child.pk}/",
                token=self.token.key, data={"display_name": "A stale edit"},
            )
            try:
                self.assertTrue(authenticated.wait(5), "PATCH did not authenticate")
                Token.objects.filter(pk=self.token.pk).delete()
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=15)[0], 401)
        self.child.refresh_from_db()
        self.assertNotEqual(self.child.display_name, "A stale edit")

    def test_membership_change_after_authentication_prevents_delayed_member_patch(self):
        other = make_family("Unrelated household", parents=[{"username": "unrelated-parent"}])
        authenticated, release = Event(), Event()
        with self._hold_authenticated("patch", authenticated, release), ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                self._request, "patch", "patch", f"/api/children/{self.child.pk}/",
                token=self.token.key, data={"display_name": "A foreign-family edit"},
            )
            try:
                self.assertTrue(authenticated.wait(5), "PATCH did not authenticate")
                User.objects.filter(pk=self.parent.pk).update(family=other.family)
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=15)[0], 401)
        self.child.refresh_from_db()
        self.assertNotEqual(self.child.display_name, "A foreign-family edit")

    def test_member_creation_after_review_requires_fresh_family_closure_confirmation(self):
        created, release_create, close_lock = Event(), Event(), Event()
        original = User.save

        def hold_new_member(user, *args, **kwargs):
            result = original(user, *args, **kwargs)
            if getattr(_worker, "label", None) == "create" and user.username == "new-lifecycle-child":
                created.set()
                if not release_create.wait(10):
                    raise TimeoutError("Member creation was not released")
            return result

        with patch.object(User, "save", hold_new_member), ThreadPoolExecutor(max_workers=2) as pool:
            creating = pool.submit(
                self._request, "create", "post", "/api/children/", token=self.token.key,
                data={"username": "new-lifecycle-child", "password": self.password},
            )
            try:
                self.assertTrue(created.wait(5), "New member was not inserted")
                closing = pool.submit(
                    self._request, "close", "post", self.close_url, token=self.token.key,
                    data=self._closure_data(), family_lock=close_lock,
                )
                self.assertTrue(close_lock.wait(5), "Closure did not attempt to lock the family")
            finally:
                release_create.set()
            self.assertEqual(creating.result(timeout=15)[0], 201)
            self.assertEqual(closing.result(timeout=15)[0], 409)
        self.assertTrue(Family.objects.filter(pk=self.household.family.pk).exists())
        self.assertTrue(User.objects.filter(username="new-lifecycle-child").exists())
        self._refresh_closure_version()
        status, _body = self._request(
            "reviewed-close", "post", self.close_url, token=self.token.key, data=self._closure_data(),
        )
        self.assertEqual(status, 204)
        self.assertFalse(Family.objects.filter(pk=self.household.family.pk).exists())
        self.assertFalse(User.objects.filter(username="new-lifecycle-child").exists())

    def test_member_creation_authenticated_before_closure_cannot_recreate_the_family(self):
        closing_started, release_close, create_lock = Event(), Event(), Event()
        original = Family.delete

        def hold_closure(family, *args, **kwargs):
            if getattr(_worker, "label", None) == "close":
                closing_started.set()
                if not release_close.wait(10):
                    raise TimeoutError("Family closure was not released")
            return original(family, *args, **kwargs)

        with patch.object(Family, "delete", hold_closure), ThreadPoolExecutor(max_workers=2) as pool:
            closing = pool.submit(
                self._request, "close", "post", self.close_url, token=self.token.key,
                data=self._closure_data(),
            )
            try:
                self.assertTrue(closing_started.wait(5), "Closure did not reach the locked delete")
                creating = pool.submit(
                    self._request, "create", "post", "/api/children/", token=self.token.key,
                    data={"username": "late-lifecycle-child", "password": self.password},
                    family_lock=create_lock,
                )
                self.assertTrue(create_lock.wait(5), "Creation did not attempt to lock the family")
            finally:
                release_close.set()
            self.assertEqual(closing.result(timeout=15)[0], 204)
            self.assertEqual(creating.result(timeout=15)[0], 401)
        self.assertFalse(Family.objects.filter(pk=self.household.family.pk).exists())
        self.assertFalse(User.objects.filter(username="late-lifecycle-child").exists())

    def test_closure_refuses_busy_approval_without_deadlock_and_can_be_retried(self):
        from apps.achievements.services import _lock_award_user as original_lock_award_user
        from apps.chores.services import ChoreService

        chore = Chore.objects.create(
            title="Concurrent chore approval", created_by=self.parent,
            family=self.household.family, coin_reward=3, xp_reward=0,
        )
        completion = ChoreCompletion.objects.create(
            chore=chore, user=self.child, completed_date="2026-10-17",
            reward_amount_snapshot=0, coin_reward_snapshot=3,
        )
        approval_locked, release_approval = Event(), Event()

        def hold_before_award_user(user):
            if getattr(_worker, "label", None) == "approve":
                # The real approval already holds ChoreCompletion's row lock.
                # Lifecycle locks users before its dependent-record preflight.
                approval_locked.set()
                if not release_approval.wait(10):
                    raise TimeoutError("Chore approval was not released")
            return original_lock_award_user(user)

        def approve():
            close_old_connections()
            _worker.label = "approve"
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                return ChoreService.approve_completion(completion, self.parent).status
            finally:
                connection.close()
                _worker.label = None

        with patch("apps.achievements.services._lock_award_user", hold_before_award_user), ThreadPoolExecutor(max_workers=2) as pool:
            approving = pool.submit(approve)
            try:
                self.assertTrue(approval_locked.wait(5), "Approval did not reach the locked reward boundary")
                closing = pool.submit(
                    self._request, "close", "post", self.close_url, token=self.token.key,
                    data=self._closure_data(),
                )
                # Waiting for approval here would form an inverse user→record
                # / record→user cycle. Closure must decline while approval is
                # still held, rather than rely on PostgreSQL aborting a victim.
                self.assertEqual(closing.result(timeout=3)[0], 409)
            finally:
                release_approval.set()
            self.assertEqual(approving.result(timeout=15), ChoreCompletion.Status.APPROVED)
        self.assertTrue(Family.objects.filter(pk=self.household.family.pk).exists())
        completion.refresh_from_db()
        self.assertEqual(completion.status, ChoreCompletion.Status.APPROVED)
        chore_awards = CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.CHORE_REWARD)
        self.assertEqual(chore_awards.count(), 1)
        self.assertEqual(chore_awards.get().amount, 3)
        self.assertTrue(Token.objects.filter(pk=self.token.pk).exists())
        self._refresh_closure_version()
        status, _body = self._request(
            "retry-close", "post", self.close_url, token=self.token.key, data=self._closure_data(),
        )
        self.assertEqual(status, 204)
        self.assertFalse(Family.objects.filter(pk=self.household.family.pk).exists())

    def _late_login(self, removal):
        from apps.projects.views import authenticate as original_authenticate

        authenticated, release = Event(), Event()

        def hold_password_result(*args, **kwargs):
            user = original_authenticate(*args, **kwargs)
            if getattr(_worker, "label", None) == "login":
                self.assertIsNotNone(user)
                authenticated.set()
                if not release.wait(10):
                    raise TimeoutError("Password login was not released")
            return user

        with patch("apps.projects.views.authenticate", hold_password_result), ThreadPoolExecutor(max_workers=2) as pool:
            logging_in = pool.submit(
                self._request, "login", "post", "/api/auth/",
                data={"action": "login", "username": self.parent.username, "password": self.password},
            )
            try:
                self.assertTrue(authenticated.wait(5), "Password login did not authenticate")
                status = pool.submit(removal).result(timeout=15)[0]
                self.assertIn(status, [200, 204])
            finally:
                release.set()
            self.assertEqual(logging_in.result(timeout=15)[0], 401)
        self.assertFalse(Token.objects.filter(user_id=self.parent.pk).exists())

    def test_password_login_authenticated_before_deactivation_does_not_mint_a_token(self):
        other = User.objects.create_user(
            username="lifecycle-coparent", password=self.password,
            family=self.household.family, role="parent",
        )
        token = Token.objects.create(user=other)
        self._late_login(lambda: self._request(
            "deactivate", "post", f"/api/parents/{self.parent.pk}/deactivate/", token=token.key,
        ))
        self.parent.refresh_from_db()
        self.assertFalse(self.parent.is_active)

    def test_password_login_authenticated_before_closure_does_not_mint_a_token(self):
        self._late_login(lambda: self._request(
            "close", "post", self.close_url, token=self.token.key, data=self._closure_data(),
        ))
        self.assertFalse(Family.objects.filter(pk=self.household.family.pk).exists())

    def test_password_login_authenticated_before_reset_cannot_use_the_old_password(self):
        other = User.objects.create_user(
            username="lifecycle-coparent", password=self.password,
            family=self.household.family, role="parent",
        )
        token = Token.objects.create(user=other)
        self._late_login(lambda: self._request(
            "reset", "post", f"/api/parents/{self.parent.pk}/reset-password/", token=token.key,
            data={"password": "Replacement-lifecycle-password-83!"},
        ))
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.check_password("Replacement-lifecycle-password-83!"))
