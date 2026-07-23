# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""SSRF-safe URL validation.

Used by webhook and outbound-webhook-like features to reject URLs that would
point a server-side HTTP client at the loopback interface, RFC1918 / carrier-
grade NAT / link-local ranges, cloud-metadata addresses, multicast, or any
non-http(s) scheme (``file://``, ``gopher://``, ``dict://`` …).

Two layers of protection:
    1. ``validate_external_url`` - synchronous, no DNS, good for Pydantic
       validators. Rejects bad schemes, literal IPs in blocklisted ranges,
       and the small set of hard-coded cloud metadata hostnames.
    2. ``resolve_and_validate_external_url`` - async, performs DNS lookup
       and rejects any resolved address in a blocklisted range. Call this
       right before ``httpx.post`` so a DNS rebinding or a hostname that
       resolves to a private IP is caught at dispatch time.

Both helpers raise ``UnsafeUrlError`` (a subclass of ``ValueError``) so they
can be used inside Pydantic field validators without any adapter layer.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

__all__ = [
    "UnsafeUrlError",
    "resolve_and_validate_ai_provider_url",
    "resolve_and_validate_external_url",
    "validate_ai_provider_url",
    "validate_external_url",
]


_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Hostnames that are *always* unsafe regardless of DNS result. The cloud
# metadata addresses resolve to link-local ranges anyway, but listing them
# explicitly guards against proxies / split-horizon DNS that rewrite the
# hostname to a public IP. ``localhost`` and friends are blocked here so
# the sync validator catches them without waiting for the async DNS path.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "broadcasthost",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "169.254.169.254",
        "fd00:ec2::254",
    }
)


class UnsafeUrlError(ValueError):
    """Raised when a URL points at a blocklisted host or scheme."""


def _is_blocked_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if *addr* is in a blocklisted range."""
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _parse_host(url: str) -> tuple[str, str]:
    """Return (scheme, hostname) or raise UnsafeUrlError on malformed input."""
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise UnsafeUrlError(f"Invalid URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"URL scheme {scheme!r} is not allowed - use http or https")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UnsafeUrlError("URL is missing a hostname")

    return scheme, host


def validate_external_url(url: str) -> str:
    """Reject URLs that are trivially unsafe (bad scheme, literal private IP).

    This check is synchronous and makes no DNS calls, so it is cheap enough
    to run inside a Pydantic validator. For defence in depth, pair it with
    :func:`resolve_and_validate_external_url` at dispatch time.
    """
    _, host = _parse_host(url)

    if host in _BLOCKED_HOSTNAMES:
        raise UnsafeUrlError(f"Hostname {host!r} is blocked")

    # Is the host a literal IP address?
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return url  # hostname - resolve later

    if _is_blocked_address(addr):
        raise UnsafeUrlError(f"URL targets non-routable address {addr}")

    return url


async def resolve_and_validate_external_url(url: str) -> str:
    """Resolve *url*'s hostname and reject if any resolved IP is blocklisted.

    This is the second line of defence, run right before HTTP dispatch so
    DNS-rebinding and split-horizon setups cannot sneak a private address
    past the sync validator.
    """
    validate_external_url(url)  # fast-path
    _, host = _parse_host(url)

    # Skip DNS for literal IPs - already validated above.
    try:
        ipaddress.ip_address(host)
        return url
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            host,
            None,
            proto=socket.IPPROTO_TCP,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Hostname does not resolve: {host}") from exc

    for info in infos:
        raw_addr = info[4][0]
        try:
            addr = ipaddress.ip_address(raw_addr)
        except ValueError:
            continue
        if _is_blocked_address(addr):
            raise UnsafeUrlError(f"Hostname {host!r} resolves to non-routable address {addr}")

    return url


# ── Self-hosted AI provider endpoints (Ollama / vLLM) ────────────────────────
#
# The AI-settings page lets a user point the platform at a self-hosted, OpenAI-
# compatible runtime (Ollama, vLLM) by URL, which is then fetched server-side -
# an SSRF vector. Unlike a webhook it LEGITIMATELY needs to reach loopback
# (Ollama on localhost) and RFC1918 (vLLM on a Docker / LAN host), so the
# webhook policy above (which blocks all loopback / private) is too strict here.
#
# The AI policy therefore permits loopback and private ranges by default while
# ALWAYS blocking the ranges an inference endpoint has no business reaching:
# link-local (which covers the 169.254.169.254 cloud-metadata address),
# multicast, reserved, unspecified, and the known IPv6 cloud-metadata address.
# Operators who want a tighter posture configure an allowlist (hostnames and/or
# CIDR ranges); when set, only hosts in it are accepted.

# Cloud-metadata hostnames that are never a valid AI endpoint. Unlike the
# webhook block-list this deliberately does NOT include ``localhost`` - a local
# Ollama is a first-class, supported setup.
_AI_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "169.254.169.254",
        "fd00:ec2::254",
    }
)

# Metadata addresses that stay blocked even though some sit inside the private
# ranges the AI policy otherwise permits. 169.254.169.254 is already link-local;
# the AWS IPv6 IMDS fd00:ec2::254 lives in the fc00::/7 ULA range and would
# otherwise pass the private-is-ok rule.
_AI_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)


def _ai_address_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Address ranges unsafe even for a self-hosted AI endpoint.

    Loopback and private are permitted (Ollama / vLLM); everything an inference
    URL should never reach - link-local (which covers the cloud-metadata
    address), multicast, unspecified, and the known metadata addresses - is not.

    ``is_reserved`` is deliberately NOT used: on IPv6 it also flags the loopback
    ``::1`` (it falls in the reserved ``::/8`` block), which a local Ollama
    legitimately resolves to. IPv4-mapped IPv6 (``::ffff:a.b.c.d``) is unwrapped
    first so a mapped form of a blocked range cannot slip through.
    """
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped
    return (
        addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
        or addr in _AI_METADATA_ADDRESSES
    )


