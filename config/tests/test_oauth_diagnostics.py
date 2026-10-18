from django.test import SimpleTestCase

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
