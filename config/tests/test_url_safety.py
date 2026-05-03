"""Tests for the SSRF-blocking ``safe_get`` helper.

Mocks ``socket.getaddrinfo`` to control DNS resolution outcomes, and
``requests.get`` to verify the actual request never fires for rejected
URLs. The IP-classification logic is verified directly against literal
IPs (no DNS round-trip needed for AAAA records).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from django.test import TestCase

from config.url_safety import (
    UnsafeURLError,
    safe_get,
    validate_url,
)


def _fake_getaddrinfo(addrs):
    """Build a getaddrinfo replacement that returns fixed IPs.

    socket.getaddrinfo returns a list of 5-tuples
    ``(family, type, proto, canonname, sockaddr)`` where ``sockaddr`` is
    ``(addr, port)`` for IPv4 and ``(addr, port, flowinfo, scope)`` for
    IPv6. Tests only care about ``addr``, so we hand back a minimal stub.
    """
    return [(2, 1, 0, "", (a, 0)) for a in addrs]


class ValidateUrlSchemeTests(TestCase):
    def test_rejects_ftp(self):
        with self.assertRaises(UnsafeURLError) as ctx:
            validate_url("ftp://example.com/file")
        self.assertIn("scheme", str(ctx.exception))

    def test_rejects_file(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("file:///etc/passwd")

    def test_rejects_javascript(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("javascript:alert(1)")

    def test_rejects_gopher(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("gopher://example.com")


class ValidateUrlHostTests(TestCase):
    def test_rejects_no_host(self):
        with self.assertRaises(UnsafeURLError) as ctx:
            validate_url("http:///path")
        self.assertIn("no host", str(ctx.exception))

    def test_rejects_unresolvable_host(self):
        with patch(
            "config.url_safety.socket.getaddrinfo",
            side_effect=__import__("socket").gaierror("Name or service not known"),
        ):
            with self.assertRaises(UnsafeURLError) as ctx:
                validate_url("http://nonexistent.invalid/")
        self.assertIn("could not resolve", str(ctx.exception))


class ValidateUrlIpClassTests(TestCase):
    """The full set of IP categories that should be rejected. Each test
    pins a specific real-world SSRF target — the names are the docs."""

    def test_rejects_aws_metadata_169_254(self):
        with self.assertRaises(UnsafeURLError) as ctx:
            validate_url("http://169.254.169.254/latest/meta-data/")
        self.assertIn("non-public IP", str(ctx.exception))

    def test_rejects_loopback_127(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://127.0.0.1:6379/")

    def test_rejects_loopback_localhost(self):
        with patch(
            "config.url_safety.socket.getaddrinfo",
            return_value=_fake_getaddrinfo(["127.0.0.1"]),
        ):
            with self.assertRaises(UnsafeURLError):
                validate_url("http://localhost/")

    def test_rejects_private_class_a_10(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://10.0.0.5/")

    def test_rejects_private_class_b_172_16(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://172.16.5.10/")

    def test_rejects_private_class_c_192_168(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://192.168.1.1/")

    def test_rejects_ipv6_loopback(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://[::1]/")

    def test_rejects_ipv6_unique_local(self):
        # fc00::/7 — IPv6 private/ULA range
        with self.assertRaises(UnsafeURLError):
            validate_url("http://[fc00::1]/")

    def test_rejects_unspecified_0_0_0_0(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://0.0.0.0/")

    def test_rejects_internal_host_resolving_to_private_ip(self):
        # Simulate a /etc/hosts trick or a DNS rebind: hostname "internal"
        # resolves to an RFC1918 address. validate_url must reject.
        with patch(
            "config.url_safety.socket.getaddrinfo",
            return_value=_fake_getaddrinfo(["10.5.0.20"]),
        ):
            with self.assertRaises(UnsafeURLError):
                validate_url("http://internal-redis/")

    def test_rejects_when_any_resolved_ip_is_private(self):
        # DNS returns one public + one private IP — must reject. (Defends
        # against DNS-rebinding-style splits where the attacker controls
        # one of multiple A records.)
        with patch(
            "config.url_safety.socket.getaddrinfo",
            return_value=_fake_getaddrinfo(["8.8.8.8", "10.0.0.1"]),
        ):
            with self.assertRaises(UnsafeURLError):
                validate_url("http://multi.example.com/")


class ValidateUrlPublicTests(TestCase):
    def test_accepts_public_https(self):
        with patch(
            "config.url_safety.socket.getaddrinfo",
            return_value=_fake_getaddrinfo(["93.184.216.34"]),
        ):
            # Returns None (no exception) on success.
            self.assertIsNone(validate_url("https://example.com/"))

    def test_accepts_public_http(self):
        with patch(
            "config.url_safety.socket.getaddrinfo",
            return_value=_fake_getaddrinfo(["8.8.8.8"]),
        ):
            self.assertIsNone(validate_url("http://dns.google/"))


class SafeGetTests(TestCase):
    def test_unsafe_url_does_not_call_requests(self):
        # The actual request must never fire if validation fails.
        with patch("config.url_safety.requests.get") as mock_get:
            with self.assertRaises(UnsafeURLError):
                safe_get("http://169.254.169.254/")
        mock_get.assert_not_called()

    def test_safe_url_returns_response(self):
        mock_resp = MagicMock(
            is_redirect=False, is_permanent_redirect=False,
            status_code=200, content=b"ok",
        )
        with patch(
            "config.url_safety.socket.getaddrinfo",
            return_value=_fake_getaddrinfo(["93.184.216.34"]),
        ), patch(
            "config.url_safety.requests.get", return_value=mock_resp,
        ) as mock_get:
            resp = safe_get("https://example.com/")
        self.assertIs(resp, mock_resp)
        # allow_redirects must be forced to False so we control the
        # redirect chain and re-validate each hop.
        _, kwargs = mock_get.call_args
        self.assertFalse(kwargs["allow_redirects"])

    def test_redirect_to_private_ip_is_blocked(self):
        # First hop: public, returns 302 → http://10.0.0.5/internal.
        # safe_get must validate the second hop and reject.
        first_resp = MagicMock(
            is_redirect=True, is_permanent_redirect=False,
            headers={"Location": "http://10.0.0.5/internal"},
        )
        # If the second .get() ever fires, fail loudly.
        second_resp = MagicMock()

        getaddrinfo_calls = []

        def fake_resolve(host, *args, **kwargs):
            getaddrinfo_calls.append(host)
            if host == "example.com":
                return _fake_getaddrinfo(["93.184.216.34"])
            return _fake_getaddrinfo(["10.0.0.5"])

        with patch(
            "config.url_safety.socket.getaddrinfo",
            side_effect=fake_resolve,
        ), patch(
            "config.url_safety.requests.get",
            side_effect=[first_resp, second_resp],
        ) as mock_get:
            with self.assertRaises(UnsafeURLError):
                safe_get("https://example.com/")
        # Only the first hop fired; the second was rejected before request.
        self.assertEqual(mock_get.call_count, 1)

    def test_redirect_chain_terminates_after_max_hops(self):
        # 6 redirects in a row → exceeds _MAX_REDIRECTS=5 → UnsafeURLError.
        redirect = MagicMock(
            is_redirect=True, is_permanent_redirect=False,
            headers={"Location": "https://example.com/next"},
        )
        with patch(
            "config.url_safety.socket.getaddrinfo",
            return_value=_fake_getaddrinfo(["93.184.216.34"]),
        ), patch(
            "config.url_safety.requests.get",
            return_value=redirect,
        ):
            with self.assertRaises(UnsafeURLError) as ctx:
                safe_get("https://example.com/")
        self.assertIn("too many redirects", str(ctx.exception))