def _host_in_allowlist(host: str, allowlist: list[str]) -> bool:
    """Return True if *host* matches any allowlist entry.

    Entries are exact hostnames (case-insensitive) or IP networks in CIDR
    notation (a bare IP is treated as a single-address network). A CIDR entry
    matches only a literal-IP host inside that network; a hostname entry matches
    the URL host string exactly.
    """
    host = host.strip().lower()
    try:
        host_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(host)
    except ValueError:
        host_ip = None
    for raw in allowlist:
        entry = (raw or "").strip().lower()
        if not entry:
            continue
        if host_ip is not None:
            try:
                if host_ip in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                pass  # entry is not a network - fall through to hostname compare
        if host_ip is None and host == entry:
            return True
    return False


def validate_ai_provider_url(url: str, allowlist: list[str] | None = None) -> str:
    """Validate a user-supplied self-hosted AI endpoint (Ollama / vLLM).

    Synchronous and DNS-free, so it is safe inside a Pydantic validator. Rejects
    non-http(s) schemes, cloud-metadata hostnames, and literal IPs in a blocked
    range. Loopback and private literals are allowed so local runtimes work out
    of the box, UNLESS *allowlist* is non-empty, in which case the host must
    appear in it. Pair with :func:`resolve_and_validate_ai_provider_url` at
    dispatch time to also catch DNS rebinding.
    """
    _, host = _parse_host(url)

    if host in _AI_BLOCKED_HOSTNAMES:
        raise UnsafeUrlError(f"Hostname {host!r} is blocked")

    allow = [a for a in (allowlist or []) if a and a.strip()]
    if allow and not _host_in_allowlist(host, allow):
        raise UnsafeUrlError(f"Host {host!r} is not in the AI provider allowlist")

    # Literal-IP ranges are always enforced, allowlisted or not - an allowlist
    # entry can never re-enable a metadata / link-local address.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return url  # hostname - resolved and re-checked at dispatch time
    if _ai_address_blocked(addr):
        raise UnsafeUrlError(f"URL targets a blocked address {addr}")
    return url


async def resolve_and_validate_ai_provider_url(url: str, allowlist: list[str] | None = None) -> str:
    """Resolve *url* and reject if it maps to a blocked address.

    Dispatch-time defence for self-hosted AI endpoints: a hostname that passed
    the sync check but resolves to a link-local / cloud-metadata address (DNS
    rebinding) is caught here. Loopback and private resolved addresses are
    permitted (Ollama / vLLM).
    """
    validate_ai_provider_url(url, allowlist)
    _, host = _parse_host(url)

    try:
        ipaddress.ip_address(host)
        return url  # literal IP already validated above
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            host,
            None,
            proto=socket.IPPROTO_TCP,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Hostname does not resolve: {host}") from exc

    for info in infos:
        raw_addr = info[4][0]
        try:
            addr = ipaddress.ip_address(raw_addr)
        except ValueError:
            continue
        if _ai_address_blocked(addr):
            raise UnsafeUrlError(f"Hostname {host!r} resolves to a blocked address {addr}")

    return url
