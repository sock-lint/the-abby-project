"""Tests for the unified LLM adapter (`config.llm`)."""
from __future__ import annotations

import json
import traceback
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from config import llm


@override_settings(
    LLM_BACKEND="auto",
    ANTHROPIC_API_KEY="",
)
class ActiveBackendTests(SimpleTestCase):
    def test_auto_with_no_config_returns_none(self):
        self.assertEqual(llm.active_backend(), "none")
        self.assertFalse(llm.is_available())

    @override_settings(ANTHROPIC_API_KEY="key")
    def test_auto_prefers_anthropic_when_key_set(self):
        self.assertEqual(llm.active_backend(), "anthropic")

    @override_settings(ANTHROPIC_API_KEY="key", OLLAMA_BASE_URL="http://lan:11434")
    def test_auto_uses_claude_even_if_retired_provider_url_remains(self):
        self.assertEqual(llm.active_backend(), "anthropic")

    @override_settings(LLM_BACKEND="anthropic", ANTHROPIC_API_KEY="")
    def test_explicit_anthropic_without_key_is_none(self):
        self.assertEqual(llm.active_backend(), "none")

    @override_settings(LLM_BACKEND="none", ANTHROPIC_API_KEY="key")
    def test_explicit_none_disables_everything(self):
        self.assertEqual(llm.active_backend(), "none")


@override_settings(LLM_BACKEND="auto", ANTHROPIC_API_KEY="")
class CompleteJsonUnavailableTests(SimpleTestCase):
    def test_raises_llm_unavailable_when_no_backend(self):
        with self.assertRaises(llm.LLMUnavailable):
            llm.complete_json(prompt="hi")

    @override_settings(ANTHROPIC_API_KEY="synthetic-deployment-key", OLLAMA_BASE_URL="http://retired-provider.invalid:11434")
    def test_removed_or_unknown_backend_fails_closed_without_provider_request(self):
        response = MagicMock()
        response.json.return_value = {"response": '{"unexpected": true}'}
        for backend in ("ollama", "unknown", "openai", "", None):
            with self.subTest(backend=backend), override_settings(LLM_BACKEND=backend), patch(
                "requests.post", return_value=response,
            ) as post, patch("config.llm._anthropic_complete", return_value='{"unexpected": true}') as anthropic:
                with self.assertRaises(llm.LLMUnavailable):
                    llm.complete_json(prompt="Never send this homework")
                self.assertEqual(llm.active_backend(), "none")
                self.assertFalse(llm.is_available())
                post.assert_not_called()
                anthropic.assert_not_called()

    @override_settings(OLLAMA_BASE_URL="http://retired-provider.invalid:11434")
    def test_auto_ignores_retired_provider_url_without_a_claude_key(self):
        response = MagicMock()
        response.json.return_value = {"response": '{"unexpected": true}'}
        with patch("requests.post", return_value=response) as post:
            with self.assertRaises(llm.LLMUnavailable):
                llm.complete_json(prompt="Never send this homework")
            self.assertEqual(llm.active_backend(), "none")
            post.assert_not_called()


class SharedJsonParserTests(SimpleTestCase):
    def test_parses_json_objects_and_arrays(self):
        for payload in ({"category": "Woodworking", "difficulty": 2}, [{"step": "Read"}]):
            with self.subTest(payload=payload):
                self.assertEqual(llm._parse_json(json.dumps(payload)), payload)

    def test_extracts_json_from_mixed_response(self):
        self.assertEqual(llm._parse_json('Here is your JSON: {"a": 1} hope that helps.'), {"a": 1})

    def test_extracts_json_array_from_mixed_response(self):
        self.assertEqual(llm._parse_json('Suggested steps: ["Read", "Write"] done.'), ["Read", "Write"])

    def test_strips_markdown_code_fence(self):
        for fence in ("json", "JSON", ""):
            with self.subTest(fence=fence):
                self.assertEqual(llm._parse_json(f'```{fence}\n{{"a": 1}}\n```'), {"a": 1})

    def test_skips_invalid_object_when_a_valid_array_is_present(self):
        self.assertEqual(llm._parse_json('Invalid {object}; valid [1, 2] follows.'), [1, 2])

    def test_unparseable_or_empty_response_raises_llm_error(self):
        for text in ("", "   ", "not JSON", '{"broken": invalid}', "unclosed ["):
            with self.subTest(text=text), self.assertRaises(llm.LLMError):
                llm._parse_json(text)


@override_settings(
    LLM_BACKEND="anthropic",
    ANTHROPIC_API_KEY="sk-test",
    CLAUDE_MODEL="claude-haiku-4-5-20251001",
)
class AnthropicBackendTests(SimpleTestCase):
    def _stub_anthropic_module(self, text):
        """Build a fake `anthropic` module whose client returns ``text``."""
        message = MagicMock()
        message.content = [MagicMock(type="text", text=text)]
        message.stop_reason = "end_turn"
        client = MagicMock()
        client.messages.create.return_value = message
        client.__enter__.return_value = client
        module = MagicMock()
        module.Anthropic.return_value = client
        return module, client

    def test_complete_json_round_trip(self):
        module, client = self._stub_anthropic_module('{"a": 1}')
        with patch.dict("sys.modules", {"anthropic": module}):
            self.assertEqual(llm.complete_json(prompt="hi", max_tokens=42), {"a": 1})
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(kwargs["max_tokens"], 42)
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "hi"}])
        self.assertNotIn("system", kwargs)

    def test_passes_system_when_provided(self):
        module, client = self._stub_anthropic_module('{"a": 1}')
        with patch.dict("sys.modules", {"anthropic": module}):
            llm.complete_json(prompt="hi", system="be terse")
        self.assertEqual(client.messages.create.call_args.kwargs["system"], "be terse")

    def test_deployment_defaults_keep_sdk_transport_options(self):
        module, _ = self._stub_anthropic_module('{"a": 1}')
        with patch.dict("sys.modules", {"anthropic": module}):
            self.assertEqual(llm.complete_json(prompt="hi"), {"a": 1})
        module.Anthropic.assert_called_once_with(api_key="sk-test")

    def test_default_response_handling_still_parses_complete_json_at_token_limit(self):
        module, client = self._stub_anthropic_module('{"a": 1}')
        client.messages.create.return_value.stop_reason = "max_tokens"
        with patch.dict("sys.modules", {"anthropic": module}):
            self.assertEqual(llm.complete_json(prompt="hi"), {"a": 1})

    def test_empty_content_raises_llm_error(self):
        module, _ = self._stub_anthropic_module("")
        with patch.dict("sys.modules", {"anthropic": module}):
            with self.assertRaises(llm.LLMError):
                llm.complete_json(prompt="hi")


