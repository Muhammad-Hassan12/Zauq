"""Authoritative SSRF Defense and URL Validation for Zauq v4.

Defends against Server-Side Request Forgery across:
- web.fetch (direct fetch and redirect chains)
- Autonomous research roamers
- MCP HTTP client connections
"""

from __future__ import annotations
import ipaddress
import logging
import socket
import urllib.parse
from typing import Set

logger = logging.getLogger("zauq.security.ssrf")

# Cloud metadata and loopback hostnames
_BLOCKED_HOSTNAMES: Set[str] = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
    "169.254.169.254",
    "metadata.nic.internal",
})

# Specific IP networks that must never be targeted by public web fetching
_ADDITIONAL_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),         # Current network (only valid as source)
    ipaddress.ip_network("100.64.0.0/10"),     # Shared address space / CGNAT (RFC 6598)
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmark testing (RFC 2544)
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved for future use (Class E)
    ipaddress.ip_network("fc00::/7"),          # IPv6 Unique Local Addresses (ULA)
    ipaddress.ip_network("fe80::/10"),         # IPv6 Link-Local
]


def is_safe_ip_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address belongs to public routable internet space."""
    # Handle IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return False

    # Check additional reserved / private ranges
    for net in _ADDITIONAL_BLOCKED_NETWORKS:
        try:
            if ip in net:
                return False
        except TypeError:
            # IPv4 vs IPv6 network mismatch
            continue

    return True


def is_safe_public_url(url: str) -> bool:
    """Validates that a URL:
    - Uses http or https scheme
    - Does not resolve to private, loopback, link-local, or cloud metadata endpoints
    - Is safe for outbound fetching from the backend server
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        hostname_lower = hostname.lower().strip("[]")
        if hostname_lower in _BLOCKED_HOSTNAMES:
            return False

        # Fast-path: direct IP address check
        try:
            direct_ip = ipaddress.ip_address(hostname_lower)
            return is_safe_ip_address(direct_ip)
        except ValueError:
            pass

        # DNS resolution check
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False

        for _family, _type, _proto, _canon, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if not is_safe_ip_address(ip):
                return False

        return True
    except Exception as exc:
        logger.debug(f"SSRF validation rejected '{url}': {exc}")
        return False


def validate_mcp_endpoint_url(url: str, allow_operator_private: bool = True) -> tuple[bool, str]:
    """Validate MCP streamable_http server URL.

    Operator configuration (mcp_servers.json) can point to private service URLs
    within the Docker network (e.g. http://my-mcp:8080).
    Non-operator/user input is strictly rejected if not a safe public URL.
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty."

    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid scheme '{parsed.scheme}'. MCP server URL must be http or https."

        if not parsed.hostname:
            return False, "Invalid URL: missing hostname."

        if not allow_operator_private:
            if not is_safe_public_url(url):
                return False, "Target URL resolves to private or restricted network address."

        return True, ""
    except Exception as e:
        return False, f"Malformed URL: {e}"
