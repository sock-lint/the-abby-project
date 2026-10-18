"""Google authorization limits share an identity with the durable flow cap."""
from ipaddress import ip_address, ip_network

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


def _address(value):
    if not isinstance(value, str) or len(value) > 64 or "%" in value:
        return None
    try:
        address = ip_address(value.strip())
    except ValueError:
        return None
    # A mapped IPv4 address must not create a second caller identity.
    return getattr(address, "ipv4_mapped", None) or address


def _trusted_networks():
    configured = getattr(settings, "GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS", ()) or ()
    if isinstance(configured, str):
        configured = (configured,)
    networks = []
    for value in configured:
        try:
            networks.append(ip_network(value))
        except (TypeError, ValueError):
            continue  # Invalid configuration never grants proxy trust.
    return networks


def _client_address(request):
    peer = _address(request.META.get("REMOTE_ADDR"))
    if peer is None:
        return "unknown"
    networks = _trusted_networks()

    def trusted(address):
        return any(address in network for network in networks)

    if not trusted(peer):
        return str(peer)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if not isinstance(forwarded, str) or not forwarded or len(forwarded) > 4096:
        return str(peer)
    values = forwarded.split(",")
    if len(values) > 32:
        return str(peer)
    addresses = [_address(value) for value in values]
    if any(address is None for address in addresses):
        return str(peer)
    # Only a configured proxy can vouch for the hop immediately to its left.
    # Stop before any attacker-controlled prefix beyond the first caller.
    caller = peer
    for address in reversed(addresses):
        if not trusted(caller):
            break
        caller = address
    return str(caller)


def google_client_identity(request):
    """Use authenticated identity, otherwise the caller behind trusted proxies."""
    user = getattr(request, "user", None)
    if user and user.is_authenticated and user.pk is not None:
        return f"user:{user.pk}"
    return f"ip:{_client_address(request)}"


class GoogleOAuthThrottle(ScopedRateThrottle):
    def get_ident(self, request):
        return google_client_identity(request)

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
