"""Family-owned, write-only homework AI credentials and planner selection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.homework.models import HomeworkAssignment
from apps.homework.services import HomeworkError, HomeworkService
from config.llm import LLMError
from config.tests.factories import make_family


URL = "/api/homework/ai-settings/"
DEFAULT = {"provider": "default", "model": "", "has_api_key": False}
KEY = "synthetic-provider-secret"


class HomeworkAISettingsTests(TestCase):
    def setUp(self):
        self.house = make_family(
            parents=[{"username": "ai-parent"}, {"username": "ai-coparent"}],
            children=[{"username": "ai-child"}],
        )
        self.other = make_family(
            "Other house", parents=[{"username": "other-ai-parent"}],
            children=[{"username": "other-ai-child"}],
        )
        self.parent, self.coparent = self.house.parents
        self.child = self.house.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def save_settings(self, provider="openai", model="gpt-test", api_key=KEY):
        return self.client.put(URL, {
            "provider": provider, "model": model, "api_key": api_key,
        }, format="json")

    def saved(self):
        return apps.get_model("homework", "HomeworkAISettings").objects.get(
            family=self.house.family,
        )

    def assignment(self, child=None):
        return HomeworkAssignment.objects.create(
            title="Plan a science report", subject="science",
            due_date=timezone.localdate() + timedelta(days=7),
            assigned_to=child or self.child, created_by=self.parent,
        )

    def test_initial_settings_are_default_without_creating_a_record(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, DEFAULT)
        self.assertFalse(apps.get_model("homework", "HomeworkAISettings").objects.exists())

    def test_save_encrypts_key_and_never_returns_it(self):
        response = self.save_settings()
        self.assertEqual(response.status_code, 200)
        expected = {"provider": "openai", "model": "gpt-test", "has_api_key": True}
        self.assertEqual(response.data, expected)
        encrypted = bytes(self.saved().encrypted_api_key)
        self.assertNotIn(KEY.encode(), encrypted)
        self.assertNotEqual(encrypted, KEY.encode())
        self.assertEqual(self.client.get(URL).data, expected)
        self.assertNotIn(KEY, response.content.decode())

    def test_settings_are_parent_only_for_every_method(self):
        for user, expected in ((None, 401), (self.child, 403)):
            self.client.force_authenticate(user)
            for method in ("get", "put", "delete"):
                with self.subTest(user=user, method=method):
                    response = getattr(self.client, method)(URL, {}, format="json")
                    self.assertEqual(response.status_code, expected)

    def test_coparents_share_settings_but_other_families_do_not(self):
        self.assertEqual(self.save_settings().status_code, 200)
        self.client.force_authenticate(self.coparent)
        self.assertTrue(self.client.get(URL).data["has_api_key"])
        self.client.force_authenticate(self.other.parents[0])
        self.assertEqual(self.client.get(URL).data, DEFAULT)
        self.assertEqual(self.client.delete(URL).data, DEFAULT)
        self.assertTrue(self.saved().encrypted_api_key)

    def test_family_selector_is_rejected_without_writes(self):
        response = self.client.put(URL, {
            "provider": "openai", "model": "gpt-test", "api_key": KEY,
            "family": self.other.family.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(apps.get_model("homework", "HomeworkAISettings").objects.exists())

    def test_blank_or_omitted_key_preserves_key_for_same_provider(self):
        self.assertEqual(self.save_settings().status_code, 200)
        encrypted = bytes(self.saved().encrypted_api_key)
        for key_update in ({}, {"api_key": ""}):
            response = self.client.put(URL, {
                "provider": "openai", "model": "gpt-second", **key_update,
            }, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(bytes(self.saved().encrypted_api_key), encrypted)
            self.assertEqual(self.saved().model, "gpt-second")

    def test_first_save_and_provider_switch_require_a_key(self):
        self.assertEqual(self.save_settings(api_key="").status_code, 400)
        self.assertEqual(self.save_settings().status_code, 200)
        response = self.save_settings(provider="anthropic", model="claude-test", api_key="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.saved().provider, "openai")
        self.assertEqual(self.save_settings("anthropic", "claude-test", "replacement-key").status_code, 200)
        self.assertEqual(self.saved().provider, "anthropic")

    def test_delete_or_selecting_default_restores_deployment_settings(self):
        for remove in (lambda: self.client.delete(URL), lambda: self.save_settings("default", "", "")):
            self.assertEqual(self.save_settings().status_code, 200)
            self.assertEqual(remove().data, DEFAULT)
            self.assertEqual(self.client.get(URL).data, DEFAULT)
            self.assertFalse(apps.get_model("homework", "HomeworkAISettings").objects.exists())

    def test_invalid_inputs_return_safe_errors_without_writes(self):
        for fields in (
            {"provider": "unknown"}, {"model": ""}, {"model": "unsafe/model"},
            {"model": "m" * 129}, {"api_key": "secret\nsecond-line"},
            {"api_key": "secret\rline"}, {"api_key": "s" * 4097},
            {"api_key": "secret middle"}, {"api_key": "secret-\u00e9"},
        ):
            with self.subTest(fields=tuple(fields)):
                response = self.client.put(URL, {
                    "provider": "openai", "model": "gpt-test", "api_key": KEY, **fields,
                }, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(KEY, response.content.decode())
                if "api_key" in fields:
                    self.assertNotIn(fields["api_key"], response.content.decode())
        self.assertFalse(apps.get_model("homework", "HomeworkAISettings").objects.exists())

    @patch("config.llm.complete_json", return_value={"title": "Science steps"})
    def test_planning_uses_selected_provider_model_and_decrypted_family_key(self, complete):
        for provider, model in (("openai", "gpt-test"), ("anthropic", "claude-test")):
            with self.subTest(provider=provider):
                self.assertEqual(self.save_settings(provider, model).status_code, 200)
                assignment = self.assignment()
                HomeworkService.plan_assignment(assignment, parent=self.child)
                self.assertEqual(complete.call_args.kwargs["backend"], provider)
                self.assertEqual(complete.call_args.kwargs["model"], model)
                self.assertEqual(complete.call_args.kwargs["api_key"], KEY)
                self.assertEqual(complete.call_args.kwargs["max_tokens"], 8192)
                assignment.refresh_from_db()
                self.assertIsNotNone(assignment.project_id)

    @patch("config.llm.complete_json", return_value={"title": "Science steps"})
    def test_assignment_family_controls_key_instead_of_creator_or_requester(self, complete):
        self.assertEqual(self.save_settings().status_code, 200)
        assignment = self.assignment(child=self.other.children[0])
        HomeworkService.plan_assignment(assignment, parent=self.parent)
        self.assertNotIn("api_key", complete.call_args.kwargs)
        self.assertNotIn("backend", complete.call_args.kwargs)

    @patch("config.llm.complete_json", return_value={"title": "Science steps"})
    def test_no_override_keeps_existing_planner_call(self, complete):
        HomeworkService.plan_assignment(self.assignment(), parent=self.parent)
        self.assertEqual(set(complete.call_args.kwargs), {"prompt", "max_tokens"})

    @patch("config.llm.complete_json")
    def test_corrupt_or_wrong_secret_key_fails_closed_without_provider_request(self, complete):
        self.assertEqual(self.save_settings().status_code, 200)
        assignment = self.assignment()
        with override_settings(SECRET_KEY="different-test-encryption-key"):
            with self.assertRaisesMessage(HomeworkError, "AI planning failed. Check your homework AI settings and try again."):
                HomeworkService.plan_assignment(assignment, parent=self.parent)
        complete.assert_not_called()
        assignment.refresh_from_db()
        self.assertIsNone(assignment.project_id)

    @patch("config.llm.complete_json")
    def test_provider_error_does_not_escape_to_response_or_logs(self, complete):
        for error in (LLMError(KEY), RuntimeError(KEY)):
            with self.subTest(error=type(error)):
                complete.side_effect = error
                assignment = self.assignment()
                with self.assertLogs("apps.homework.services", level="WARNING") as logs:
                    response = self.client.post(f"/api/homework/{assignment.pk}/plan/")
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(KEY, response.content.decode())
                self.assertNotIn(KEY, " ".join(logs.output))
                assignment.refresh_from_db()
                self.assertIsNone(assignment.project_id)

    @patch("config.llm.complete_json", return_value={"title": "Science steps"})
    def test_child_can_plan_with_family_key_but_existing_access_gates_still_apply(self, complete):
        self.assertEqual(self.save_settings().status_code, 200)
        assignment = self.assignment()
        self.client.force_authenticate(self.child)
        response = self.client.post(f"/api/homework/{assignment.pk}/plan/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(complete.call_args.kwargs["api_key"], KEY)
        complete.reset_mock()
        urgent = self.assignment()
        urgent.due_date = timezone.localdate() + timedelta(days=1)
        urgent.save(update_fields=["due_date"])
        self.assertEqual(self.client.post(f"/api/homework/{urgent.pk}/plan/").status_code, 403)
        foreign = self.assignment(child=self.other.children[0])
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.post(f"/api/homework/{foreign.pk}/plan/").status_code, 404)
        complete.assert_not_called()


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class HomeworkAISettingsConcurrencyTests(TransactionTestCase):
    def test_simultaneous_coparent_first_saves_keep_one_consistent_configuration(self):
        from apps.homework.ai_settings import planner_options

        house = make_family(parents=[{"username": "race-parent-a"}, {"username": "race-parent-b"}])
        barrier = Barrier(2)
        choices = (("openai", "gpt-test", "openai-key"), ("anthropic", "claude-test", "claude-key"))

        def save(user, choice):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '3s'")
                    cursor.execute("SET statement_timeout = '5s'")
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait(timeout=5)
                provider, model, api_key = choice
                response = client.put(URL, {"provider": provider, "model": model, "api_key": api_key}, format="json")
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(save, user, choice) for user, choice in zip(house.parents, choices)]
            self.assertEqual([future.result(timeout=10) for future in futures], [200, 200])
        model = apps.get_model("homework", "HomeworkAISettings")
        self.assertEqual(model.objects.filter(family=house.family).count(), 1)
        options = planner_options(house.family)
        self.assertIn((options["backend"], options["model"], options["api_key"]), choices)
