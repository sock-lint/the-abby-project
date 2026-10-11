"""Synthetic deployment API checks; never contacts GitHub, Coolify, or production."""

import contextlib
import io
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from deploy_coolify import ApiError, Config, DeploymentError, DeploymentInterrupted, JsonApi, NoRedirect, deploy


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
        self.health.request.return_value = {"status": "ok", "db": "up"}
        self.latest_main = Mock(return_value=SHA)
        self.responses = []
        self.history = {"count": 0, "deployments": []}
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
            return {"deployments": [{"resource_uuid": APP_UUID, "deployment_uuid": DEPLOY_UUID}]}
        if path.startswith("/deployments/applications/"):
            return self.history
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


if __name__ == "__main__":
    unittest.main()
