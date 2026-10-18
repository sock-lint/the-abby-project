"""Browser-proof Google return protocol, separate from Google's own PKCE.

Locks: ordered User rows (NO KEY UPDATE), Token, transaction, GoogleAccount.
Provider requests happen after the callback claim commits, without row locks.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.db.models.functions import Now
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException

from .models import GoogleAccount, GoogleAuthInvalidation, GoogleOAuthAdmission, GoogleOAuthTransaction
from .services import GoogleAuthService, _decrypt, _encrypt
from .throttling import google_client_identity

OPAQUE = re.compile(r"^[A-Za-z0-9_-]{43}$")
VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
MAX_TRANSACTIONS = 1000
MESSAGES = {
    "invalid_exchange": "This Google authorization expired or was already used. Start again.",
    "authorization_changed": "Your account or authorization changed. Start again.",
    "no_account": "This Google account is not linked. Sign in with your password to link it.",
    "inactive": "This account is inactive.",
    "already_linked_other": "This Google account is already linked to another account.",
    "authorization_busy": "Google authorization is busy. Please try again later.",
}


class ExchangeError(Exception):
    def __init__(self, code="invalid_exchange"):
        self.code = code
        super().__init__(MESSAGES[code])


class CapacityError(ExchangeError):
    http_status = 503

    def __init__(self):
        super().__init__("authorization_busy")


class AuthorizationBusy(APIException):
    status_code = 409
    default_detail = "Your account is changing. Please try again."
    default_code = "authorization_changed"


def is_lock_conflict(exc):
    cause = exc.__cause__
    return (getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)) == "55P03"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def invalidate_google_flows(user_id, *, using="default"):
    """Caller holds the User row lock, in the same transaction as revocation."""
    try:
        with transaction.atomic(using=using):
            # Legacy cascades may already hold this subordinate row while
            # waiting to delete User. Fail the competing mutation atomically.
            list(GoogleAuthInvalidation.objects.using(using).select_for_update(nowait=True)
                 .filter(user_id=user_id))
            GoogleAuthInvalidation.objects.using(using).update_or_create(
                user_id=user_id, defaults={"invalidated_at": Now()},
            )
    except OperationalError as exc:
        if is_lock_conflict(exc):
            raise AuthorizationBusy() from None
        raise


def lock_users(ids):
    return {u.pk: u for u in get_user_model().objects.select_for_update(no_key=True)
            .filter(pk__in=sorted(set(ids))).order_by("pk")}


def _seal(value):
    return _encrypt(json.dumps(value).encode())


def _open(value):
    return json.loads(_decrypt(value))


def start(request, *, mode, target=None):
    challenge = request.query_params.get("code_challenge", "")
    if not OPAQUE.fullmatch(challenge) or request.query_params.get("code_challenge_method") != "S256":
        raise ExchangeError()
    state = secrets.token_urlsafe(32)
    # Google's verifier and this browser's verifier are independent secrets.
    url, _, provider_verifier = GoogleAuthService.get_authorization_url(state=state)
    actor = request.user if request.user.is_authenticated else None
    if actor and not isinstance(request.auth, Token):
        raise ExchangeError("authorization_changed")
    with transaction.atomic():
        users = lock_users([u.pk for u in (actor, target) if u])
        values = {}
        if actor:
            actor = users.get(actor.pk)
            if not actor or not actor.is_active or not Token.objects.filter(
                user=actor, key=request.auth.key,
            ).exists():
                raise ExchangeError("authorization_changed")
            values.update(initiator=actor, initiator_family_id=actor.family_id,
                          initiator_role=actor.role, initiator_password_hash=actor.get_session_auth_hash(),
                          initiator_token_hash=digest(request.auth.key))
        if target:
            target = users.get(target.pk)
            if not target or not target.is_active or not actor or (
                target.pk != actor.pk and (actor.role != "parent" or target.role != "child"
                                           or actor.family_id != target.family_id)
            ):
                raise ExchangeError("authorization_changed")
            values.update(target=target, target_family_id=target.family_id,
                          target_role=target.role, target_password_hash=target.get_session_auth_hash())
        client_hash = salted_hmac("google-oauth-client", google_client_identity(request),
                                 algorithm="sha256").hexdigest()
        now = timezone.now()
        # Count all retained stages, not just live rows: if erasure is down,
        # new authorization fails closed instead of growing storage forever.
        GoogleOAuthAdmission.objects.select_for_update().get_or_create(pk=1)
        if GoogleOAuthTransaction.objects.count() >= MAX_TRANSACTIONS:
            raise CapacityError()
        if GoogleOAuthTransaction.objects.filter(
            client_hash=client_hash, expires_at__gt=now, stage__in=["pending", "processing", "ready"],
        ).count() >= 10:
            raise ExchangeError()
        GoogleOAuthTransaction.objects.create(
            state_hash=digest(state), browser_challenge=challenge, mode=mode,
            client_hash=client_hash, expires_at=now + timedelta(minutes=10),
            encrypted_payload=_seal({"code_verifier": provider_verifier}), **values,
        )
    return {"authorization_url": url, "state": state, "expires_in": 600}


def claim_callback(state):
    if not isinstance(state, str) or not OPAQUE.fullmatch(state):
        return None
    with transaction.atomic():
        flow = GoogleOAuthTransaction.objects.select_for_update().filter(state_hash=digest(state)).first()
        if not flow or flow.stage != "pending" or flow.expires_at <= timezone.now():
            return None
        payload = _open(flow.encrypted_payload)
        flow.stage = "processing"
        flow.encrypted_payload = b""
        flow.save(update_fields=["stage", "encrypted_payload"])
    return flow.pk, payload.get("code_verifier")


def fail_callback(flow_id):
    GoogleOAuthTransaction.objects.filter(pk=flow_id, stage="processing").update(
        stage="failed", encrypted_payload=b"",
    )


def finish_callback(flow_id, google_id, email, credentials):
    ticket = secrets.token_urlsafe(32)
    now = timezone.now()
    updated = GoogleOAuthTransaction.objects.filter(
        pk=flow_id, stage="processing", expires_at__gt=now,
    ).update(stage="ready", exchange_hash=digest(ticket),
             exchange_expires_at=now + timedelta(seconds=90),
             encrypted_payload=_seal({"google_id": google_id, "email": email, "credentials": credentials}))
    return ticket if updated else None


def _unchanged(user, flow, prefix):
    return bool(user and user.is_active
                and user.family_id == getattr(flow, prefix + "_family_id")
                and user.role == getattr(flow, prefix + "_role")
                and hmac.compare_digest(user.get_session_auth_hash(), getattr(flow, prefix + "_password_hash"))
                and not GoogleAuthInvalidation.objects.filter(
                    user=user, invalidated_at__gte=flow.created_at,
                ).exists())


def _validate_actor(request, flow, users):
    actor = users.get(flow.initiator_id)
    if flow.initiator_id:
        if (not _unchanged(actor, flow, "initiator") or not request.user.is_authenticated
                or request.user.pk != actor.pk or not isinstance(request.auth, Token)
                or not hmac.compare_digest(digest(request.auth.key), flow.initiator_token_hash)
                or not Token.objects.select_for_update(nowait=True).filter(user=actor, key=request.auth.key).exists()):
            raise ExchangeError("authorization_changed")
    elif request.user.is_authenticated:
        raise ExchangeError("authorization_changed")
    return actor


def _redeem(request, flow, users, payload):
    actor = _validate_actor(request, flow, users)
    google_id = payload["google_id"]
    if flow.mode == "link":
        target = users.get(flow.target_id)
        if not _unchanged(target, flow, "target") or not actor or (
            target.pk != actor.pk and (actor.role != "parent" or target.role != "child"
                                       or actor.family_id != target.family_id)
        ):
            raise ExchangeError("authorization_changed")
        if GoogleAccount.objects.filter(google_id=google_id).exclude(user=target).exists():
            raise ExchangeError("already_linked_other")
        GoogleAuthService.link_account(target, google_id, payload["email"], payload["credentials"],
                                       actor if actor.pk != target.pk else None)
        return {"mode": "link", "linked": True}
    account = GoogleAccount.objects.select_for_update(nowait=True).filter(google_id=google_id).first()
    if not account:
        raise ExchangeError("no_account")
    user = users.get(account.user_id)
    if not user:
        raise ExchangeError("authorization_changed")
    if not user.is_active:
        raise ExchangeError("inactive")
    if (account.created_at >= flow.created_at or GoogleAuthInvalidation.objects.filter(
        user=user, invalidated_at__gte=flow.created_at,
    ).exists()):
        raise ExchangeError("authorization_changed")
    account.encrypted_credentials = GoogleAuthService.encrypt_credentials(payload["credentials"])
    account.save(update_fields=["encrypted_credentials", "updated_at"])
    token, _ = Token.objects.get_or_create(user=user)  # Documented Google login contract.
    from apps.projects.serializers import UserSerializer
    return {"mode": "login", "token": token.key, "user": UserSerializer(user).data}


def exchange(request):
    ticket = request.data.get("exchange_code")
    verifier = request.data.get("code_verifier")
    if (not isinstance(ticket, str) or not OPAQUE.fullmatch(ticket)
            or not isinstance(verifier, str) or not VERIFIER.fullmatch(verifier)):
        raise ExchangeError()
    snapshot = GoogleOAuthTransaction.objects.filter(exchange_hash=digest(ticket), stage="ready").first()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    if not snapshot or not hmac.compare_digest(challenge, snapshot.browser_challenge):
        raise ExchangeError()  # A bad browser proof never consumes the legitimate ticket.
    try:
        payload = _open(snapshot.encrypted_payload)
    except (ValueError, TypeError, KeyError):
        raise ExchangeError() from None
    ids = [i for i in (snapshot.initiator_id, snapshot.target_id) if i]
    if snapshot.mode == "login":
        owner = GoogleAccount.objects.filter(google_id=payload["google_id"]).values_list("user_id", flat=True).first()
        if owner:
            ids.append(owner)
    result = None
    error = None
    with transaction.atomic():
        users = lock_users(ids)
        # The actor's token lock precedes the flow lock (logout shares User -> Token).
        if snapshot.initiator_id:
            list(Token.objects.select_for_update(nowait=True).filter(user_id=snapshot.initiator_id))
        flow = GoogleOAuthTransaction.objects.select_for_update(nowait=True).filter(pk=snapshot.pk).first()
        now = timezone.now()
        if (not flow or flow.stage != "ready" or flow.expires_at <= now
                or flow.exchange_expires_at <= now):
            raise ExchangeError()
        list(GoogleAccount.objects.select_for_update(nowait=True).filter(user_id__in=users))
        list(GoogleAuthInvalidation.objects.select_for_update(nowait=True).filter(user_id__in=users))
        try:
            # Savepoint keeps a unique Google-ID collision from rolling back consumption.
            with transaction.atomic():
                result = _redeem(request, flow, users, payload)
        except ExchangeError as exc:
            error = exc
        except IntegrityError:
            error = ExchangeError("authorization_changed")
        flow.stage = "consumed"
        flow.encrypted_payload = b""
        flow.exchange_hash = None
        flow.save(update_fields=["stage", "encrypted_payload", "exchange_hash"])
    if error:
        raise error
    return result


def prune_expired(limit=200):
    """Bounded erasure; expiry is enforced even if the periodic task is unavailable."""
    ids = list(GoogleOAuthTransaction.objects.filter(
        Q(expires_at__lte=timezone.now()) | Q(exchange_expires_at__lte=timezone.now()))
               .order_by("expires_at").values_list("pk", flat=True)[:limit])
    GoogleOAuthTransaction.objects.filter(pk__in=ids).delete()
    return len(ids)
