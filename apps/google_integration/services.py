import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Google OAuth scopes
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar.events",
]


def _derive_key():
    """Derive a 32-byte key from Django's SECRET_KEY for AES-like encryption."""
    return hashlib.sha256(settings.SECRET_KEY.encode()).digest()


def _encrypt(plaintext_bytes):
    """Simple HMAC-authenticated encryption using XOR with a derived key stream.

    Format: salt (16) || ciphertext || hmac (32)
    This is simpler than Fernet but avoids the `cryptography` C-extension
    dependency which can be fragile in some environments.
    """
    key = _derive_key()
    salt = os.urandom(16)
    # Derive a key stream via repeated HMAC
    stream = b""
    block = salt
    while len(stream) < len(plaintext_bytes):
        block = hmac.new(key, block, hashlib.sha256).digest()
        stream += block
    ciphertext = bytes(a ^ b for a, b in zip(plaintext_bytes, stream))
    tag = hmac.new(key, salt + ciphertext, hashlib.sha256).digest()
    return salt + ciphertext + tag


def _decrypt(encrypted_bytes):
    """Decrypt data encrypted by _encrypt(). Raises ValueError on tamper."""
    key = _derive_key()
    if len(encrypted_bytes) < 48:  # 16 salt + 0 data + 32 hmac
        raise ValueError("Encrypted data too short")
    salt = encrypted_bytes[:16]
    tag = encrypted_bytes[-32:]
    ciphertext = encrypted_bytes[16:-32]
    expected_tag = hmac.new(key, salt + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Credential integrity check failed")
    stream = b""
    block = salt
    while len(stream) < len(ciphertext):
        block = hmac.new(key, block, hashlib.sha256).digest()
        stream += block
    return bytes(a ^ b for a, b in zip(ciphertext, stream))


class GoogleAuthService:
    """Handles OAuth2 flow and credential management."""

    @staticmethod
    def is_configured():
        """Return True if Google OAuth credentials are set."""
        return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)

    @staticmethod
    def get_authorization_url(state=None):
        """Build the Google OAuth consent URL.

        Returns (authorization_url, state).
        """
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return authorization_url, state

    @staticmethod
    def exchange_code(code):
        """Exchange authorization code for credentials.

        Returns (google_id, email, credentials_json).
        """
        import google.auth.transport.requests
        from google.oauth2 import id_token as google_id_token
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Verify the ID token to get user info
        request = google.auth.transport.requests.Request()
        id_info = google_id_token.verify_oauth2_token(
            credentials.id_token, request, settings.GOOGLE_CLIENT_ID
        )
        google_id = id_info["sub"]
        email = id_info.get("email", "")

        credentials_json = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or []),
        }
        if credentials.expiry:
            credentials_json["expiry"] = credentials.expiry.isoformat()

        return google_id, email, credentials_json

    @staticmethod
    def encrypt_credentials(credentials_json):
        """Encrypt a credentials dict. Returns bytes."""
        return _encrypt(json.dumps(credentials_json).encode())

    @staticmethod
    def decrypt_credentials(encrypted):
        """Decrypt encrypted credentials. Returns dict."""
        return json.loads(_decrypt(bytes(encrypted)).decode())

    @classmethod
    def get_google_credentials(cls, google_account):
        """Build a google.oauth2.credentials.Credentials from a GoogleAccount."""
        from google.oauth2.credentials import Credentials

        creds_data = cls.decrypt_credentials(google_account.encrypted_credentials)
        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_data.get("client_id", settings.GOOGLE_CLIENT_ID),
            client_secret=creds_data.get("client_secret", settings.GOOGLE_CLIENT_SECRET),
            scopes=creds_data.get("scopes"),
        )
        if creds_data.get("expiry"):
            creds.expiry = datetime.fromisoformat(creds_data["expiry"])
        return creds

    @classmethod
    def refresh_if_needed(cls, google_account):
        """Refresh credentials if expired and save back."""
        import google.auth.transport.requests

        creds = cls.get_google_credentials(google_account)
        if creds.expired and creds.refresh_token:
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            # Persist refreshed token
            creds_data = cls.decrypt_credentials(google_account.encrypted_credentials)
            creds_data["token"] = creds.token
            if creds.expiry:
                creds_data["expiry"] = creds.expiry.isoformat()
            google_account.encrypted_credentials = cls.encrypt_credentials(creds_data)
            google_account.save(update_fields=["encrypted_credentials", "updated_at"])
        return creds

    @classmethod
    def link_account(cls, user, google_id, email, credentials_json, linked_by=None):
        """Create or update a GoogleAccount for the given user."""
        from .models import GoogleAccount

        encrypted = cls.encrypt_credentials(credentials_json)
        account, created = GoogleAccount.objects.update_or_create(
            user=user,
            defaults={
                "google_id": google_id,
                "google_email": email,
                "encrypted_credentials": encrypted,
                "linked_by": linked_by,
            },
        )
        return account

    @staticmethod
    def unlink_account(user):
        """Remove the user's GoogleAccount and all calendar mappings."""
        from .models import CalendarEventMapping, GoogleAccount

        CalendarEventMapping.objects.filter(user=user).delete()
        GoogleAccount.objects.filter(user=user).delete()


