"""Real PostgreSQL transactions fence account administration and late logins."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import Barrier, Event, local
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chores.models import Chore, ChoreCompletion
from apps.families.models import Family
from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import SpriteAsset
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

            # Django's exception signal is process-wide: with two clients an
            # expected rejected FK save must not be re-raised by the other
            # request after that request successfully returns 204.
            client = APIClient(raise_request_exception=False)
            if token is not None:
                client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
            with connection.execute_wrapper(observe_family_lock):
                response = getattr(client, method)(url, data=data, format="json")
            if response.status_code == 500 and getattr(response, "exc_info", None):
                error = response.exc_info[1]
                if isinstance(error, IntegrityError):
                    self.assertEqual(getattr(error.__cause__, "pgcode", None), "23503")
                    return "foreign_key_rejected", None
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

    def _create_project(self, title):
        # A request authenticated before deletion may fail its deferred FK
        # after the user is removed. The helper distinguishes that from 201.
        return self._request(
            "create-project", "post", "/api/projects/", token=self.token.key,
            data={"title": title, "assigned_to_id": self.child.pk},
        )

    def _self_delete(self, successor):
        return self._request(
            "delete-self", "post", "/api/account/lifecycle/delete/", token=self.token.key,
            data={"password": self.password, "confirm_username": self.parent.username, "successor_id": successor.pk},
        )

    def test_project_created_after_handoff_cannot_acknowledge_201_then_disappear(self):
        from apps.accounts.lifecycle import collect_safe_deletion as original_collect

        successor = User.objects.create_user(username="handoff-successor", password=self.password, role="parent", family=self.household.family)
        existing = Project.objects.create(title="Already shared", assigned_to=self.child, created_by=self.parent)
        after_handoff, release_delete, inserted = Event(), Event(), Event()
        calls = 0
        original_save = Project.save

        def hold_after_handoff(*args, **kwargs):
            nonlocal calls
            if getattr(_worker, "label", None) == "delete-self":
                calls += 1
                if calls == 2:
                    after_handoff.set()
                    if not release_delete.wait(10):
                        raise TimeoutError("Account departure was not released")
            return original_collect(*args, **kwargs)

        def observe_insert(project, *args, **kwargs):
            result = original_save(project, *args, **kwargs)
            if getattr(_worker, "label", None) == "create-project":
                inserted.set()
            return result

        with patch("apps.accounts.lifecycle.collect_safe_deletion", hold_after_handoff), patch.object(Project, "save", observe_insert), ThreadPoolExecutor(max_workers=2) as pool:
            deleting = pool.submit(self._self_delete, successor)
            creating = None
            early_result = None
            try:
                self.assertTrue(after_handoff.wait(5), "Departure did not finish the ownership handoff")
                creating = pool.submit(self._create_project, "Shared project at the handoff boundary")
                self.assertTrue(inserted.wait(5), "Project INSERT did not reach its deferred FK commit")
                try:
                    early_result = creating.result(timeout=0.3)
                except FutureTimeout:
                    pass
            finally:
                release_delete.set()
            self.assertEqual(deleting.result(timeout=15)[0], 204)
            self.assertIsNotNone(creating)
            created_status, body = creating.result(timeout=15)
        existing.refresh_from_db()
        self.assertEqual(existing.created_by_id, successor.pk)
        if created_status == 201:
            # This failed on 1d96255c: both requests succeeded, but the new
            # project was cascaded without ever passing to the successor.
            self.assertTrue(Project.objects.filter(pk=body["id"], created_by=successor).exists(), "A project acknowledged with 201 disappeared during the ownership handoff")
        else:
            self.assertIsNone(early_result, "A failed pending write must not have been acknowledged before departure")
            self.assertEqual(created_status, "foreign_key_rejected")
        self.assertFalse(User.objects.filter(pk=self.parent.pk).exists())

    def test_pending_project_fk_makes_departure_busy_then_retry_preserves_201_shared_work(self):
        successor = User.objects.create_user(username="handoff-successor", password=self.password, role="parent", family=self.household.family)
        fk_checked, release_create = Event(), Event()
        original_save = Project.save

        def hold_project_fk(project, *args, **kwargs):
            result = original_save(project, *args, **kwargs)
            if getattr(_worker, "label", None) == "create-project":
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                fk_checked.set()
                if not release_create.wait(10):
                    raise TimeoutError("Project creation was not released")
            return result

        with patch.object(Project, "save", hold_project_fk), ThreadPoolExecutor(max_workers=2) as pool:
            creating = pool.submit(self._create_project, "Shared project saved before departure")
            deleting = None
            busy_result = None
            try:
                self.assertTrue(fk_checked.wait(5), "Project FK did not hold its parent reference")
                deleting = pool.submit(self._self_delete, successor)
                try:
                    busy_result = deleting.result(timeout=2)
                except FutureTimeout:
                    pass
            finally:
                release_create.set()
            created_status, body = creating.result(timeout=15)
            self.assertEqual(created_status, 201)
            if busy_result is None and deleting is not None:
                try:
                    deleting.result(timeout=15)
                except IntegrityError:
                    pass  # Drain the failing old implementation before asserting.
        self.assertIsNotNone(busy_result, "Departure must return busy rather than wait for an in-flight FK save")
        self.assertEqual(busy_result[0], 409)
        self.assertTrue(User.objects.filter(pk=self.parent.pk).exists())
        self.assertTrue(Project.objects.filter(pk=body["id"], created_by=self.parent).exists())
        self.assertEqual(self._self_delete(successor)[0], 204)
        self.assertTrue(Project.objects.filter(pk=body["id"], created_by=successor, assigned_to=self.child).exists())

    def test_closure_refuses_pending_proof_fk_then_retry_keeps_cleanup_tracked(self):
        assignment = HomeworkAssignment.objects.create(title="Concurrent proof", subject="math", assigned_to=self.child, created_by=self.parent, due_date="2026-10-17")
        submission = HomeworkSubmission.objects.create(assignment=assignment, user=self.child, timeliness="on_time")
        fk_checked, release_upload = Event(), Event()

        def save_proof():
            close_old_connections()
            try:
                with transaction.atomic():
                    proof = HomeworkProof.objects.create(submission=submission, image="homework_proofs/synthetic-fk-race.png")
                    with connection.cursor() as cursor:
                        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    fk_checked.set()
                    if not release_upload.wait(10):
                        raise TimeoutError("Proof save was not released")
                return proof.pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            uploading = pool.submit(save_proof)
            closing = None
            busy_result = None
            try:
                self.assertTrue(fk_checked.wait(5), "Proof FK did not hold its submission reference")
                closing = pool.submit(self._request, "close", "post", self.close_url, token=self.token.key, data=self._closure_data())
                try:
                    busy_result = closing.result(timeout=2)
                except FutureTimeout:
                    pass
            finally:
                release_upload.set()
            proof_pk = uploading.result(timeout=15)
            if busy_result is None and closing is not None:
                try:
                    closing.result(timeout=15)
                except IntegrityError:
                    pass
        self.assertIsNotNone(busy_result, "Closure must return busy before an in-flight proof save finishes")
        self.assertEqual(busy_result[0], 409)
        self.assertTrue(HomeworkProof.objects.filter(pk=proof_pk).exists())
        self.assertEqual(self._request("retry-close", "post", self.close_url, token=self.token.key, data=self._closure_data())[0], 204)
        from apps.accounts.models import PendingFileDeletion
        self.assertTrue(PendingFileDeletion.objects.filter(storage_key="homework_proofs/synthetic-fk-race.png").exists())

    def test_global_catalog_save_makes_departure_busy_without_deleting_global_art(self):
        successor = User.objects.create_user(username="handoff-successor", password=self.password, role="parent", family=self.household.family)
        sprite = SpriteAsset.objects.create(slug="global-concurrent", image="global-fixture.png", created_by=self.parent, frame_width_px=1, frame_height_px=1)
        row_locked, release_save = Event(), Event()

        def save_global_art():
            close_old_connections()
            try:
                with transaction.atomic():
                    current = SpriteAsset.objects.select_for_update().get(pk=sprite.pk)
                    row_locked.set()
                    if not release_save.wait(10):
                        raise TimeoutError("Global catalog save was not released")
                    current.frame_width_px = 2
                    current.save()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            saving = pool.submit(save_global_art)
            deleting = None
            busy_result = None
            try:
                self.assertTrue(row_locked.wait(5), "Global catalog row was not locked")
                deleting = pool.submit(self._self_delete, successor)
                try:
                    busy_result = deleting.result(timeout=2)
                except FutureTimeout:
                    pass
            finally:
                release_save.set()
            saving.result(timeout=15)
            if busy_result is None and deleting is not None:
                deleting.result(timeout=15)
        self.assertIsNotNone(busy_result, "Departure must not wait on an inverse global catalog save")
        self.assertEqual(busy_result[0], 409)
        sprite.refresh_from_db()
        self.assertEqual(sprite.frame_width_px, 2)
        self.assertEqual(self._self_delete(successor)[0], 204)
        sprite.refresh_from_db()
        self.assertIsNone(sprite.created_by_id)
        self.assertEqual(sprite.image.name, "global-fixture.png")

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
