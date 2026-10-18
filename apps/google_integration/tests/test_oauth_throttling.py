"""Proxy headers cannot create arbitrary Google authorization identities."""
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.google_integration.throttling import GoogleOAuthThrottle, google_client_identity


@override_settings(GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS=[])
class GoogleOAuthThrottleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.view = SimpleNamespace(throttle_scope="google_oauth")

    def request(self, peer="198.51.100.7", forwarded=None, user=None):
        request = self.factory.get("/api/auth/google/login/", REMOTE_ADDR=peer)
        if forwarded is not None:
            request.META["HTTP_X_FORWARDED_FOR"] = forwarded
        request.user = user or AnonymousUser()
        return request

    def allowed(self, request):
        with patch.object(GoogleOAuthThrottle, "THROTTLE_RATES", {"google_oauth": "2/min"}):
            return GoogleOAuthThrottle().allow_request(request, self.view)

    def test_varying_forwarded_headers_from_one_untrusted_peer_share_one_limit(self):
        requests = [self.request(forwarded=f"203.0.113.{number}") for number in range(1, 26)]
        self.assertEqual({google_client_identity(request) for request in requests}, {"ip:198.51.100.7"})
        self.assertEqual([self.allowed(request) for request in requests], [True, True] + [False] * 23)

    @override_settings(GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS=["10.0.0.0/24"])
    def test_trusted_appending_proxies_stop_at_first_untrusted_caller(self):
        requests = [
            self.request("10.0.0.10", f"{prefix}, 198.51.100.42, 10.0.0.9")
            for prefix in ("203.0.113.1", "203.0.113.2", "2001:db8::1")
        ]
        self.assertEqual({google_client_identity(request) for request in requests}, {"ip:198.51.100.42"})
        self.assertEqual([self.allowed(request) for request in requests], [True, True, False])

    @override_settings(GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS=["10.0.0.0/24"])
    def test_direct_peer_cannot_claim_to_be_behind_a_trusted_proxy(self):
        request = self.request("198.51.100.7", "203.0.113.44, 10.0.0.9")
        self.assertEqual(google_client_identity(request), "ip:198.51.100.7")

    def test_private_loopback_and_link_local_peers_have_no_implicit_trust(self):
        for peer in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.1.1", "::1", "fe80::1"):
            with self.subTest(peer=peer):
                self.assertEqual(google_client_identity(self.request(peer, "203.0.113.9")), f"ip:{peer}")

    @override_settings(GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS=["10.0.0.0/24"])
    def test_missing_malformed_and_excessive_forwarded_chains_fall_back_to_peer(self):
        for header in (
            None, "", "not-an-address", "198.51.100.2,", "198.51.100.2,,10.0.0.9",
            "198.51.100.2:443", '"198.51.100.2"', "fe80::1%spoofed",
            ",".join(["198.51.100.2"] * 33), "1" * 4097,
        ):
            with self.subTest(header=header):
                self.assertEqual(google_client_identity(self.request("10.0.0.10", header)), "ip:10.0.0.10")

    @override_settings(GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS=["2001:db8:ffff::/48"])
    def test_ipv6_proxy_chains_use_canonical_caller_addresses(self):
        request = self.request(
            "2001:db8:ffff::2",
            "2001:db8:0001:0000:0000:0000:0000:000a, 2001:db8:ffff::1",
        )
        self.assertEqual(google_client_identity(request), "ip:2001:db8:1::a")

    def test_ipv4_mapped_addresses_share_the_ipv4_identity(self):
        self.assertEqual(google_client_identity(self.request("::ffff:198.51.100.7")), "ip:198.51.100.7")

    def test_missing_or_invalid_transport_peer_has_one_unknown_identity(self):
        for peer in (None, "", "not-an-address", "127.0.0.1%spoofed"):
            with self.subTest(peer=peer):
                self.assertEqual(google_client_identity(self.request(peer, "203.0.113.9")), "ip:unknown")

    def test_authenticated_identity_is_consistent_across_networks_and_forwarded_headers(self):
        user = SimpleNamespace(pk=73, is_authenticated=True)
        requests = [
            self.request(peer, forwarded, user)
            for peer, forwarded in (
                ("198.51.100.7", "203.0.113.1"),
                ("203.0.113.9", "203.0.113.2"),
                ("2001:db8::1", None),
            )
        ]
        self.assertEqual({google_client_identity(request) for request in requests}, {"user:73"})
        self.assertEqual([GoogleOAuthThrottle().get_ident(request) for request in requests], ["user:73"] * 3)
        self.assertEqual([self.allowed(request) for request in requests], [True, True, False])
        other = self.request(user=SimpleNamespace(pk=74, is_authenticated=True))
        self.assertTrue(self.allowed(other))

    @override_settings(GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS=["invalid-cidr"])
    def test_invalid_proxy_configuration_does_not_grant_trust(self):
        self.assertEqual(google_client_identity(self.request("10.0.0.10", "203.0.113.9")), "ip:10.0.0.10")
