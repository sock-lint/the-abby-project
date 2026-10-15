"""Single text-LLM seam for the project.

All call sites that ask a language model for a JSON response (ingestion
enrichment, project suggestions, homework planning) route through
``complete_json`` here instead of importing the Anthropic SDK directly.
Deployment defaults live in settings. Homework may supply an explicit
family-owned OpenAI or Anthropic connection for that request only.

Settings (read via ``django.conf.settings``):

- ``LLM_BACKEND``         "auto" (default) | "anthropic" | "ollama" | "none"
- ``ANTHROPIC_API_KEY``   secret; when set + backend allows, Anthropic wins
- ``CLAUDE_MODEL``        Anthropic model id (default haiku)
- ``OLLAMA_BASE_URL``     e.g. "http://ollama.lan:11434" (no trailing /api)
- ``OLLAMA_MODEL``        e.g. "gemma4:latest" (default)
- ``OLLAMA_TIMEOUT``      seconds for a single request (default 120)

"auto" picks Anthropic when a key is set, then Ollama when a base URL is
set, then falls back to "none" — same opt-in shape as today's call sites
which all treat the LLM as optional.
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
    """Return the resolved backend slug: ``anthropic``, ``ollama``, or ``none``.

    ``LLM_BACKEND="auto"`` (the default) prefers Anthropic when a key is
    configured, then Ollama when a base URL is configured.
    """
    requested = (getattr(settings, "LLM_BACKEND", "auto") or "auto").lower()
    if requested == "anthropic":
        return "anthropic" if getattr(settings, "ANTHROPIC_API_KEY", "") else "none"
    if requested == "ollama":
        return "ollama" if getattr(settings, "OLLAMA_BASE_URL", "") else "none"
    if requested == "none":
        return "none"
    # auto
    if getattr(settings, "ANTHROPIC_API_KEY", ""):
        return "anthropic"
    if getattr(settings, "OLLAMA_BASE_URL", ""):
        return "ollama"
    return "none"


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
    elif backend == "ollama":
        text = _ollama_complete(prompt=prompt, max_tokens=max_tokens, system=system)
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

    api_key = api_key if api_key is not None else getattr(settings, "ANTHROPIC_API_KEY", "")
    model = model if model is not None else getattr(settings, "CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    try:
        with anthropic.Anthropic(
            api_key=api_key, base_url="https://api.anthropic.com", timeout=120, max_retries=0,
        ) as client:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            message = client.messages.create(**kwargs)
            if message.stop_reason not in {"end_turn", "stop_sequence"}:
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
# Ollama
# ---------------------------------------------------------------------------
def _ollama_complete(*, prompt: str, max_tokens: int, system: str | None) -> str:
    """Call Ollama's /api/generate with ``format: "json"`` for strict JSON.

    Ollama's JSON mode constrains the sampler to emit a syntactically valid
    JSON object — schema-less, but better than free-form text + regex
    cleanup. We still parse defensively because models can over-truncate.
    """
    import requests  # locally available via requirements.txt

    base_url = (getattr(settings, "OLLAMA_BASE_URL", "") or "").rstrip("/")
    model = getattr(settings, "OLLAMA_MODEL", "gemma4:latest")
    timeout = float(getattr(settings, "OLLAMA_TIMEOUT", 120))
    if not base_url:
        raise LLMError("OLLAMA_BASE_URL is not set")

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"num_predict": max_tokens},
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(
            f"{base_url}/api/generate", json=payload, timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"ollama request failed: {exc}") from exc

    text = (data.get("response") or "").strip()
    if not text:
        raise LLMError("ollama returned empty response")
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
