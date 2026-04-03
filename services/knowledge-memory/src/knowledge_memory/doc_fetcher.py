"""HTTP documentation retrieval and text extraction.

Fetches remote documents and converts HTML content to plain text
using BeautifulSoup for downstream knowledge ingestion.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from architect_common.logging import get_logger

logger = get_logger(component="knowledge_memory.doc_fetcher")

_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript"}
_ALLOWED_SCHEMES = {"http", "https"}

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
]


def validate_url(url: str) -> None:
    """Validate a URL to prevent Server-Side Request Forgery (SSRF).

    Checks the URL scheme and resolves the hostname to ensure it does not
    point to a private or internal IP address.

    Raises:
        ValueError: If the URL fails validation.
    """
    parsed = urlparse(url)

    if not parsed.scheme:
        raise ValueError(f"URL has no scheme: {url}")

    if parsed.scheme.lower() in _BLOCKED_SCHEMES:
        raise ValueError(f"Blocked URL scheme: {parsed.scheme}")

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"URL scheme '{parsed.scheme}' is not allowed; only http and https are permitted"
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")

    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}") from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                logger.warning(
                    "ssrf_blocked",
                    url=url,
                    resolved_ip=str(ip),
                    blocked_network=str(network),
                )
                raise ValueError(f"URL resolves to blocked internal address {ip} (in {network})")


async def fetch_documentation(
    url: str,
    *,
    max_size_kb: int = 500,
    timeout_seconds: int = 30,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Fetch a document from a URL and return its text content.

    HTML pages are converted to plain text using BeautifulSoup.
    Non-HTML responses are returned as-is (truncated to *max_size_kb*).

    Args:
        url: The URL to fetch.
        max_size_kb: Maximum response size in kilobytes.
        timeout_seconds: HTTP request timeout.
        client: Optional pre-existing httpx client to reuse. When ``None``,
            a temporary client is created for this request.

    Returns:
        Extracted text content from the document.

    Raises:
        httpx.HTTPStatusError: On non-2xx HTTP responses.
        httpx.TimeoutException: On request timeout.
    """
    validate_url(url)
    max_bytes = max_size_kb * 1024

    def _validate_redirect(response: httpx.Response) -> None:
        """Validate redirect targets to prevent SSRF bypass via redirect chains."""
        if response.is_redirect:
            redirect_url = response.headers.get("location")
            if redirect_url:
                validate_url(redirect_url)

    async def _do_fetch(c: httpx.AsyncClient) -> str:
        c.event_hooks["response"] = [_validate_redirect]
        response = await c.get(url)
        response.raise_for_status()
        raw_bytes = response.content[:max_bytes]
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type or "application/xhtml" in content_type:
            result = _html_to_text(raw_bytes.decode("utf-8", errors="replace"))
        else:
            result = raw_bytes.decode("utf-8", errors="replace")
        logger.info("fetched documentation", url=url, size_bytes=len(raw_bytes))
        return result

    if client is not None:
        return await _do_fetch(client)

    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        max_redirects=5,
    ) as new_client:
        return await _do_fetch(new_client)


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text, stripping scripts and styles."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Extract text
    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive blank lines
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)
