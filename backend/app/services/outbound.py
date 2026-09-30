from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit


def normalize_host(host: str) -> str:
    if not isinstance(host, str) or not host.strip():
        raise ValueError("Outbound host is required")
    host = host.strip().lower().removesuffix(".")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if "%" in host:
        raise ValueError("Scoped IP addresses are not supported")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    host = host.encode("idna").decode("ascii")
    if len(host) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in host.split(".")
    ):
        raise ValueError("Outbound host is invalid")
    return host


def validate_feishu_webhook(webhook: str) -> tuple[str, str]:
    if not isinstance(webhook, str) or any(ord(char) <= 32 for char in webhook):
        raise ValueError("Feishu webhook is invalid")
    url = urlsplit(webhook)
    if (
        url.scheme != "https"
        or url.hostname not in {"open.feishu.cn", "open.larksuite.com"}
        or url.username is not None
        or url.password is not None
        or url.netloc.lower() not in {url.hostname, f"{url.hostname}:443"}
        or "?" in webhook
        or "#" in webhook
        or not re.fullmatch(r"/open-apis/bot/v2/hook/[A-Za-z0-9_-]+", url.path)
    ):
        raise ValueError("Only official HTTPS Feishu/Lark bot webhooks are allowed")
    return url.hostname, url.path


def resolve_addresses(host: str, port: int, *, allow_private: bool = False) -> list[tuple]:
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Outbound port is invalid")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Outbound host did not resolve")
    for family, _, _, _, address in addresses:
        if family not in (socket.AF_INET, socket.AF_INET6):
            raise ValueError("Unsupported outbound address family")
        ip = ipaddress.ip_address(address[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        nonpublic = (
            not ip.is_global or ip.is_reserved or getattr(ip, "is_site_local", False)
        )
        if ip.is_unspecified or ip.is_multicast or (not allow_private and nonpublic):
            raise ValueError("Outbound host resolves to a prohibited address")
    return addresses


def resolve_smtp_target(host: str, port: int, security=None) -> tuple[str, list[tuple]]:
    host = normalize_host(host)
    allowed = {normalize_host(item) for item in getattr(security, "smtp_allowed_hosts", ())}
    private = {
        normalize_host(item) for item in getattr(security, "smtp_allow_private_hosts", ())
    }
    if allowed and host not in allowed:
        raise ValueError("SMTP host is not in the configured allowlist")
    return host, resolve_addresses(host, port, allow_private=host in private)


def connect_addresses(addresses: list[tuple], timeout: float, source_address=None):
    """Connect using the checked sockaddr values without resolving the host again."""
    last_error = None
    for family, socktype, protocol, _, address in addresses:
        sock = socket.socket(family, socktype, protocol)
        try:
            sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(address)
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    if last_error is not None:
        raise last_error
    raise ValueError("No outbound addresses are available")
