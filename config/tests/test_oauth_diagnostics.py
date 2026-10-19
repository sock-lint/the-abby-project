import sentry_sdk
from django.test import RequestFactory, SimpleTestCase
from sentry_sdk.integrations.django import DjangoRequestExtractor
from sentry_sdk.scrubber import EventScrubber

from config.oauth_diagnostics import scrub_google_oauth


class GoogleOAuthDiagnosticsTests(SimpleTestCase):
    def test_temporary_provider_and_browser_secrets_are_removed(self):
        for path in ("/api/auth/google/", "/api/auth/google/callback/", "/api/auth/google/exchange/"):
            with self.subTest(path=path):
                event = {"request": {"url": "https://example.invalid" + path + "?code=secret#secret",
                                      "query_string": "code=secret", "data": {"code_verifier": "secret"},
                                      "cookies": "secret", "headers": {"Authorization": "secret"}},
                         "breadcrumbs": {"values": [{"message": "secret"}]},
                         "spans": [{"description": "secret"}], "exception": {"values": []}}
                result = scrub_google_oauth(event)
                self.assertNotIn("secret", str(result))
                self.assertIn("exception", result)

    def test_exception_locals_messages_and_extra_are_removed(self):
        event = {"request": {"url": "https://example.invalid/api/auth/google/exchange/"},
                 "exception": {"values": [{"type": "DatabaseError", "value": "secret",
                    "stacktrace": {"frames": [{"filename": "oauth_exchange.py", "lineno": 123,
                                              "vars": {"payload": {"credentials": "secret"}}}]}}]},
                 "extra": {"verifier": "secret"}, "contexts": {"provider": "secret"},
                 "message": "secret", "logentry": {"message": "secret"}}
        result = scrub_google_oauth(event)
        self.assertNotIn("secret", str(result))
        frame = result["exception"]["values"][0]["stacktrace"]["frames"][0]
        self.assertEqual(frame, {"filename": "oauth_exchange.py", "lineno": 123})

    def test_other_requests_keep_their_existing_diagnostics(self):
        event = {"request": {"url": "https://example.invalid/api/projects/?page=2"}}
        self.assertIs(scrub_google_oauth(event), event)
        self.assertIn("page=2", event["request"]["url"])

    def test_oauth_performance_trace_is_not_sent(self):
        event = {"type": "transaction", "request": {"url": "https://example.invalid/api/auth/google/callback/"},
                 "spans": [{"description": "secret"}]}
        self.assertIsNone(scrub_google_oauth(event))


