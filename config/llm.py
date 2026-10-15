"""Single text-LLM seam for the project.

All call sites that ask a language model for a JSON response (ingestion
enrichment, project suggestions, homework planning) route through
``complete_json`` here instead of importing the Anthropic SDK directly.
Deployment defaults for ingestion and project suggestions live in settings.
Homework requires an explicit family-owned OpenAI or Anthropic connection.

Settings (read via ``django.conf.settings``):

- ``LLM_BACKEND``         "auto" (default) | "anthropic" | "none"
- ``ANTHROPIC_API_KEY``   secret; when set + backend allows, Anthropic wins
- ``CLAUDE_MODEL``        Anthropic model id (default haiku)

"auto" picks Anthropic when a key is set, otherwise "none". Unsupported
deployment backend values disable AI rather than select a different provider.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """No LLM backend is configured. Caller should fall back to non-AI path."""


class LLMError(RuntimeError):
    """An LLM call was attempted but the response could not be used."""


def active_backend() -> str:
    """Return the deployment backend: ``anthropic`` or ``none``.

    Only ``auto`` and ``anthropic`` permit a deployment key. ``none`` and
    unsupported settings stay disabled, including obsolete backend values.
    """
    requested = getattr(settings, "LLM_BACKEND", "auto")
    if not isinstance(requested, str) or requested.lower() not in {"auto", "anthropic"}:
        return "none"
    return "anthropic" if getattr(settings, "ANTHROPIC_API_KEY", "") else "none"


def is_available() -> bool:
    return active_backend() != "none"


@sensitive_variables()
def complete_json(
    *,
    prompt: str,
    max_tokens: int = 2048,
    system: str | None = None,
    backend: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> Any:
    """Send a one-shot prompt and return parsed JSON.

    Raises :class:`LLMUnavailable` if no backend is configured — callers
    should catch this and fall back to their non-AI path. Raises
    :class:`LLMError` on transport, parse, or empty-response failures.
    """
    # A partial family configuration must never borrow deployment credentials.
    override = any(value is not None for value in (backend, api_key, model))
    if override:
        if backend not in {"openai", "anthropic"} or not api_key or not model:
            raise LLMError("The AI connection needs a provider, API key and model.")
    else:
        backend = active_backend()
    if backend == "anthropic":
        text = _anthropic_complete(
            prompt=prompt, max_tokens=max_tokens, system=system, api_key=api_key, model=model,
        )
    elif backend == "openai":
        text = _openai_complete(
            prompt=prompt, max_tokens=max_tokens, system=system, api_key=api_key, model=model,
        )
    else:
        raise LLMUnavailable("No LLM backend configured.")

    return _parse_json(text)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
@sensitive_variables()
def _anthropic_complete(
    *, prompt: str, max_tokens: int, system: str | None,
    api_key: str | None = None, model: str | None = None,
) -> str:
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise LLMError("anthropic package not installed") from exc

    family_override = api_key is not None
    api_key = api_key if api_key is not None else getattr(settings, "ANTHROPIC_API_KEY", "")
    model = model if model is not None else getattr(settings, "CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    try:
        client_options: dict[str, Any] = {"api_key": api_key}
        if family_override:
            # Bound family-key calls without changing the deployment's retry
            # policy or its existing Anthropic proxy configuration.
            client_options.update(base_url="https://api.anthropic.com", timeout=120, max_retries=0)
        with anthropic.Anthropic(**client_options) as client:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            message = client.messages.create(**kwargs)
            if family_override and message.stop_reason not in {"end_turn", "stop_sequence"}:
                raise ValueError("Incomplete response")
            text = "".join(block.text for block in message.content if block.type == "text").strip()
    except Exception:  # noqa: BLE001
        # Provider exceptions may include request/response bodies and secrets.
        raise LLMError("Claude could not complete the request. Check the API key and model, then try again.") from None
    if not text:
        raise LLMError("anthropic returned empty content")
    return text


@sensitive_variables()
def _openai_complete(*, prompt: str, max_tokens: int, system: str | None, api_key: str, model: str) -> str:
    """Use the fixed Responses endpoint without retained conversation state."""
    import requests

    payload: dict[str, Any] = {
        "model": model, "input": prompt, "max_output_tokens": max_tokens, "store": False,
    }
    if system:
        payload["instructions"] = system
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=120, allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError("Request failed")
        data = response.json()
        if data.get("status") != "completed":
            raise ValueError("Incomplete response")
        text = "".join(
            block["text"]
            for item in data["output"] if item.get("type") == "message"
            for block in item["content"] if block.get("type") == "output_text"
        ).strip()
        if not text:
            raise ValueError("Empty response")
    except Exception:  # noqa: BLE001
        raise LLMError("OpenAI could not complete the request. Check the API key and model, then try again.") from None
    return text


# ---------------------------------------------------------------------------
# Shared parse
# ---------------------------------------------------------------------------
def _parse_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Last-resort: pull the first {...} or [...] block out of mixed text.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cleaned.find(opener)
            end = cleaned.rfind(closer) + 1
            if 0 <= start < end:
                try:
                    return json.loads(cleaned[start:end])
                except json.JSONDecodeError:
                    continue
        raise LLMError(f"could not parse JSON from LLM response: {exc}") from exc
