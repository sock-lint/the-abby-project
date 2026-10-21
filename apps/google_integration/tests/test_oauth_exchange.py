"""Browser-bound Google authorization, using real Abby credentials and writes."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.google_integration.models import CalendarEventMapping, GoogleAccount, GoogleAuthInvalidation, GoogleOAuthTransaction
from apps.google_integration.services import GoogleAuthService
from config.tests.factories import make_family


BASE = "/api/auth/google/"
VERIFIER = "synthetic-browser-proof-" + "a" * 41
GOOGLE_CREDENTIALS = {"token": "synthetic-provider-access", "refresh_token": "synthetic-provider-refresh"}


def challenge(verifier=VERIFIER):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def provider_authorization(*, state):
    return "https://accounts.google.com/o/oauth2/auth?" + urlencode({"state": state}), state, "synthetic-provider-pkce-verifier"


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


@override_settings(
    GOOGLE_CLIENT_ID="synthetic-client.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="synthetic-server-secret",
    GOOGLE_REDIRECT_URI="https://testserver/api/auth/google/callback/",
)
class GoogleExchangeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.household = make_family("Google exchange family", parents=[{"username": "parent"}, {"username": "coparent"}], children=[{"username": "child"}])
        self.parent, self.coparent = self.household.parents
        self.child = self.household.children[0]
        self.other = make_family("Other Google family", parents=[{"username": "other-parent"}], children=[{"username": "other-child"}])
        self.client = APIClient()
        authorization = patch.object(GoogleAuthService, "get_authorization_url", side_effect=provider_authorization)
        self.provider_authorization = authorization.start()
        self.addCleanup(authorization.stop)
        exchange = patch.object(GoogleAuthService, "exchange_code", return_value=("synthetic-google-subject", "synthetic@example.invalid", GOOGLE_CREDENTIALS))
        self.provider_exchange = exchange.start()
        self.addCleanup(exchange.stop)

    def sign_in(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return token

    def begin(self, *, mode="login", actor=None, target=None, verifier=VERIFIER):
        if actor is None:
            self.client.credentials()
        else:
            self.sign_in(actor)
        query = {"code_challenge": challenge(verifier), "code_challenge_method": "S256"}
        if target is not None:
            query["for_user"] = target.pk
        response = self.client.get(BASE + ("login/" if mode == "login" else ""), query)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), {"authorization_url", "state", "expires_in"})
        self.assertEqual(body["expires_in"], 600)
        self.assertEqual(parse_qs(urlsplit(body["authorization_url"]).query)["state"], [body["state"]])
        return body

    def callback(self, flow, *, claimed=True):
        # Browser navigation from Google does not carry Abby's API header.
        response = APIClient().get(BASE + "callback/", {"state": flow["state"], "code": "synthetic-provider-code"})
        self.assertEqual(response.status_code, 302)
        location = urlsplit(response.url)
        self.assertEqual(location.path, "/")
        self.assertEqual(location.query, "")
        for secret in ("synthetic-provider-code", *GOOGLE_CREDENTIALS.values()):
            self.assertNotIn(secret, response.url)
        fragment = parse_qs(location.fragment)
        if claimed:
            self.assertEqual(fragment.get("google_state"), [flow["state"]])
        else:
            self.assertNotIn("google_state", fragment)
        return fragment

    def ticket(self, flow):
        fragment = self.callback(flow)
        self.assertIn("google_exchange", fragment, fragment)
        value = fragment["google_exchange"][0]
        self.assertRegex(value, r"^[A-Za-z0-9_-]{43}$")
        return value

    def redeem(self, ticket, *, verifier=VERIFIER):
        return self.client.post(BASE + "exchange/", {"exchange_code": ticket, "code_verifier": verifier}, format="json")

    def linked(self, user=None):
        return GoogleAuthService.link_account(user or self.parent, "synthetic-google-subject", "synthetic@example.invalid", {"token": "synthetic-old-provider-token"})

    def transaction(self, flow):
        return GoogleOAuthTransaction.objects.get(state_hash=hashlib.sha256(flow["state"].encode()).hexdigest())

    def assert_failure(self, response, code):
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(set(response.json()), {"error", "code"})
        self.assertEqual(response.json()["code"], code)
        for secret in (*GOOGLE_CREDENTIALS.values(), VERIFIER):
            self.assertNotIn(secret, response.content.decode())

    def test_config_is_side_effect_free_and_public_without_server_secrets(self):
        for configured, values in ((True, {}), (False, {"GOOGLE_CLIENT_SECRET": ""})):
            with self.subTest(configured=configured), override_settings(**values):
                response = self.client.get(BASE + "config/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"configured": configured})
        self.assertFalse(GoogleOAuthTransaction.objects.exists())
        self.provider_authorization.assert_not_called()

    def test_init_requires_s256_proof_before_creating_a_transaction(self):
        invalid = ({}, {"code_challenge": challenge()}, {"code_challenge": challenge(), "code_challenge_method": "plain"}, {"code_challenge": "bad", "code_challenge_method": "S256"}, {"code_challenge": "+" * 43, "code_challenge_method": "S256"})
        for query in invalid:
            with self.subTest(query=query):
                self.assertEqual(self.client.get(BASE + "login/", query).status_code, 400)
        self.assertFalse(GoogleOAuthTransaction.objects.exists())
        self.provider_authorization.assert_not_called()

    def test_callback_stages_encrypted_material_without_linking_or_minting_a_token(self):
        flow = self.begin()
        ticket = self.ticket(flow)
        row = self.transaction(flow)
        stored = json.dumps(list(GoogleOAuthTransaction.objects.values()), default=str)
        for secret in (flow["state"], ticket, VERIFIER, "synthetic-provider-pkce-verifier", *GOOGLE_CREDENTIALS.values()):
            self.assertNotIn(secret, stored)
        self.assertTrue(row.encrypted_payload)
        self.assertFalse(GoogleAccount.objects.exists())
        self.assertFalse(Token.objects.exists())
        self.provider_exchange.assert_called_once_with("synthetic-provider-code", "synthetic-provider-pkce-verifier")

    def test_staff_login_preserves_current_account_authoring_identity(self):
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        self.linked()
        response = self.redeem(self.ticket(self.begin()))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["user"]["is_staff"], True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.json()['token']}")
        self.assertIs(self.client.get("/api/auth/me/").json()["is_staff"], True)

    def test_login_exchanges_once_and_preserves_existing_shared_token_and_calendar_settings(self):
        account = self.linked()
        account.calendar_sync_enabled, account.calendar_id = True, "synthetic-owned-calendar"
        account.save(update_fields=["calendar_sync_enabled", "calendar_id"])
        mapping = CalendarEventMapping.objects.create(user=self.parent, content_type="chore", object_id=91, google_event_id="synthetic-calendar-event")
        token = Token.objects.create(user=self.parent)
        old_credentials = bytes(account.encrypted_credentials)
        flow = self.begin()
        ticket = self.ticket(flow)
        account.refresh_from_db()
        self.assertEqual(bytes(account.encrypted_credentials), old_credentials)
        response = self.redeem(ticket)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["mode"], "login")
        self.assertEqual(response.json()["token"], token.key)
        self.assertEqual(response.json()["user"]["id"], self.parent.pk)
        self.assertEqual(response.json()["user"]["family"]["id"], self.household.family.pk)
        self.assertEqual(Token.objects.filter(user=self.parent).count(), 1)
        account.refresh_from_db()
        self.assertEqual(GoogleAuthService.decrypt_credentials(account.encrypted_credentials), GOOGLE_CREDENTIALS)
        self.assertTrue(account.calendar_sync_enabled)
        self.assertEqual(account.calendar_id, "synthetic-owned-calendar")
        self.assertTrue(CalendarEventMapping.objects.filter(pk=mapping.pk).exists())
        self.assert_failure(self.redeem(ticket), "invalid_exchange")
        self.assertFalse(self.transaction(flow).encrypted_payload)

    def test_stolen_ticket_wrong_tab_proof_does_not_consume_legitimate_exchange(self):
        self.linked()
        ticket = self.ticket(self.begin())
        self.assert_failure(self.redeem(ticket, verifier="b" * 64), "invalid_exchange")
        self.assertFalse(Token.objects.exists())
        self.assertEqual(self.redeem(ticket).status_code, 200)

    def test_callback_is_single_use_and_replay_cannot_destroy_first_ticket(self):
        self.linked()
        flow = self.begin()
        ticket = self.ticket(flow)
        self.assertIn("google_error", self.callback(flow, claimed=False))
        self.provider_exchange.assert_called_once()
        self.assertEqual(self.redeem(ticket).status_code, 200)

    def test_expired_state_never_calls_google_and_expired_return_cannot_mint_token(self):
        self.linked()
        flow = self.begin()
        GoogleOAuthTransaction.objects.filter(pk=self.transaction(flow).pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIn("google_error", self.callback(flow, claimed=False))
        self.provider_exchange.assert_not_called()
        fresh = self.begin()
        ticket = self.ticket(fresh)
        GoogleOAuthTransaction.objects.filter(pk=self.transaction(fresh).pk).update(exchange_expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_failure(self.redeem(ticket), "invalid_exchange")
        self.assertFalse(Token.objects.exists())

    def test_link_requires_captured_parent_credential_and_defers_the_write_until_exchange(self):
        flow = self.begin(mode="link", actor=self.parent, target=self.child)
        credential = Token.objects.get(user=self.parent)
        ticket = self.ticket(flow)
        self.assertFalse(GoogleAccount.objects.exists())
        self.assertEqual(Token.objects.count(), 1)
        response = self.redeem(ticket)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"mode": "link", "linked": True})
        account = GoogleAccount.objects.get(user=self.child)
        self.assertEqual(account.linked_by_id, self.parent.pk)
        self.assertFalse(account.calendar_sync_enabled)
        self.assertTrue(Token.objects.filter(pk=credential.key).exists())
        self.assertFalse(Token.objects.filter(user=self.child).exists())

    def test_linking_authority_is_scoped_to_self_or_same_family_child(self):
        query = {"code_challenge": challenge(), "code_challenge_method": "S256"}
        self.assertEqual(self.client.get(BASE, query).status_code, 401)
        self.sign_in(self.child)
        self.assertEqual(self.client.get(BASE, {**query, "for_user": self.parent.pk}).status_code, 403)
        self.sign_in(self.parent)
        self.assertEqual(self.client.get(BASE, {**query, "for_user": self.other.children[0].pk}).status_code, 404)
        self.assertFalse(GoogleOAuthTransaction.objects.exists())
        own = self.begin(mode="link", actor=self.child)
        self.assertEqual(self.redeem(self.ticket(own)).status_code, 200)
        self.assertIsNone(GoogleAccount.objects.get(user=self.child).linked_by_id)

    def test_linked_subject_collision_cannot_replace_another_family_account(self):
        account = self.linked(self.other.parents[0])
        before = bytes(account.encrypted_credentials)
        ticket = self.ticket(self.begin(mode="link", actor=self.parent, target=self.child))
        self.assert_failure(self.redeem(ticket), "already_linked_other")
        account.refresh_from_db()
        self.assertEqual(bytes(account.encrypted_credentials), before)
        self.assertFalse(GoogleAccount.objects.filter(user=self.child).exists())

    def test_signin_does_not_create_accounts_or_match_an_unlinked_email(self):
        self.parent.email = "synthetic@example.invalid"
        self.parent.save(update_fields=["email"])
        users_before = get_user_model().objects.count()
        ticket = self.ticket(self.begin())
        self.assert_failure(self.redeem(ticket), "no_account")
        self.assertEqual(get_user_model().objects.count(), users_before)
        self.assertFalse(Token.objects.exists())

    def test_deleted_link_initiator_or_target_cannot_complete_a_staged_callback(self):
        for departing in (self.parent, self.child):
            with self.subTest(departing=departing.role):
                # Separate nested rollback leaves the real saved identities
                # available for the second complete endpoint workflow.
                from django.db import transaction

                with transaction.atomic():
                    ticket = self.ticket(self.begin(mode="link", actor=self.parent, target=self.child))
                    get_user_model().objects.get(pk=departing.pk).delete()
                    self.client.credentials()
                    self.assert_failure(self.redeem(ticket), "invalid_exchange")
                    self.assertFalse(GoogleAccount.objects.exists())
                    transaction.set_rollback(True)

    def test_link_revalidates_both_members_family_role_password_and_activation(self):
        from django.db import transaction

        changes = ((self.parent, "family", self.other.family), (self.child, "family", self.other.family), (self.parent, "role", "child"), (self.child, "role", "parent"), (self.parent, "password", "changed"), (self.child, "password", "changed"), (self.parent, "is_active", False), (self.child, "is_active", False))
        for member, field, value in changes:
            with self.subTest(member=member.username, field=field), transaction.atomic():
                cache.clear()
                ticket = self.ticket(self.begin(mode="link", actor=self.parent, target=self.child))
                fresh = get_user_model().objects.get(pk=member.pk)
                if field == "password":
                    fresh.set_password(value)
                else:
                    setattr(fresh, field, value)
                fresh.save(update_fields=[field])
                response = self.redeem(ticket)
                if member.pk == self.parent.pk and field == "is_active":
                    # Invalid request credentials fail DRF authentication
                    # before the exchange's own authorization checks.
                    self.assertEqual(response.status_code, 401)
                else:
                    self.assert_failure(response, "authorization_changed")
                self.assertFalse(GoogleAccount.objects.exists())
                transaction.set_rollback(True)

    def test_link_rejects_changed_initiating_token_and_another_accounts_credential(self):
        for changed in ("revoked", "replaced", "other-account"):
            with self.subTest(changed=changed):
                from django.db import transaction

                with transaction.atomic():
                    ticket = self.ticket(self.begin(mode="link", actor=self.parent, target=self.child))
                    if changed == "other-account":
                        self.sign_in(self.other.parents[0])
                    else:
                        Token.objects.filter(user=self.parent).delete()
                        if changed == "replaced":
                            self.sign_in(self.parent)
                        else:
                            self.client.credentials()
                    self.assert_failure(self.redeem(ticket), "authorization_changed")
                    self.assertFalse(GoogleAccount.objects.exists())
                    transaction.set_rollback(True)

    def test_anonymous_login_started_before_revocation_cannot_revive_authorization(self):
        from django.db import transaction

        for change in ("logout", "password-reset", "self-password-reset", "password-save", "deactivate-reactivate", "move-back", "token-queryset-delete", "unlink-relink"):
            for moment in ("before-callback", "after-callback"):
                with self.subTest(change=change, moment=moment), transaction.atomic():
                    cache.clear()
                    self.linked()
                    token = Token.objects.create(user=self.parent)
                    flow = self.begin()
                    ticket = self.ticket(flow) if moment == "after-callback" else None
                    if change == "logout":
                        api = APIClient()
                        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
                        self.assertEqual(api.post("/api/auth/", {"action": "logout"}, format="json").status_code, 200)
                    elif change == "password-reset":
                        self.sign_in(self.coparent)
                        self.assertEqual(self.client.post(f"/api/parents/{self.parent.pk}/reset-password/", {"password": "new-synthetic-password42"}, format="json").status_code, 204)
                        self.client.credentials()
                    elif change == "self-password-reset":
                        self.sign_in(self.parent)
                        self.assertEqual(self.client.post(f"/api/parents/{self.parent.pk}/reset-password/", {"password": "new-synthetic-password42"}, format="json").status_code, 204)
                        self.assertTrue(Token.objects.filter(pk=token.key).exists())
                        self.client.credentials()
                    elif change == "password-save":
                        fresh = get_user_model().objects.get(pk=self.parent.pk)
                        fresh.set_password("new-synthetic-password42")
                        fresh.save(update_fields=["password"])
                    elif change == "deactivate-reactivate":
                        self.parent.is_active = False
                        self.parent.save(update_fields=["is_active"])
                        self.parent.is_active = True
                        self.parent.save(update_fields=["is_active"])
                    elif change == "move-back":
                        self.parent.family = self.other.family
                        self.parent.save(update_fields=["family"])
                        self.parent.family = self.household.family
                        self.parent.save(update_fields=["family"])
                    elif change == "token-queryset-delete":
                        Token.objects.filter(pk=token.key).delete()
                    else:
                        api = APIClient()
                        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
                        self.assertEqual(api.delete(BASE + "account/").status_code, 204)
                        self.linked()
                    ticket = ticket or self.ticket(flow)
                    self.assert_failure(self.redeem(ticket), "authorization_changed")
                    transaction.set_rollback(True)

    def test_deleting_member_with_a_token_does_not_create_an_orphan_invalidation_marker(self):
        self.linked()
        self.sign_in(self.parent)
        user_id = self.parent.pk
        get_user_model().objects.get(pk=user_id).delete()
        self.assertFalse(Token.objects.filter(user_id=user_id).exists())
        self.assertFalse(GoogleAuthInvalidation.objects.filter(user_id=user_id).exists())

    def test_old_authenticated_logout_preserves_a_new_google_authorization(self):
        self.linked()
        old = Token.objects.create(user=self.parent)
        delayed = APIClient()
        # Model an already-authenticated request paused before password login
        # rotates its real token, as the existing AuthView regression does.
        delayed.force_authenticate(user=self.parent, token=old)
        login = self.client.post("/api/auth/", {"action": "login", "username": self.parent.username, "password": "pw"}, format="json")
        self.assertEqual(login.status_code, 200)
        replacement = login.json()["token"]
        ticket = self.ticket(self.begin())
        self.assertEqual(delayed.post("/api/auth/", {"action": "logout"}, format="json").status_code, 200)
        response = self.redeem(ticket)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["token"], replacement)

    def test_fresh_google_login_after_logout_can_issue_a_new_shared_token(self):
        self.linked()
        old = self.sign_in(self.parent)
        self.assertEqual(self.client.post("/api/auth/", {"action": "logout"}, format="json").status_code, 200)
        response = self.redeem(self.ticket(self.begin()))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotEqual(response.json()["token"], old.key)
        self.assertEqual(Token.objects.filter(user=self.parent).count(), 1)

    def test_database_failure_rolls_back_credential_updates_and_ticket_consumption(self):
        account = self.linked()
        original = bytes(account.encrypted_credentials)
        ticket = self.ticket(self.begin())
        save = GoogleAccount.save

        def save_then_fail(instance, *args, **kwargs):
            save(instance, *args, **kwargs)
            raise DatabaseError("Synthetic auth transaction failure")

        with patch.object(GoogleAccount, "save", save_then_fail), self.assertRaises(DatabaseError):
            self.redeem(ticket)
        account.refresh_from_db()
        self.assertEqual(bytes(account.encrypted_credentials), original)
        self.assertFalse(Token.objects.exists())
        self.assertEqual(self.redeem(ticket).status_code, 200)
        self.assert_failure(self.redeem(ticket), "invalid_exchange")

    def test_init_is_throttled_and_cannot_accumulate_unbounded_pending_transactions(self):
        query = {"code_challenge": challenge(), "code_challenge_method": "S256"}
        rejected = False
        for _ in range(12):
            response = self.client.get(BASE + "login/", query)
            self.assertIn(response.status_code, {200, 400, 429})
            rejected |= response.status_code != 200
        self.assertTrue(rejected)
        self.assertLessEqual(GoogleOAuthTransaction.objects.count(), 10)
        cache.clear()  # Check the durable pending cap independently of rate limiting.
        self.assertEqual(self.client.get(BASE + "login/", query).status_code, 400)

    def test_spoofed_forwarded_headers_cannot_bypass_pending_authorization_limit(self):
        query = {"code_challenge": challenge(), "code_challenge_method": "S256"}
        statuses = [
            self.client.get(
                BASE + "login/", query, REMOTE_ADDR="192.0.2.10",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{index + 1}",
            ).status_code
            for index in range(25)
        ]
        saved = GoogleOAuthTransaction.objects.count()
        self.assertTrue(all(code in {200, 400, 429} for code in statuses), statuses)
        self.assertLessEqual(
            statuses.count(200), 10,
            f"One network peer created {saved} durable authorizations by varying an untrusted header; statuses={statuses}",
        )
        self.assertLessEqual(saved, 10)
        self.assertIn(429, statuses, "Forwarded-header changes must not bypass the Google authorization throttle either")
        # The database cap remains authoritative after a cache restart or
        # throttle eviction, with the same stable network peer identity.
        for index in range(15):
            cache.clear()
            response = self.client.get(
                BASE + "login/", query, REMOTE_ADDR="192.0.2.10",
                HTTP_X_FORWARDED_FOR=f"203.0.113.{index + 1}",
            )
            self.assertEqual(response.status_code, 400)
        self.assertLessEqual(GoogleOAuthTransaction.objects.count(), 10)

    def test_completed_and_failed_flows_do_not_block_a_fresh_attempt(self):
        for _ in range(10):
            flow = self.begin()
            row = self.transaction(flow)
            GoogleOAuthTransaction.objects.filter(pk=row.pk).update(stage="consumed" if _ % 2 else "failed", encrypted_payload=b"")
            cache.clear()
        self.assertEqual(self.begin()["expires_in"], 600)

    def test_global_retained_transaction_limit_fails_closed_until_expiry_cleanup_frees_capacity(self):
        from apps.google_integration.oauth_exchange import prune_expired

        query = {"code_challenge": challenge(), "code_challenge_method": "S256"}
        with patch("apps.google_integration.oauth_exchange.MAX_TRANSACTIONS", 3):
            for index in range(3):
                response = self.client.get(BASE + "login/", query, REMOTE_ADDR=f"192.0.2.{index + 1}")
                self.assertEqual(response.status_code, 200, response.content)
            rows = list(GoogleOAuthTransaction.objects.order_by("pk"))
            GoogleOAuthTransaction.objects.filter(pk=rows[0].pk).update(stage="consumed", encrypted_payload=b"")
            GoogleOAuthTransaction.objects.filter(pk=rows[1].pk).update(expires_at=timezone.now() - timedelta(seconds=1))
            blocked = self.client.get(BASE + "login/", query, REMOTE_ADDR="192.0.2.4")
            self.assertEqual(blocked.status_code, 503, blocked.content)
            self.assertEqual(set(blocked.json()), {"error", "code"})
            self.assertEqual(blocked.json()["code"], "authorization_busy")
            self.assertEqual(GoogleOAuthTransaction.objects.count(), 3)
            self.assertEqual(prune_expired(limit=1), 1)
            retry = self.client.get(BASE + "login/", query, REMOTE_ADDR="192.0.2.4")
            self.assertEqual(retry.status_code, 200, retry.content)
            self.assertEqual(GoogleOAuthTransaction.objects.count(), 3)
            self.assertTrue(GoogleOAuthTransaction.objects.filter(pk=rows[0].pk, stage="consumed").exists())
            for secret in (VERIFIER, "synthetic-provider-pkce-verifier", "synthetic-server-secret"):
                self.assertNotIn(secret, blocked.content.decode())

    def test_expired_credentials_are_pruned_in_bounded_batches_without_removing_live_flow(self):
        from apps.google_integration.oauth_exchange import prune_expired

        live = self.begin()
        expired = [self.begin() for _ in range(3)]
        for flow in expired:
            GoogleOAuthTransaction.objects.filter(pk=self.transaction(flow).pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(prune_expired(limit=2), 2)
        self.assertEqual(GoogleOAuthTransaction.objects.count(), 2)
        self.assertEqual(prune_expired(limit=2), 1)
        self.assertTrue(GoogleOAuthTransaction.objects.filter(pk=self.transaction(live).pk).exists())

    def test_expired_pending_verifiers_are_boundedly_erased_and_capacity_is_reusable(self):
        from apps.google_integration.oauth_exchange import prune_expired

        flows = [self.begin() for _ in range(10)]
        rows = [self.transaction(flow) for flow in flows]
        self.assertTrue(all(row.encrypted_payload for row in rows))
        self.assertTrue(all(
            GoogleAuthService.decrypt_credentials(row.encrypted_payload)["code_verifier"] == "synthetic-provider-pkce-verifier"
            for row in rows
        ))
        expired_ids = [row.pk for row in rows[:3]]
        retained_ids = [row.pk for row in rows[3:]]
        GoogleOAuthTransaction.objects.filter(pk__in=expired_ids).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(prune_expired(limit=2), 2)
        self.assertEqual(GoogleOAuthTransaction.objects.filter(pk__in=expired_ids).count(), 1)
        self.assertEqual(GoogleOAuthTransaction.objects.filter(pk__in=retained_ids).count(), 7)
        cache.clear()
        self.assertEqual(self.begin()["expires_in"], 600)
        self.assertEqual(prune_expired(limit=2), 1)
        self.assertEqual(GoogleOAuthTransaction.objects.count(), 8)
        self.assertFalse(GoogleOAuthTransaction.objects.filter(pk__in=expired_ids).exists())
        self.assertEqual(GoogleOAuthTransaction.objects.filter(pk__in=retained_ids).count(), 7)

    def test_short_return_expiry_erases_staged_credentials_before_initial_state_expiry(self):
        from apps.google_integration.oauth_exchange import prune_expired

        flow = self.begin()
        self.ticket(flow)
        row = self.transaction(flow)
        self.assertGreater(row.expires_at, timezone.now())
        GoogleOAuthTransaction.objects.filter(pk=row.pk).update(exchange_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(prune_expired(limit=1), 1)
        self.assertFalse(GoogleOAuthTransaction.objects.filter(pk=row.pk).exists())

    def test_inactive_or_deleted_linked_account_never_receives_a_new_token(self):
        self.linked()
        flow = self.begin()
        ticket = self.ticket(flow)
        self.parent.is_active = False
        self.parent.save(update_fields=["is_active"])
        response = self.redeem(ticket)
        self.assertEqual(response.status_code, 400)
        self.assertIn(response.json()["code"], {"inactive", "authorization_changed"})
        self.assertFalse(Token.objects.exists())
        self.parent.delete()
        self.assertNotEqual(self.redeem(ticket).status_code, 200)

    def test_provider_errors_are_allowlisted_and_do_not_echo_secrets_to_urls_or_logs(self):
        marker = "synthetic-sensitive-provider-text&token=" + "b" * 40
        flow = self.begin()
        handler = _LogCapture()
        logging.getLogger().addHandler(handler)
        try:
            injected = APIClient().get(BASE + "callback/", {"state": flow["state"], "error": marker})
            self.assertEqual(injected.status_code, 302)
            self.assertEqual(urlsplit(injected.url).query, "")
            self.assertNotIn(marker, injected.url)
            self.assertIn("google_error", parse_qs(urlsplit(injected.url).fragment))
            self.provider_exchange.assert_not_called()
            flow = self.begin()
            self.provider_exchange.side_effect = RuntimeError(marker)
            self.assertIn("google_error", self.callback(flow))
        finally:
            logging.getLogger().removeHandler(handler)
        text = "\n".join(handler.messages)
        for secret in (marker, "synthetic-provider-code", VERIFIER, *GOOGLE_CREDENTIALS.values()):
            self.assertNotIn(secret, text)

    def test_exchange_accepts_only_post_and_validates_proof_without_side_effects(self):
        self.assertEqual(self.client.get(BASE + "exchange/").status_code, 405)
        for data in ({}, {"exchange_code": "a" * 43}, {"exchange_code": "a" * 43, "code_verifier": "short"}, {"exchange_code": "a" * 43, "code_verifier": VERIFIER, "user_id": self.child.pk}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(BASE + "exchange/", data, format="json").status_code, 400)
        self.assertFalse(Token.objects.exists())
        self.assertFalse(GoogleAccount.objects.exists())


@override_settings(
    GOOGLE_CLIENT_ID="synthetic-client.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="synthetic-server-secret",
    GOOGLE_REDIRECT_URI="https://testserver/api/auth/google/callback/",
)
class GoogleProviderPkceCompatibilityTests(TestCase):
    def test_real_google_authorization_keeps_provider_pkce_and_calendar_scope_separate_from_drive(self):
        url, state, verifier = GoogleAuthService.get_authorization_url(state="s" * 43)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(state, "s" * 43)
        self.assertRegex(verifier, r"^[A-Za-z0-9._~-]{43,128}$")
        self.assertEqual(query["code_challenge"], [challenge(verifier)])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(set(query["scope"][0].split()), {"openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/calendar.events.owned"})
        self.assertNotIn("drive.file", query["scope"][0])