@override_settings(LLM_BACKEND="none", ANTHROPIC_API_KEY="deployment-key")
class FamilyProviderOverrideTests(SimpleTestCase):
    def test_openai_uses_explicit_key_model_and_stateless_responses(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [
                    {"type": "output_text", "text": '{"steps": []}'},
                ]},
            ],
        }
        with patch("requests.post", return_value=response) as post:
            result = llm.complete_json(prompt="Return JSON", max_tokens=8192,
                system="Be kind", backend="openai", api_key="family-key", model="gpt-example")
        self.assertEqual(result, {"steps": []})
        post.assert_called_once_with(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": "Bearer family-key", "Content-Type": "application/json"},
            json={"model": "gpt-example", "input": "Return JSON", "max_output_tokens": 8192,
                  "store": False, "instructions": "Be kind"},
            timeout=120, allow_redirects=False,
        )
        self.assertEqual(llm.active_backend(), "none")

    def test_anthropic_override_collects_text_after_thinking(self):
        module = MagicMock()
        client = module.Anthropic.return_value
        client.__enter__.return_value = client
        client.messages.create.return_value.content = [
            MagicMock(type="thinking", thinking="private reasoning"),
            MagicMock(type="text", text='{"steps": []}'),
        ]
        client.messages.create.return_value.stop_reason = "end_turn"
        with patch.dict("sys.modules", {"anthropic": module}):
            result = llm.complete_json(prompt="Return JSON", backend="anthropic",
                api_key="family-key", model="claude-example")
        self.assertEqual(result, {"steps": []})
        self.assertEqual(module.Anthropic.call_args.kwargs["api_key"], "family-key")
        self.assertEqual(module.Anthropic.call_args.kwargs["max_retries"], 0)
        self.assertEqual(client.messages.create.call_args.kwargs["model"], "claude-example")

    def test_incomplete_override_never_falls_back_to_deployment_credentials(self):
        for kwargs in ({"backend": "anthropic", "model": "claude-example"},
                       {"api_key": "key", "model": "example"},
                       {"backend": "ollama", "api_key": "key", "model": "example"},
                       {"backend": "openai", "api_key": "key"}):
            with self.subTest(kwargs=kwargs), patch("requests.post") as post:
                with self.assertRaises(llm.LLMError):
                    llm.complete_json(prompt="Return JSON", **kwargs)
                post.assert_not_called()

    def test_openai_failures_and_redirects_are_sanitized(self):
        response = MagicMock(status_code=302)
        with patch("requests.post", return_value=response):
            with self.assertRaises(llm.LLMError):
                llm.complete_json(prompt="Return JSON", backend="openai", api_key="key", model="x")
        for backend in ("openai", "anthropic"):
            with self.subTest(backend=backend):
                module = MagicMock()
                module.Anthropic.side_effect = RuntimeError("private-key-and-homework")
                with patch.dict("sys.modules", {"anthropic": module}), patch(
                    "requests.post", side_effect=RuntimeError("private-key-and-homework")
                ):
                    try:
                        llm.complete_json(prompt="Return JSON", backend=backend, api_key="key", model="x")
                    except llm.LLMError:
                        self.assertNotIn("private-key-and-homework", traceback.format_exc())
                    else:
                        self.fail("Provider error must fail safely")

    def test_openai_rejects_truncated_empty_refused_or_malformed_content(self):
        for payload in (
            {"status": "incomplete", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": '{"valid_but_incomplete": true}'},
            ]}]},
            {"status": "completed", "output": []},
            {"status": "completed", "output": [{"type": "message", "content": [
                {"type": "refusal", "refusal": "no"},
            ]}]},
            {"status": "completed", "output": "invalid"},
        ):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = payload
            with self.subTest(payload=payload), patch("requests.post", return_value=response):
                with self.assertRaises(llm.LLMError):
                    llm.complete_json(prompt="Return JSON", backend="openai", api_key="key", model="x")

    def test_anthropic_rejects_truncation_even_if_json_is_valid(self):
        module = MagicMock()
        client = module.Anthropic.return_value
        client.__enter__.return_value = client
        client.messages.create.return_value.content = [MagicMock(type="text", text='{"partial": true}')]
        client.messages.create.return_value.stop_reason = "max_tokens"
        with patch.dict("sys.modules", {"anthropic": module}):
            with self.assertRaises(llm.LLMError):
                llm.complete_json(prompt="Return JSON", backend="anthropic", api_key="key", model="x")
