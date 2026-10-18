"""Calendar failures add bounded diagnostics without changing sync or reporting."""
import json
import logging
from unittest.mock import MagicMock, patch

import httplib2
import sentry_sdk
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase
from googleapiclient.errors import HttpError
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from apps.google_integration.models import CalendarEventMapping, GoogleAccount
from apps.google_integration.services import GoogleCalendarService
from config.tests.factories import make_family


INSERT_URI = "https://www.googleapis.com/calendar/v3/calendars/primary/events?alt=json"
UPDATE_URI = "https://www.googleapis.com/calendar/v3/calendars/primary/events/synthetic-event?alt=json"
SECRET = "synthetic-private-provider-data"
DOMAINS = {
    "userRateLimitExceeded": "usageLimits",
    "rateLimitExceeded": "usageLimits",
    "quotaExceeded": "usageLimits",
    "forbiddenForNonOrganizer": "calendar",
}


def provider_error(*, reason="rateLimitExceeded", domain="usageLimits", code=403,
                   status=403, content=None, uri=INSERT_URI):
    if content is None:
        content = json.dumps({"error": {"code": code, "message": SECRET,
                                       "errors": [{"domain": domain, "reason": reason,
                                                   "message": SECRET}]}}).encode()
    return HttpError(httplib2.Response({"status": status, "reason": "Forbidden"}),
                     content, uri=uri)


class CalendarFailureClassificationTests(SimpleTestCase):
    def classify(self, error, operation="insert"):
        from apps.google_integration.diagnostics import calendar_failure_diagnostics
        result = calendar_failure_diagnostics(error, operation=operation)
        self.assertEqual(set(result), {"operation", "status", "reason"})
        self.assertNotIn(SECRET, json.dumps(result))
        return result

    def test_documented_403_reasons_require_their_google_domain(self):
        for reason, domain in DOMAINS.items():
            with self.subTest(reason=reason):
                self.assertEqual(self.classify(provider_error(reason=reason, domain=domain)), {
                    "operation": "insert", "status": 403, "reason": reason,
                })
                self.assertEqual(self.classify(provider_error(reason=reason, domain="foreign"))["reason"],
                                 "unknown")

    def test_unknown_or_inconsistent_payloads_never_claim_a_known_reason(self):
        payloads = [
            provider_error(reason=SECRET), provider_error(code=401),
            provider_error(code="403"), provider_error(code=True),
            provider_error(content=b"not JSON"), provider_error(content=b"\xff"),
            provider_error(content=b"x" * 16385), provider_error(content=b"null"),
            provider_error(content=b"[]"), provider_error(content=b'{"error":null}'),
            provider_error(content=b'{"error":{"code":403,"errors":{}}}'),
            provider_error(content=b'{"error":{"code":403,"errors":[]}}'),
            provider_error(content=b'{"error":{"code":403,"errors":[null]}}'),
            provider_error(content=b'{"error":{"code":403,"errors":[{"domain":"usageLimits","reason":[]} ]}}'),
            provider_error(content=b'{"error":{"code":403,"errors":[{"domain":"usageLimits","reason":"rateLimitExceeded"},{"domain":"calendar","reason":"forbiddenForNonOrganizer"}]}}'),
            provider_error(content=b'{"error":{"code":403,"errors":[{"domain":"usageLimits","reason":"rateLimitExceeded","reason":"quotaExceeded"}]}}'),
            provider_error(content=b'{"error":{"code":403,"details":[{"@type":"type.googleapis.com/google.rpc.ErrorInfo","domain":"foreign","reason":"rateLimitExceeded"}]}}'),
        ]
        for error in payloads:
            with self.subTest(content=error.content[:100]):
                self.assertEqual(self.classify(error)["reason"], "unknown")

    def test_only_matching_http_403_can_receive_a_documented_403_reason(self):
        for status in (401, 404, 429, 500):
            with self.subTest(status=status):
                result = self.classify(provider_error(status=status, code=status))
                self.assertEqual(result["status"], status)
                self.assertEqual(result["reason"], "unknown")

    def test_invalid_response_status_types_are_unknown(self):
        for status in ("403", True, None, 403.0, 99, 600):
            error = provider_error()
            error.resp.status = status
            with self.subTest(status=status):
                self.assertEqual(self.classify(error), {
                    "operation": "insert", "status": None, "reason": "unknown",
                })

    def test_foreign_or_unexpected_uris_do_not_establish_provider_attribution(self):
        for uri in (None, "", "https://example.invalid/calendar/v3/calendars/primary/events",
                    "http://www.googleapis.com/calendar/v3/calendars/primary/events",
                    "https://www.googleapis.com.evil.invalid/calendar/v3/calendars/primary/events",
                    "https://user@www.googleapis.com/calendar/v3/calendars/primary/events",
                    "https://www.googleapis.com:443/calendar/v3/calendars/primary/events",
                    "https://www.googleapis.com/drive/v3/files",
                    UPDATE_URI, INSERT_URI + "#fragment", "https://[bad/calendar"):
            with self.subTest(uri=uri):
                self.assertEqual(self.classify(provider_error(uri=uri)), {
                    "operation": "insert", "status": None, "reason": "unknown",
                })

    def test_wrappers_and_other_errors_never_borrow_chained_provider_diagnostics(self):
        wrapped = DatabaseError(SECRET)
        wrapped.__cause__ = provider_error()
        for error in (wrapped, ValueError(SECRET), None):
            self.assertEqual(self.classify(error), {
                "operation": "insert", "status": None, "reason": "unknown",
            })

    def test_http_error_subclasses_are_not_assumed_to_be_direct_calendar_responses(self):
        class OtherHttpError(HttpError):
            pass

        error = provider_error()
        error.__class__ = OtherHttpError
        self.assertEqual(self.classify(error), {
            "operation": "insert", "status": None, "reason": "unknown",
        })

    def test_update_operation_uses_its_matching_event_endpoint(self):
        self.assertEqual(self.classify(provider_error(uri=UPDATE_URI), "update"), {
            "operation": "update", "status": 403, "reason": "rateLimitExceeded",
        })