class GoogleCalendarService:
    """Pushes app events to Google Calendar."""

    @classmethod
    def get_calendar_client(cls, user):
        """Build an authenticated Calendar API client for a user.

        Returns None if the user has no linked account or sync is disabled.
        """
        from .models import GoogleAccount

        try:
            account = user.google_account
        except GoogleAccount.DoesNotExist:
            return None

        if not account.calendar_sync_enabled:
            return None

        try:
            creds = GoogleAuthService.refresh_if_needed(account)
        except Exception:
            logger.exception("Failed to refresh Google credentials for user %s", user)
            return None

        from googleapiclient.discovery import build

        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    @classmethod
    def _upsert_event(cls, user, content_type, object_id, event_body, calendar_id="primary"):
        """Create or update a Google Calendar event and maintain the mapping."""
        from .models import CalendarEventMapping, GoogleAccount

        service = cls.get_calendar_client(user)
        if service is None:
            return

        try:
            cal_id = user.google_account.calendar_id or "primary"
        except GoogleAccount.DoesNotExist:
            return

        mapping = CalendarEventMapping.objects.filter(
            user=user, content_type=content_type, object_id=object_id
        ).first()

        try:
            if mapping:
                # Update existing event
                event = (
                    service.events()
                    .update(calendarId=cal_id, eventId=mapping.google_event_id, body=event_body)
                    .execute()
                )
            else:
                # Create new event
                event = (
                    service.events()
                    .insert(calendarId=cal_id, body=event_body)
                    .execute()
                )
                CalendarEventMapping.objects.create(
                    user=user,
                    content_type=content_type,
                    object_id=object_id,
                    google_event_id=event["id"],
                )
        except Exception:
            logger.exception(
                "Google Calendar API error for %s:%s (user %s)",
                content_type,
                object_id,
                user,
            )

    @classmethod
    def delete_event(cls, user, content_type, object_id):
        """Remove a Google Calendar event by mapping lookup."""
        from .models import CalendarEventMapping, GoogleAccount

        mapping = CalendarEventMapping.objects.filter(
            user=user, content_type=content_type, object_id=object_id
        ).first()
        if not mapping:
            return

        service = cls.get_calendar_client(user)
        if service is None:
            mapping.delete()
            return

        try:
            cal_id = user.google_account.calendar_id or "primary"
        except GoogleAccount.DoesNotExist:
            mapping.delete()
            return

        try:
            service.events().delete(calendarId=cal_id, eventId=mapping.google_event_id).execute()
        except Exception:
            logger.exception(
                "Failed to delete Google Calendar event %s for user %s",
                mapping.google_event_id,
                user,
            )
        mapping.delete()

    @classmethod
    def sync_project_due_date(cls, project):
        """Create/update an all-day event for a project's due date."""
        if not project.due_date or not project.assigned_to_id:
            return

        event_body = {
            "summary": f"[Abby] {project.title} due",
            "description": f"Project deadline for {project.assigned_to}",
            "start": {"date": str(project.due_date)},
            "end": {"date": str(project.due_date)},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 1440},  # 1 day before
                    {"method": "popup", "minutes": 60},  # 1 hour before
                ],
            },
        }
        cls._upsert_event(project.assigned_to, "project_due", project.id, event_body)

    @classmethod
    def sync_chore(cls, chore):
        """Create/update a recurring calendar event for a chore."""
        from apps.projects.models import User

        tz = settings.TIME_ZONE
        today = timezone.localdate()

        # Build recurrence rule based on chore frequency
        if chore.recurrence == "daily":
            rrule = "RRULE:FREQ=DAILY"
        elif chore.recurrence == "weekly":
            rrule = "RRULE:FREQ=WEEKLY"
        else:
            # one_time — no recurrence
            rrule = None

        event_body = {
            "summary": f"[Abby] {chore.title}",
            "description": f"Chore — reward: ${chore.reward_amount}",
            "start": {"date": str(today), "timeZone": tz},
            "end": {"date": str(today), "timeZone": tz},
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 30}],
            },
        }
        if rrule:
            event_body["recurrence"] = [rrule]

        # Sync to all child users (chores aren't assigned to a specific child)
        children = User.objects.filter(role="child")
        for child in children:
            cls._upsert_event(child, "chore", chore.id, event_body)

    @classmethod
    def sync_time_entry(cls, time_entry):
        """Create a time block for a completed time entry."""
        if not time_entry.clock_out or not time_entry.user_id:
            return

        tz = settings.TIME_ZONE
        event_body = {
            "summary": f"[Abby] Worked on: {time_entry.project.title}",
            "start": {
                "dateTime": time_entry.clock_in.isoformat(),
                "timeZone": tz,
            },
            "end": {
                "dateTime": time_entry.clock_out.isoformat(),
                "timeZone": tz,
            },
        }
        cls._upsert_event(time_entry.user, "time_entry", time_entry.id, event_body)

    @classmethod
    def full_sync(cls, user):
        """Manually trigger a full resync of all events for a user."""
        from apps.chores.models import Chore
        from apps.projects.models import Project
        from apps.timecards.models import TimeEntry

        # Sync project due dates
        projects = Project.objects.filter(assigned_to=user, due_date__isnull=False)
        for project in projects:
            cls.sync_project_due_date(project)

        # Sync completed time entries (last 30 days)
        cutoff = timezone.now() - timedelta(days=30)
        entries = TimeEntry.objects.filter(
            user=user, status="completed", clock_out__isnull=False, clock_in__gte=cutoff
        )
        for entry in entries:
            cls.sync_time_entry(entry)

        # Sync active chores
        chores = Chore.objects.filter(is_active=True)
        for chore in chores:
            cls._upsert_event(
                user,
                "chore",
                chore.id,
                {
                    "summary": f"[Abby] {chore.title}",
                    "description": f"Chore — reward: ${chore.reward_amount}",
                    "start": {"date": str(timezone.localdate()), "timeZone": settings.TIME_ZONE},
                    "end": {"date": str(timezone.localdate()), "timeZone": settings.TIME_ZONE},
                    "reminders": {
                        "useDefault": False,
                        "overrides": [{"method": "popup", "minutes": 30}],
                    },
                    **(
                        {"recurrence": ["RRULE:FREQ=DAILY"]}
                        if chore.recurrence == "daily"
                        else {"recurrence": ["RRULE:FREQ=WEEKLY"]}
                        if chore.recurrence == "weekly"
                        else {}
                    ),
                },
            )
