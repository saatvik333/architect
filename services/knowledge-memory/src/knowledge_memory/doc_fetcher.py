"""HTTP documentation retrieval and text extraction.

Fetches remote documents and converts HTML content to plain text
using BeautifulSoup for downstream knowledge ingestion.
"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from architect_common.logging import get_logger

logger = get_logger(component="knowledge_memory.doc_fetcher")


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
    max_bytes = max_size_kb * 1024

    async def _do_fetch(c: httpx.AsyncClient) -> str:
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