class _OfflineTransport(Transport):
    def capture_envelope(self, envelope):
        pass


class CalendarFailureReportingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_family("Calendar diagnostics", children=[{
            "username": "calendar-diagnostic-child",
        }]).children[0]
        cls.account = GoogleAccount.objects.create(
            user=cls.user, google_id="synthetic-google-id",
            google_email="calendar@example.invalid", encrypted_credentials=b"synthetic-unused",
            calendar_sync_enabled=True,
        )

    def setUp(self):
        self.google = MagicMock()
        client_patch = patch.object(GoogleCalendarService, "get_calendar_client", return_value=self.google)
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def sync(self):
        GoogleCalendarService._upsert_event(self.user, "chore", 123, {"summary": SECRET})

    def assert_original_reporting(self, record, error):
        self.assertEqual(record.levelno, logging.ERROR)
        self.assertEqual(record.msg, "Google Calendar API error for %s:%s (user %s)")
        self.assertEqual(record.args, ("chore", 123, self.user))
        self.assertIs(record.exc_info[1], error)
        self.assertNotIn(SECRET, json.dumps(record.google_calendar_failure))

    def test_insert_failure_adds_diagnostics_and_preserves_exception_reporting(self):
        error = provider_error()
        self.google.events.return_value.insert.return_value.execute.side_effect = error
        with self.assertLogs("apps.google_integration.services", level="ERROR") as logged:
            self.sync()
        self.assert_original_reporting(logged.records[0], error)
        self.assertEqual(logged.records[0].google_calendar_failure, {
            "operation": "insert", "status": 403, "reason": "rateLimitExceeded",
        })
        self.google.events.return_value.insert.assert_called_once_with(
            calendarId="primary", body={"summary": SECRET})
        self.google.events.return_value.insert.return_value.execute.assert_called_once_with()
        self.assertFalse(CalendarEventMapping.objects.exists())
        self.account.refresh_from_db()
        self.assertTrue(self.account.calendar_sync_enabled)
        self.assertEqual(self.account.calendar_id, "primary")

    def test_update_failure_keeps_mapping_and_does_not_retry_or_insert(self):
        mapping = CalendarEventMapping.objects.create(user=self.user, content_type="chore", object_id=123,
                                                       google_event_id="synthetic-event")
        error = provider_error(uri=UPDATE_URI)
        self.google.events.return_value.update.return_value.execute.side_effect = error
        with self.assertLogs("apps.google_integration.services", level="ERROR") as logged:
            self.sync()
        self.assert_original_reporting(logged.records[0], error)
        self.assertEqual(logged.records[0].google_calendar_failure["operation"], "update")
        self.assertEqual(logged.records[0].google_calendar_failure["reason"], "rateLimitExceeded")
        self.google.events.return_value.update.assert_called_once_with(
            calendarId="primary", eventId="synthetic-event", body={"summary": SECRET})
        self.google.events.return_value.update.return_value.execute.assert_called_once_with()
        self.google.events.return_value.insert.assert_not_called()
        mapping.refresh_from_db()
        self.assertEqual(mapping.google_event_id, "synthetic-event")

    def test_mapping_failure_is_not_classified_as_a_provider_failure(self):
        # Even an HttpError raised after the provider returned must not be
        # attributed to that successful request.
        error = provider_error()
        self.google.events.return_value.insert.return_value.execute.return_value = {"id": "synthetic-event"}
        with patch.object(CalendarEventMapping.objects, "create", side_effect=error):
            with self.assertLogs("apps.google_integration.services", level="ERROR") as logged:
                self.sync()
        self.assert_original_reporting(logged.records[0], error)
        self.assertEqual(logged.records[0].google_calendar_failure, {
            "operation": "insert", "status": None, "reason": "unknown",
        })
        self.google.events.return_value.insert.return_value.execute.assert_called_once_with()
        self.assertFalse(CalendarEventMapping.objects.exists())

    def test_successful_insert_keeps_existing_mapping_behavior(self):
        self.google.events.return_value.insert.return_value.execute.return_value = {"id": "synthetic-event"}
        with patch("apps.google_integration.services.logger.exception") as logged:
            self.sync()
        logged.assert_not_called()
        self.assertEqual(CalendarEventMapping.objects.get(user=self.user).google_event_id, "synthetic-event")

    def test_sentry_logging_still_captures_original_exception_and_safe_extra(self):
        error = provider_error()
        self.google.events.return_value.insert.return_value.execute.side_effect = error
        events = []

        def collect(event, hint):
            events.append(event)
            return None

        original_scope = sentry_sdk.get_current_scope()
        original_client = original_scope.client
        client = sentry_sdk.Client(dsn="https://public@example.invalid/1", default_integrations=False,
                                   integrations=[LoggingIntegration(event_level=logging.ERROR)],
                                   transport=_OfflineTransport, before_send=collect)
        try:
            with sentry_sdk.new_scope() as scope:
                scope.set_client(client)
                with self.assertLogs("apps.google_integration.services", level="ERROR"):
                    self.sync()
        finally:
            client.close()
        self.assertIs(sentry_sdk.get_current_scope(), original_scope)
        self.assertIs(original_scope.client, original_client)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["exception"]["values"][-1]["type"], "HttpError")
        self.assertEqual(events[0]["logentry"]["message"],
                         "Google Calendar API error for %s:%s (user %s)")
        self.assertEqual(events[0]["extra"]["google_calendar_failure"], {
            "operation": "insert", "status": 403, "reason": "rateLimitExceeded",
        })
