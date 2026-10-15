"""Synthetic deployment API checks; never contacts GitHub, Coolify, or production."""

import contextlib
import io
import unittest
from unittest.mock import Mock
from http.client import RemoteDisconnected
from urllib.error import HTTPError, URLError

from deploy_coolify import (
    ApiError, Config, ConnectionFailure, DeploymentError, DeploymentInterrupted,
    InvalidResponse, JsonApi, NoRedirect, deploy,
)


SHA = "a" * 40
OTHER_SHA = "b" * 40
APP_UUID = "synthetic-app"
DEPLOY_UUID = "synthetic-deployment"


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=30, poll_interval=10)
        self.application = {
            "uuid": APP_UUID, "git_repository": "synthetic/abby", "git_branch": "main", "git_commit_sha": "HEAD",
        }
        self.coolify = Mock()
        self.health = Mock()
        self.health.request.return_value = {"status": "ok", "db": "up", "commit": SHA, "resourceUuid": APP_UUID}
        self.latest_main = Mock(return_value=SHA)
        self.responses = []
        self.history = {"count": 0, "deployments": []}
        self.histories = []
        self.post_response = {"deployments": [{"resource_uuid": APP_UUID, "deployment_uuid": DEPLOY_UUID}]}
        self.now = 0
        self.coolify.request.side_effect = self.request
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stderr = contextlib.redirect_stderr(io.StringIO())
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def request(self, method, path, body=None):
        if path == f"/applications/{APP_UUID}":
            return self.application
        if path == "/deploy":
            if isinstance(self.post_response, Exception):
                raise self.post_response
            return self.post_response
        if path.startswith("/deployments/applications/"):
            result = self.histories.pop(0) if self.histories else self.history
            if isinstance(result, Exception):
                raise result
            return result
        if path.endswith("/cancel"):
            return {"status": "cancelled-by-user"}
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def response(self, status, commit=SHA):
        return {"deployment_uuid": DEPLOY_UUID, "status": status, "commit": commit, "pull_request_id": 0}

    def sleep(self, seconds):
        self.now += seconds

    def run_deploy(self):
        return deploy(self.config, self.coolify, self.latest_main, self.health, clock=lambda: self.now, sleep=self.sleep)

    def mutations(self):
        return [call for call in self.coolify.request.call_args_list if call.args[0] == "POST"]

    def test_superseded_run_never_contacts_coolify(self):
        self.latest_main.return_value = OTHER_SHA
        self.assertFalse(self.run_deploy())
        self.coolify.request.assert_not_called()

    def test_main_changed_during_verification_does_not_queue(self):
        self.latest_main.side_effect = [SHA, OTHER_SHA]
        self.assertFalse(self.run_deploy())
        self.assertEqual(self.mutations(), [])

    def test_wrong_application_target_never_queues(self):
        for field, value in (("uuid", "other-app"), ("git_repository", "other/repo"), ("git_branch", "dev"), ("git_commit_sha", OTHER_SHA)):
            with self.subTest(field=field):
                self.application[field] = value
                with self.assertRaises(DeploymentError):
                    self.run_deploy()
                self.assertEqual(self.mutations(), [])
                self.application[field] = {"uuid": APP_UUID, "git_repository": "synthetic/abby", "git_branch": "main", "git_commit_sha": "HEAD"}[field]

    def test_exact_commit_and_public_database_health_pass(self):
        self.responses = [self.response("queued", "HEAD"), self.response("in_progress"), self.response("finished")]
        self.assertTrue(self.run_deploy())
        self.assertEqual(len(self.mutations()), 1)
        self.coolify.request.assert_any_call("POST", "/deploy", {"uuid": APP_UUID, "force": False})
        self.health.request.assert_called_once_with("GET")

    def test_reuses_existing_exact_sha_native_deployment(self):
        self.history = {"count": 1, "deployments": [self.response("in_progress")]}
        self.responses = [self.response("finished")]
        self.assertTrue(self.run_deploy())
        self.assertEqual(self.mutations(), [])

    def test_reuses_unresolved_head_then_requires_exact_sha(self):
        self.history = {"count": 1, "deployments": [self.response("queued", "HEAD")]}
        self.responses = [self.response("queued", "HEAD"), self.response("finished")]
        self.assertTrue(self.run_deploy())
        self.assertEqual(self.mutations(), [])

    def test_unrelated_preview_history_cannot_be_reused(self):
        preview = self.response("in_progress")
        preview["pull_request_id"] = 42
        self.history = {"count": 1, "deployments": [preview]}
        self.responses = [self.response("finished")]
        self.assertTrue(self.run_deploy())
        self.assertEqual(len(self.mutations()), 1)

    def test_duplicate_api_uuid_race_resolves_same_application_history(self):
        self.coolify.request.side_effect = [
            self.application, {"count": 0, "deployments": []},
            {"deployments": [{"resource_uuid": APP_UUID, "deployment_uuid": "nonexistent-duplicate"}]},
            ApiError(404), {"count": 1, "deployments": [self.response("in_progress")]},
            self.response("finished"),
        ]
        self.assertTrue(self.run_deploy())
        self.coolify.request.assert_any_call("GET", f"/deployments/{DEPLOY_UUID}")

    def test_resolved_wrong_commit_is_cancelled_before_success(self):
        self.responses = [self.response("in_progress", OTHER_SHA)]
        with self.assertRaisesRegex(DeploymentError, "different commit"):
            self.run_deploy()
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")
        self.health.request.assert_not_called()

    def test_contradictory_identity_revokes_cancellation_even_after_valid_observation(self):
        for field, value in (("application_uuid", "synthetic-private-other-app"),
                             ("resource_uuid", "synthetic-private-other-resource"),
                             ("pull_request_id", 42),
                             ("deployment_uuid", "synthetic-private-other-deployment")):
            with self.subTest(field=field):
                self.coolify.reset_mock()
                self.now = 0
                contradiction = dict(self.response("in_progress"), **{field: value})
                self.responses = [self.response("in_progress"), contradiction]
                with self.assertRaisesRegex(DeploymentError, "Cancellation was withheld") as error:
                    self.run_deploy()
                self.assertEqual(len(self.mutations()), 1)
                self.assertEqual(self.mutations()[0].args[1], "/deploy")
                self.assertNotIn("synthetic-private", str(error.exception))
                self.health.request.assert_not_called()

    def test_contradiction_after_adopting_scoped_history_never_cancels_cross_target(self):
        self.history = {"deployments": [self.response("in_progress")]}
        self.responses = [dict(self.response("in_progress"), resource_uuid="synthetic-private-other-app")]
        with self.assertRaisesRegex(DeploymentError, "Cancellation was withheld"):
            self.run_deploy()
        self.assertEqual(self.mutations(), [])

    def test_new_main_cancels_monitored_deployment(self):
        self.latest_main.side_effect = [SHA, SHA, OTHER_SHA]
        self.responses = [self.response("queued", "HEAD")]
        with self.assertRaisesRegex(DeploymentError, "superseded"):
            self.run_deploy()
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_timeout_cancels_monitored_deployment(self):
        self.responses = [self.response("queued", "HEAD")] * 3
        with self.assertRaisesRegex(DeploymentError, "exceeded"):
            self.run_deploy()
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_interruption_attempts_cancellation(self):
        self.responses = [DeploymentInterrupted("synthetic interruption")]
        with self.assertRaises(DeploymentInterrupted):
            self.run_deploy()
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_finished_head_does_not_prove_a_commit(self):
        self.responses = [self.response("finished", "HEAD")]
        with self.assertRaisesRegex(DeploymentError, "exact expected commit"):
            self.run_deploy()
        self.health.request.assert_not_called()
        self.assertEqual(len(self.mutations()), 1)

    def test_failed_deployment_never_reports_health_success(self):
        self.responses = [self.response("failed")]
        with self.assertRaisesRegex(DeploymentError, "failed"):
            self.run_deploy()
        self.health.request.assert_not_called()

    def test_finished_deployment_requires_healthy_database(self):
        self.responses = [self.response("finished")]
        self.health.request.return_value = {"status": "ok", "db": "down"}
        with self.assertRaisesRegex(DeploymentError, "public /health"):
            self.run_deploy()

    def test_transient_poll_failure_recovers_without_cancellation_or_extra_post(self):
        self.responses = [ConnectionFailure("synthetic"), ApiError(503), self.response("finished")]
        self.assertTrue(self.run_deploy())
        self.assertEqual(len(self.mutations()), 1)
        self.assertEqual(self.now, 6)

    def test_transient_github_reads_recover_before_and_during_monitoring(self):
        self.latest_main.side_effect = [ConnectionFailure("synthetic"), SHA, SHA, ApiError(502), SHA, SHA, SHA]
        self.responses = [self.response("finished")]
        self.assertTrue(self.run_deploy())
        self.assertEqual(len(self.mutations()), 1)

    def test_each_temporary_http_status_can_recover(self):
        for status in (408, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.coolify.reset_mock()
                self.responses = [ApiError(status), self.response("finished")]
                self.now = 0
                self.assertTrue(self.run_deploy())
                self.assertEqual(len(self.mutations()), 1)

    def test_permanent_api_error_is_not_retried(self):
        self.responses = [ApiError(403)]
        with self.assertRaises(ApiError):
            self.run_deploy()
        self.assertEqual(self.now, 0)
        self.assertEqual(sum(call.args == ("GET", f"/deployments/{DEPLOY_UUID}")
                             for call in self.coolify.request.call_args_list), 1)
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_persistent_read_failure_is_bounded_and_cancels_known_uuid(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=120, poll_interval=10)
        self.responses = [ConnectionFailure("synthetic")] * 5
        with self.assertRaisesRegex(DeploymentError, "bounded read retries"):
            self.run_deploy()
        self.assertEqual(self.now, 30)
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")
        self.assertEqual(sum(call.args[1] == "/deploy" for call in self.mutations()), 1)

    def test_deadline_during_read_backoff_cancels_known_uuid(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=1, poll_interval=10)
        self.responses = [ConnectionFailure("synthetic")]
        with self.assertRaisesRegex(DeploymentError, "deadline"):
            self.run_deploy()
        self.assertEqual(self.now, 1)
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_last_retry_failure_at_deadline_reports_deadline_and_cancels(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=120, poll_interval=10)
        observations = 0

        def request(method, path, body=None):
            nonlocal observations
            if path == f"/deployments/{DEPLOY_UUID}":
                observations += 1
                if observations == 5:
                    self.now = 120
                raise ConnectionFailure("synthetic")
            return self.request(method, path, body)

        self.coolify.request.side_effect = request
        with self.assertRaisesRegex(DeploymentError, "deadline"):
            self.run_deploy()
        self.assertEqual(observations, 5)
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_supersession_during_backoff_cancels_without_second_status_read(self):
        self.latest_main.side_effect = [SHA, SHA, OTHER_SHA]
        self.responses = [ConnectionFailure("synthetic")]
        with self.assertRaisesRegex(DeploymentError, "superseded"):
            self.run_deploy()
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")
        self.assertEqual(sum(call.args == ("GET", f"/deployments/{DEPLOY_UUID}")
                             for call in self.coolify.request.call_args_list), 1)

    def test_setup_retries_share_deadline_and_never_queue_after_expiry(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=1, poll_interval=10)
        self.latest_main.side_effect = [ConnectionFailure("synthetic"), SHA]
        with self.assertRaisesRegex(DeploymentError, "deadline"):
            self.run_deploy()
        self.assertEqual(self.mutations(), [])

    def uncertain_post(self, outcome, rows):
        self.post_response = outcome
        self.histories = [self.history, {"deployments": rows}]
        self.responses = [self.response("finished")]

    def test_unknown_post_response_reconciles_new_active_row_without_resubmit(self):
        self.uncertain_post(ConnectionFailure("synthetic"), [self.response("in_progress", "HEAD")])
        self.assertTrue(self.run_deploy())
        self.assertEqual(len(self.mutations()), 1)

    def test_unknown_post_response_can_reconcile_fast_finished_exact_sha(self):
        self.uncertain_post(ApiError(504), [self.response("finished")])
        self.assertTrue(self.run_deploy())
        self.assertEqual(len(self.mutations()), 1)

    def test_malformed_post_response_is_observed_without_resubmit(self):
        for outcome in (InvalidResponse("synthetic"), {}, {"deployments": [{"resource_uuid": APP_UUID}]},
                        {"deployments": [{"resource_uuid": "another-app", "deployment_uuid": "other"}]}):
            with self.subTest(outcome=type(outcome).__name__):
                self.coolify.reset_mock()
                self.uncertain_post(outcome, [self.response("finished")])
                self.assertTrue(self.run_deploy())
                self.assertEqual(len(self.mutations()), 1)

    def test_unknown_post_without_new_history_row_never_resubmits_or_cancels_unknown_uuid(self):
        old = self.response("finished")
        self.history = {"deployments": [old]}
        self.post_response = ConnectionFailure("synthetic")
        with self.assertRaisesRegex(DeploymentError, "No replacement request"):
            self.run_deploy()
        self.assertEqual(len(self.mutations()), 1)
        self.health.request.assert_not_called()

    def test_unknown_post_reconciliation_has_its_own_sixty_second_limit(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=120, poll_interval=10)
        self.post_response = ConnectionFailure("synthetic")
        with self.assertRaisesRegex(DeploymentError, "No replacement request"):
            self.run_deploy()
        self.assertEqual(self.now, 60)
        self.assertEqual(len(self.mutations()), 1)

    def test_unknown_post_reconciliation_tolerates_delayed_history_and_read_outage(self):
        self.post_response = ConnectionFailure("synthetic")
        self.histories = [self.history, ConnectionFailure("synthetic"), self.history,
                          {"deployments": [self.response("in_progress")]}]
        self.responses = [self.response("finished")]
        self.assertTrue(self.run_deploy())
        self.assertEqual(self.now, 12)
        self.assertEqual(len(self.mutations()), 1)

    def test_ambiguous_unknown_post_rows_fail_without_cancellation_or_resubmit(self):
        other = self.response("in_progress")
        other["deployment_uuid"] = "second-deployment"
        self.uncertain_post(ConnectionFailure("synthetic"), [self.response("in_progress"), other])
        with self.assertRaisesRegex(DeploymentError, "ambiguous"):
            self.run_deploy()
        self.assertEqual(len(self.mutations()), 1)

    def test_unknown_post_cannot_adopt_preview_cross_app_wrong_commit_or_finished_head(self):
        invalid_rows = [dict(self.response("in_progress"), pull_request_id=4),
                        dict(self.response("in_progress"), resource_uuid="other-app"),
                        dict(self.response("in_progress"), application_uuid="other-app"),
                        self.response("in_progress", OTHER_SHA), self.response("finished", "HEAD")]
        for row in invalid_rows:
            with self.subTest(row=row):
                self.coolify.reset_mock()
                self.now = 0
                self.history = {"deployments": [row]}
                self.histories = [{"deployments": []}]
                self.post_response = ConnectionFailure("synthetic")
                with self.assertRaisesRegex(DeploymentError, "No replacement request"):
                    self.run_deploy()
                self.assertEqual(len(self.mutations()), 1)

    def test_permanent_post_error_is_never_retried(self):
        self.post_response = ApiError(403)
        with self.assertRaises(ApiError):
            self.run_deploy()
        self.assertEqual(len(self.mutations()), 1)
        self.assertEqual(self.now, 0)

    def test_unknown_post_recovery_still_cancels_when_main_has_changed(self):
        self.uncertain_post(ConnectionFailure("synthetic"), [self.response("in_progress")])
        self.responses = [self.response("in_progress")]
        self.latest_main.side_effect = [SHA, SHA, OTHER_SHA]
        with self.assertRaisesRegex(DeploymentError, "superseded"):
            self.run_deploy()
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_health_requires_exact_serving_commit_and_application(self):
        for field, value in (("commit", OTHER_SHA), ("commit", None), ("resourceUuid", "other-app"), ("resourceUuid", None)):
            with self.subTest(field=field, value=value):
                self.now = 0
                self.responses = [self.response("finished")]
                self.health.request.return_value = {"status": "ok", "db": "up", "commit": SHA, "resourceUuid": APP_UUID, field: value}
                with self.assertRaisesRegex(DeploymentError, "public /health"):
                    self.run_deploy()

    def test_health_temporary_failure_recovers_with_identity(self):
        self.responses = [self.response("finished")]
        self.health.request.side_effect = [ConnectionFailure("synthetic"), self.health.request.return_value]
        self.assertTrue(self.run_deploy())
        self.assertEqual(len(self.mutations()), 1)

    def test_health_plaintext_rollout_response_waits_for_exact_json_identity(self):
        self.responses = [self.response("finished")]
        self.health.request.side_effect = [InvalidResponse("synthetic plaintext ok"), self.health.request.return_value]
        self.assertTrue(self.run_deploy())
        self.assertEqual(self.now, 10)
        self.assertEqual(len(self.mutations()), 1)

    def test_persistent_invalid_health_response_is_bounded_without_cancelling_finished(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=300, poll_interval=10)
        self.responses = [self.response("finished")]
        self.health.request.side_effect = InvalidResponse("synthetic plaintext ok")
        with self.assertRaisesRegex(DeploymentError, "public /health"):
            self.run_deploy()
        self.assertEqual(self.now, 120)
        self.assertEqual(self.health.request.call_count, 12)
        self.assertEqual(len(self.mutations()), 1)

    def test_supersession_during_invalid_health_retry_never_accepts_or_cancels_finished(self):
        self.responses = [self.response("finished")]
        self.health.request.side_effect = InvalidResponse("synthetic plaintext ok")
        self.latest_main.side_effect = [SHA, SHA, SHA, SHA, OTHER_SHA]
        with self.assertRaisesRegex(DeploymentError, "superseded"):
            self.run_deploy()
        self.assertEqual(self.health.request.call_count, 1)
        self.assertEqual(len(self.mutations()), 1)

    def test_invalid_coolify_or_github_json_is_not_retried_as_health_readiness(self):
        self.responses = [InvalidResponse("synthetic")]
        with self.assertRaises(InvalidResponse):
            self.run_deploy()
        self.assertEqual(self.now, 0)
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")
        self.coolify.reset_mock()
        self.latest_main.side_effect = InvalidResponse("synthetic")
        with self.assertRaises(InvalidResponse):
            self.run_deploy()
        self.assertEqual(self.mutations(), [])

    def test_main_change_during_health_never_reports_success(self):
        self.responses = [self.response("finished")]
        self.latest_main.side_effect = [SHA, SHA, SHA, SHA, OTHER_SHA]
        with self.assertRaisesRegex(DeploymentError, "superseded"):
            self.run_deploy()
        self.assertEqual(len(self.mutations()), 1)  # Finished deployment is not cancelled.

    def test_health_final_main_check_cannot_outlive_health_window(self):
        self.config = Config(SHA, "synthetic/abby", APP_UUID, timeout=300, poll_interval=10)
        self.responses = [self.response("finished")]
        reads = 0

        def current():
            nonlocal reads
            reads += 1
            if reads == 5:
                self.now = 121
            return SHA

        self.latest_main.side_effect = current
        with self.assertRaisesRegex(DeploymentError, "deadline"):
            self.run_deploy()
        self.assertEqual(len(self.mutations()), 1)

    def test_interruption_is_not_retried_as_a_temporary_failure(self):
        self.responses = [DeploymentInterrupted("synthetic interruption")]
        with self.assertRaises(DeploymentInterrupted):
            self.run_deploy()
        self.assertEqual(self.now, 0)
        self.coolify.request.assert_any_call("POST", f"/deployments/{DEPLOY_UUID}/cancel")

    def test_active_conflicting_or_ambiguous_rows_do_not_queue(self):
        for rows in ([self.response("in_progress", OTHER_SHA)],
                     [self.response("in_progress"), dict(self.response("queued", "HEAD"), deployment_uuid="second")]):
            with self.subTest(rows=rows):
                self.coolify.reset_mock()
                self.history = {"deployments": rows}
                with self.assertRaises(DeploymentError):
                    self.run_deploy()
                self.assertEqual(self.mutations(), [])


class ApiSafetyTests(unittest.TestCase):
    def test_bearer_requests_cannot_follow_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example"))

    def test_public_http_credentials_and_queries_are_rejected(self):
        for url in ("http://8.8.8.8/api/v1", "http://coolify.example/api/v1", "https://token@example.test/api/v1", "https://example.test/api/v1?token=secret"):
            with self.subTest(url=url), self.assertRaises(DeploymentError):
                JsonApi(url, "synthetic-token")
        JsonApi("http://192.168.4.76:8000/api/v1", "synthetic-token")

    def test_api_errors_do_not_echo_response_body_or_credential(self):
        api = JsonApi("https://synthetic.example/api/v1", "synthetic-token")
        api.opener = Mock()
        api.opener.open.side_effect = HTTPError("https://synthetic.example", 403, "synthetic-secret-body", {}, None)
        with self.assertRaises(DeploymentError) as error:
            api.request("GET", "/applications/synthetic")
        self.assertIn("HTTP 403", str(error.exception))
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_public_health_client_has_no_authorization_header(self):
        health = JsonApi("https://synthetic.example/health")
        response = Mock()
        response.read.return_value = b'{"status":"ok","db":"up"}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        health.opener = Mock()
        health.opener.open.return_value = response
        health.request("GET")
        request = health.opener.open.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))

    def test_connection_failures_are_sanitized_and_never_retried_by_api_client(self):
        for failure in (URLError("synthetic-secret"), TimeoutError("synthetic-secret"),
                        ConnectionResetError("synthetic-secret"), RemoteDisconnected("synthetic-secret")):
            with self.subTest(failure=type(failure).__name__):
                api = JsonApi("https://synthetic.example/api/v1", "synthetic-token")
                api.opener = Mock()
                api.opener.open.side_effect = failure
                with self.assertRaises(ConnectionFailure) as error:
                    api.request("POST", "/deploy", {"uuid": APP_UUID})
                api.opener.open.assert_called_once()
                self.assertNotIn("synthetic-secret", str(error.exception))
                self.assertNotIn("synthetic-token", str(error.exception))

    def test_plaintext_health_is_invalid_json_without_echoing_its_body(self):
        health = JsonApi("https://synthetic.example/health")
        response = Mock()
        response.read.return_value = b"synthetic-private-plaintext"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        health.opener = Mock()
        health.opener.open.return_value = response
        with self.assertRaises(InvalidResponse) as error:
            health.request("GET")
        self.assertNotIn("synthetic-private-plaintext", str(error.exception))


if __name__ == "__main__":
    unittest.main()
