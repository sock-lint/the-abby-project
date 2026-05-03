"""Safe URL fetching — block SSRF against internal services.

Audit H4: parent-supplied URLs flow into ``apps/rpg/sprite_authoring.py``
(``register_sprite``), ``apps/rpg/sprite_generation.py``
(``_fetch_reference_image``) and ``apps/ingestion/pipeline/base.py``
(``fetch_cached``). Without this guard, a parent — or an LLM with a parent
token via MCP — could hit cloud-metadata IPs (169.254.169.254), internal
services (``http://internal-redis:6379/``), or LAN-only hosts. The
response can then be exfiltrated via the error path or, in the sprite
authoring case, persisted as a sprite blob.

This module provides ``safe_get(url, **kwargs)`` — a drop-in replacement
for ``requests.get`` that validates the URL before each network hop:

  * scheme MUST be ``http`` or ``https``
  * host MUST resolve only to public IPs (rejects private, loopback,
    link-local, reserved, unspecified, multicast); IPv4 + IPv6 both checked
  * redirects are followed manually (max 5) so each hop is re-validated —
    a public-IP host can't 302 the request into a private-IP target

Raises ``UnsafeURLError`` (subclass of ``ValueError``) on rejection so
call sites can either propagate or wrap into a domain-specific exception.

A small TOCTOU race exists between resolution and the actual TCP connect:
DNS could swap the IP between the validate-and-fetch steps. Closing it
properly requires pinning the connection to the resolved IP (custom
``requests`` adapter + manual SNI), which is invasive and brittle. The
window is small in practice and this guard still blocks 99% of the
relevant attack surface.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import requests


class UnsafeURLError(ValueError):
    """Raised when a URL is rejected by the SSRF safety check."""


_ALLOWED_SCHEMES = ("http", "https")
_MAX_REDIRECTS = 5


def _ip_is_unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True for any IP that should never be fetched server-side."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def validate_url(url: str) -> None:
    """Parse + validate a URL. Raises ``UnsafeURLError`` on rejection.

    Exposed publicly so callers that pre-validate (before scheduling a
    Celery task, say) can reuse the same logic without making a request.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"URL scheme {scheme!r} not allowed; expected http or https",
        )
    host = parsed.hostname
    if not host:
        raise UnsafeURLError(f"URL {url!r} has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        # Can't resolve = can't safely fetch. Better to fail than to
        # allow a request whose target we can't classify.
        raise UnsafeURLError(f"could not resolve host {host!r}: {exc}")
    for info in infos:
        addr = info[4][0]
        # IPv6 results may include a zone id ("fe80::1%eth0") — strip it
        # before parsing.
        addr = addr.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_is_unsafe(ip):
            raise UnsafeURLError(
                f"host {host!r} resolves to non-public IP {addr}",
            )


def safe_get(url: str, **kwargs: Any) -> requests.Response:
    """Drop-in replacement for ``requests.get`` with SSRF validation.

    Manually follows up to 5 redirects, re-validating each hop.
    ``allow_redirects`` is always forced to False on the underlying
    request so this function controls redirect handling — silently
    overrides any caller-supplied value rather than erroring (most
    callers don't think about it and the safe default is "we own this").
    """
    kwargs.pop("allow_redirects", None)
    current_url = url
    for _ in range(_MAX_REDIRECTS + 1):
        validate_url(current_url)
        resp = requests.get(current_url, allow_redirects=False, **kwargs)
        if resp.is_redirect or resp.is_permanent_redirect:
            target = resp.headers.get("Location")
            if not target:
                # Malformed redirect — give the caller the response so
                # they can decide what to do.
                return resp
            current_url = urljoin(current_url, target)
            continue
        return resp
    raise UnsafeURLError(f"too many redirects starting from {url!r}")
