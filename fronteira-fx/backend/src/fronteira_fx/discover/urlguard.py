"""Only public http(s) URLs may be probed: no localhost, private/link-local/reserved IPs, no file:, no credentials.

`resolver` is injectable so tests never touch the network. Hostnames are resolved once here; the capture
step also checks every request the browser makes (see capture.py), which covers redirects and sub-resources.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

Resolver = Callable[[str], list[str]]

_FORBIDDEN_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "metadata.google.internal"}


class UnsafeUrl(ValueError):
    """The URL is not a public http(s) address."""


def _system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


def check_public_url(url: str, *, resolver: Resolver | None = None) -> str:
    """Return the URL unchanged when it is public; raise UnsafeUrl otherwise."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrl(f"somente http(s) é aceito, não {parts.scheme or 'esquema vazio'!r}")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrl("URL com usuário ou senha não é aceita")
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise UnsafeUrl("URL sem host")
    if host in _FORBIDDEN_NAMES or host.endswith(".localhost") or host.endswith(".local"):
        raise UnsafeUrl(f"host local não é aceito: {host}")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not is_public_ip(str(literal)):
            raise UnsafeUrl(f"IP não público não é aceito: {host}")
        return url
    try:
        addresses = (resolver or _system_resolver)(host)
    except OSError as exc:
        raise UnsafeUrl(f"host não resolve: {host} ({exc})") from exc
    if not addresses:
        raise UnsafeUrl(f"host não resolve: {host}")
    private = [a for a in addresses if not is_public_ip(a)]
    if private:
        raise UnsafeUrl(f"host {host} aponta para endereço não público")
    return url
