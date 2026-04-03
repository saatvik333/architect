"""Tests for the doc_fetcher module (including SSRF validation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from knowledge_memory.doc_fetcher import fetch_documentation, validate_url


class TestValidateUrl:
    """Tests for SSRF URL validation."""

    def test_rejects_file_scheme(self) -> None:
        """validate_url rejects file:// scheme."""
        with pytest.raises(ValueError, match="Blocked URL scheme"):
            validate_url("file:///etc/passwd")

    def test_rejects_ftp_scheme(self) -> None:
        """validate_url rejects ftp:// scheme."""
        with pytest.raises(ValueError, match="Blocked URL scheme"):
            validate_url("ftp://evil.com/data")

    def test_allows_https(self) -> None:
        """validate_url allows https://example.com (with DNS mocking)."""
        with patch(
            "knowledge_memory.doc_fetcher.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 443)),
            ],
        ):
            validate_url("https://example.com")  # Should not raise

    def test_blocks_loopback(self) -> None:
        """validate_url blocks http://127.0.0.1."""
        with (
            patch(
                "knowledge_memory.doc_fetcher.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("127.0.0.1", 80))],
            ),
            pytest.raises(ValueError, match="blocked internal address"),
        ):
            validate_url("http://127.0.0.1")

    def test_blocks_metadata_endpoint(self) -> None:
        """validate_url blocks http://169.254.169.254 (cloud metadata)."""
        with (
            patch(
                "knowledge_memory.doc_fetcher.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("169.254.169.254", 80))],
            ),
            pytest.raises(ValueError, match="blocked internal address"),
        ):
            validate_url("http://169.254.169.254")

    def test_blocks_private_10_network(self) -> None:
        """validate_url blocks http://10.0.0.1 (private network)."""
        with (
            patch(
                "knowledge_memory.doc_fetcher.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("10.0.0.1", 80))],
            ),
            pytest.raises(ValueError, match="blocked internal address"),
        ):
            validate_url("http://10.0.0.1")

    def test_rejects_no_scheme(self) -> None:
        """validate_url rejects URLs without a scheme."""
        with pytest.raises(ValueError, match="no scheme"):
            validate_url("example.com/page")

    def test_rejects_no_hostname(self) -> None:
        """validate_url rejects URLs without a hostname."""
        with pytest.raises(ValueError, match="no hostname"):
            validate_url("http://")


class TestFetchDocumentation:
    """Tests for fetch_documentation function."""

    async def test_fetch_valid_url_html(self) -> None:
        """fetch_documentation with a valid URL returns stripped HTML text."""
        html_content = (
            "<html><body><h1>Title</h1><p>Hello world</p><script>evil()</script></body></html>"
        )
        mock_response = httpx.Response(
            status_code=200,
            content=html_content.encode(),
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", "https://example.com/doc"),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "knowledge_memory.doc_fetcher.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        ):
            result = await fetch_documentation("https://example.com/doc", client=mock_client)

        assert "Title" in result
        assert "Hello world" in result
        # Script content should be stripped
        assert "evil()" not in result

    async def test_fetch_valid_url_plain_text(self) -> None:
        """fetch_documentation returns text content for non-HTML responses."""
        mock_response = httpx.Response(
            status_code=200,
            content=b"Plain text content here",
            headers={"content-type": "text/plain"},
            request=httpx.Request("GET", "https://example.com/readme.txt"),
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "knowledge_memory.doc_fetcher.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        ):
            result = await fetch_documentation("https://example.com/readme.txt", client=mock_client)

        assert result == "Plain text content here"

    async def test_fetch_blocked_url_raises(self) -> None:
        """fetch_documentation raises ValueError for blocked URLs."""
        with pytest.raises(ValueError, match="Blocked URL scheme"):
            await fetch_documentation("file:///etc/passwd")
