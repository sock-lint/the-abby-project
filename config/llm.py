"""Single text-LLM seam for the project.

All call sites that ask a language model for a JSON response (ingestion
enrichment, project suggestions, homework planning) route through
``complete_json`` here instead of importing the Anthropic SDK directly.
That keeps the choice of backend (hosted Anthropic vs a local Ollama
server on the LAN) at the settings layer rather than at every call site.

Settings (read via ``django.conf.settings``):

- ``LLM_BACKEND``         "auto" (default) | "anthropic" | "ollama" | "none"
- ``ANTHROPIC_API_KEY``   secret; when set + backend allows, Anthropic wins
- ``CLAUDE_MODEL``        Anthropic model id (default haiku)
- ``OLLAMA_BASE_URL``     e.g. "http://ollama.lan:11434" (no trailing /api)
- ``OLLAMA_MODEL``        e.g. "llama3.1:8b" (default)
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


def complete_json(
    *,
    prompt: str,
    max_tokens: int = 2048,
    system: str | None = None,
) -> Any:
    """Send a one-shot prompt and return parsed JSON.

    Raises :class:`LLMUnavailable` if no backend is configured — callers
    should catch this and fall back to their non-AI path. Raises
    :class:`LLMError` on transport, parse, or empty-response failures.
    """
    backend = active_backend()
    if backend == "anthropic":
        text = _anthropic_complete(prompt=prompt, max_tokens=max_tokens, system=system)
    elif backend == "ollama":
        text = _ollama_complete(prompt=prompt, max_tokens=max_tokens, system=system)
    else:
        raise LLMUnavailable("No LLM backend configured.")

    return _parse_json(text)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
def _anthropic_complete(*, prompt: str, max_tokens: int, system: str | None) -> str:
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise LLMError("anthropic package not installed") from exc

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    model = getattr(settings, "CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    try:
        client = anthropic.Anthropic(api_key=api_key)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        message = client.messages.create(**kwargs)
        text = (message.content[0].text or "").strip() if message.content else ""
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"anthropic request failed: {exc}") from exc
    if not text:
        raise LLMError("anthropic returned empty content")
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
    model = getattr(settings, "OLLAMA_MODEL", "llama3.1:8b")
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