class HomeworkProofDiagnosticsTests(SimpleTestCase):
    def test_sdk_extracted_proof_material_is_removed_but_error_coordinates_remain(self):
        proof_url = "https://drive.google.com/file/d/synthetic-private-proof/view?resourcekey=synthetic-secret"
        request = RequestFactory().post(
            "/api/homework/42/submit/", {"proof_url": proof_url},
        )
        event = {
            "event_id": "synthetic-homework-error",
            "level": "error",
            "request": {"url": "https://example.invalid/api/homework/42/submit/?proof=" + proof_url},
            "exception": {"values": [{
                "type": "StorageError", "module": "synthetic.storage", "value": proof_url,
                "stacktrace": {"frames": [{
                    "filename": "homework/services.py", "function": "submit_completion", "lineno": 281,
                    "in_app": True, "vars": {"proof_url": proof_url, "value": proof_url},
                }]},
            }]},
            "breadcrumbs": {"values": [{"message": proof_url, "data": {"proof_url": proof_url}}]},
            "spans": [{"description": proof_url}],
            "contexts": {"homework": {"proof_url": proof_url}},
            "extra": {"proof_url": proof_url},
            "message": proof_url,
            "logentry": {"message": proof_url, "params": [proof_url]},
        }
        # Exercise the installed Django SDK, whose default PII setting alone
        # still includes request bodies. No DSN or transport can send this data.
        client = sentry_sdk.Client(dsn=None, default_integrations=False, send_default_pii=False)
        try:
            with sentry_sdk.new_scope() as scope:
                scope.set_client(client)
                DjangoRequestExtractor(request).extract_into_event(event)
                EventScrubber().scrub_event(event)
        finally:
            client.close()
        self.assertEqual(event["request"]["data"]["proof_url"], proof_url)

        result = scrub_google_oauth(event)
        self.assertNotIn("synthetic-secret", str(result))
        self.assertNotIn("drive.google.com", str(result))
        self.assertEqual(result, {
            "event_id": "synthetic-homework-error",
            "level": "error",
            "request": {"url": "https://example.invalid/api/homework/42/submit/"},
            "exception": {"values": [{
                "type": "StorageError", "module": "synthetic.storage",
                "stacktrace": {"frames": [{
                    "filename": "homework/services.py", "function": "submit_completion", "lineno": 281,
                    "in_app": True,
                }]},
            }]},
        })

    def test_proof_submission_transactions_keep_timing_and_safe_trace_without_proof_material(self):
        proof_url = "https://drive.google.com/file/d/synthetic-private-proof/view?resourcekey=synthetic-secret"
        for path in ("/api/homework/42/submit/", "/api/homework/42/submit"):
            with self.subTest(path=path):
                trace = {
                    "trace_id": "a" * 32, "span_id": "b" * 16, "parent_span_id": "c" * 16,
                    "op": "http.server", "status": "ok",
                }
                event = {
                    "type": "transaction", "event_id": "d" * 32,
                    "start_timestamp": 1792440000.0, "timestamp": 1792440001.25,
                    "environment": "synthetic-test", "release": "synthetic-release",
                    "transaction": proof_url,
                    "request": {"url": "https://example.invalid" + path + "?proof=" + proof_url,
                                "data": {"proof_url": proof_url}},
                    "contexts": {"trace": {**trace, "data": {"proof_url": proof_url}},
                                 "homework": {"proof_url": proof_url}},
                    "spans": [{"description": proof_url}],
                    "breadcrumbs": {"values": [{"message": proof_url}]},
                    "extra": {"proof_url": proof_url}, "message": proof_url,
                }
                result = scrub_google_oauth(event)
                self.assertIsNotNone(result)
                self.assertNotIn("synthetic-secret", str(result))
                self.assertEqual(result, {
                    "type": "transaction", "event_id": "d" * 32,
                    "start_timestamp": 1792440000.0, "timestamp": 1792440001.25,
                    "environment": "synthetic-test", "release": "synthetic-release",
                    "transaction": "POST /api/homework/{id}/submit/",
                    "request": {"url": "https://example.invalid" + path},
                    "contexts": {"trace": trace},
                })

    def test_other_homework_and_similarly_named_routes_keep_existing_diagnostics(self):
        for path in (
            "/api/homework/42/", "/api/homework/42/plan/", "/api/homework-submissions/42/approve/",
            "/api/homework/not-a-number/submit/", "/api/homework/42/submit/extra/",
        ):
            with self.subTest(path=path):
                event = {"request": {"url": "https://example.invalid" + path}, "message": "ordinary diagnosis"}
                self.assertIs(scrub_google_oauth(event), event)

    def test_proof_transaction_trace_metadata_cannot_echo_a_proof_url(self):
        proof_url = "https://drive.google.com/file/d/synthetic-private-proof/view"
        event = {
            "type": "transaction", "start_timestamp": 1792440000.0, "timestamp": 1792440001.25,
            "request": {"url": "https://example.invalid/api/homework/42/submit/"},
            "contexts": {"trace": {
                "trace_id": "a" * 32, "span_id": "b" * 16,
                "parent_span_id": proof_url, "op": proof_url, "status": proof_url,
            }},
        }
        result = scrub_google_oauth(event)
        self.assertIsNotNone(result)
        self.assertNotIn("drive.google.com", str(result))
        self.assertEqual(result["contexts"]["trace"], {"trace_id": "a" * 32, "span_id": "b" * 16})
