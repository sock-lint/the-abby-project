"""Tests for the unified LLM adapter (`config.llm`)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from config import llm


def _ollama_response(payload):
    """Build a stub `requests.post` return value for Ollama's /api/generate."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"response": json.dumps(payload)}
    return resp


@override_settings(
    LLM_BACKEND="auto",
    ANTHROPIC_API_KEY="",
    OLLAMA_BASE_URL="",
)
class ActiveBackendTests(SimpleTestCase):
    def test_auto_with_no_config_returns_none(self):
        self.assertEqual(llm.active_backend(), "none")
        self.assertFalse(llm.is_available())

    @override_settings(ANTHROPIC_API_KEY="key")
    def test_auto_prefers_anthropic_when_key_set(self):
        self.assertEqual(llm.active_backend(), "anthropic")

    @override_settings(OLLAMA_BASE_URL="http://lan:11434")
    def test_auto_falls_back_to_ollama(self):
        self.assertEqual(llm.active_backend(), "ollama")

    @override_settings(ANTHROPIC_API_KEY="key", OLLAMA_BASE_URL="http://lan:11434")
    def test_auto_anthropic_wins_when_both_configured(self):
        self.assertEqual(llm.active_backend(), "anthropic")

    @override_settings(LLM_BACKEND="ollama", ANTHROPIC_API_KEY="key", OLLAMA_BASE_URL="")
    def test_explicit_ollama_without_url_is_none(self):
        self.assertEqual(llm.active_backend(), "none")

    @override_settings(LLM_BACKEND="anthropic", ANTHROPIC_API_KEY="", OLLAMA_BASE_URL="http://x")
    def test_explicit_anthropic_without_key_is_none(self):
        self.assertEqual(llm.active_backend(), "none")

    @override_settings(LLM_BACKEND="none", ANTHROPIC_API_KEY="key", OLLAMA_BASE_URL="http://x")
    def test_explicit_none_disables_everything(self):
        self.assertEqual(llm.active_backend(), "none")


@override_settings(LLM_BACKEND="auto", ANTHROPIC_API_KEY="", OLLAMA_BASE_URL="")
class CompleteJsonUnavailableTests(SimpleTestCase):
    def test_raises_llm_unavailable_when_no_backend(self):
        with self.assertRaises(llm.LLMUnavailable):
            llm.complete_json(prompt="hi")


@override_settings(
    LLM_BACKEND="ollama",
    OLLAMA_BASE_URL="http://lan:11434",
    OLLAMA_MODEL="llama3.1:8b",
    OLLAMA_TIMEOUT=30,
)
class OllamaBackendTests(SimpleTestCase):
    def test_complete_json_round_trip(self):
        payload = {"category": "Woodworking", "difficulty": 2}
        with patch("requests.post", return_value=_ollama_response(payload)) as post:
            result = llm.complete_json(prompt="any", max_tokens=512)
        self.assertEqual(result, payload)
        # Verify the payload sent to Ollama.
        kwargs = post.call_args.kwargs
        body = kwargs["json"]
        self.assertEqual(body["model"], "llama3.1:8b")
        self.assertEqual(body["prompt"], "any")
        self.assertEqual(body["stream"], False)
        self.assertEqual(body["format"], "json")
        self.assertEqual(body["options"]["num_predict"], 512)
        self.assertEqual(post.call_args.args[0], "http://lan:11434/api/generate")

    def test_strips_trailing_slash_on_base_url(self):
        with override_settings(OLLAMA_BASE_URL="http://lan:11434/"):
            with patch("requests.post", return_value=_ollama_response({"x": 1})) as post:
                llm.complete_json(prompt="x")
        self.assertEqual(post.call_args.args[0], "http://lan:11434/api/generate")

    def test_passes_system_prompt_when_provided(self):
        with patch("requests.post", return_value=_ollama_response({"x": 1})) as post:
            llm.complete_json(prompt="p", system="be terse")
        self.assertEqual(post.call_args.kwargs["json"]["system"], "be terse")

    def test_empty_response_raises_llm_error(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"response": "   "}
        with patch("requests.post", return_value=resp):
            with self.assertRaises(llm.LLMError):
                llm.complete_json(prompt="x")

    def test_transport_error_raises_llm_error(self):
        with patch("requests.post", side_effect=RuntimeError("boom")):
            with self.assertRaises(llm.LLMError):
                llm.complete_json(prompt="x")

    def test_unparseable_response_raises_llm_error(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"response": "not json at all"}
        with patch("requests.post", return_value=resp):
            with self.assertRaises(llm.LLMError):
                llm.complete_json(prompt="x")

    def test_extracts_json_from_mixed_response(self):
        # Defensive parser pulls the first {...} block out of noisy text.
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": 'Sure! Here is your JSON: {"a": 1} hope that helps.'
        }
        with patch("requests.post", return_value=resp):
            self.assertEqual(llm.complete_json(prompt="x"), {"a": 1})

    def test_strips_markdown_code_fence(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"response": '```json\n{"a": 1}\n```'}
        with patch("requests.post", return_value=resp):
            self.assertEqual(llm.complete_json(prompt="x"), {"a": 1})


@override_settings(
    LLM_BACKEND="anthropic",
    ANTHROPIC_API_KEY="sk-test",
    CLAUDE_MODEL="claude-haiku-4-5-20251001",
)
class AnthropicBackendTests(SimpleTestCase):
    def _stub_anthropic_module(self, text):
        """Build a fake `anthropic` module whose client returns ``text``."""
        message = MagicMock()
        message.content = [MagicMock(text=text)]
        client = MagicMock()
        client.messages.create.return_value = message
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

    def test_empty_content_raises_llm_error(self):
        module, _ = self._stub_anthropic_module("")
        with patch.dict("sys.modules", {"anthropic": module}):
            with self.assertRaises(llm.LLMError):
                llm.complete_json(prompt="hi")
