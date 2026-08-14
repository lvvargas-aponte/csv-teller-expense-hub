"""URL-import path — SSRF guards + from-url endpoint round-trip.

Every fetch is mocked — no real network calls.  Each test pins one
specific failure mode (off-allowlist host, http://, private DNS answer,
redirect to disallowed host, oversize body) so a regression in any
single guard breaks one test rather than silently weakening the whole
defense.
"""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import url_fetcher


_FAKE_VEC = [0.1] * 768


def _mock_embed(available=True):
    return patch(
        "embeddings.embed_ollama",
        new=AsyncMock(return_value={
            "ai_available": available,
            "embedding": _FAKE_VEC if available else None,
            "raw": None,
        }),
    )


def _patch_resolves_public_ok():
    """Skip the DNS+private-IP guard for tests that don't exercise it."""
    return patch.object(url_fetcher, "_check_resolves_public", lambda host: None)


# ---------------------------------------------------------------------------
# url_fetcher unit tests — exercise each guard in isolation.
# ---------------------------------------------------------------------------


class TestSchemeAllowlist:
    def test_rejects_http(self):
        with pytest.raises(url_fetcher.FetchError, match="https"):
            url_fetcher.fetch("http://www.irs.gov/pub/irs-pdf/p17.pdf")

    def test_rejects_file_scheme(self):
        with pytest.raises(url_fetcher.FetchError, match="https"):
            url_fetcher.fetch("file:///etc/passwd")

    def test_rejects_ftp(self):
        with pytest.raises(url_fetcher.FetchError, match="https"):
            url_fetcher.fetch("ftp://www.irs.gov/file.pdf")


class TestHostAllowlist:
    def test_rejects_unknown_host(self):
        with pytest.raises(url_fetcher.FetchError, match="allowlist"):
            url_fetcher.fetch("https://evil.example.com/x.pdf")

    def test_accepts_allowlisted_host(self):
        # Bypass DNS + actual network; confirm the host check passes.
        with _patch_resolves_public_ok(), patch("httpx.Client") as mock_client:
            mock_resp = httpx.Response(
                200,
                content=b"%PDF-1.4 fake",
                headers={"Content-Type": "application/pdf"},
            )
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp
            mock_resp.iter_bytes = lambda: iter([b"%PDF-1.4 fake"])

            body, ct, final = url_fetcher.fetch("https://www.irs.gov/pub/irs-pdf/p17.pdf")
            assert body == b"%PDF-1.4 fake"
            assert ct == "application/pdf"
            assert final == "https://www.irs.gov/pub/irs-pdf/p17.pdf"


class TestPrivateIpGuard:
    def test_rejects_loopback_resolution(self):
        # Pretend the allowlisted host resolves to 127.0.0.1 (DNS rebinding
        # / hosts-file trick).  The guard must refuse before the HTTP call.
        fake_addrinfo = [(2, 1, 6, "", ("127.0.0.1", 0))]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            # Inject the host into the allowlist so we hit the IP guard,
            # not the host guard.
            with patch.object(url_fetcher, "ALLOWED_HOSTS", {"rebound.example.com"}):
                with pytest.raises(url_fetcher.FetchError, match="loopback|private|reserved"):
                    url_fetcher.fetch("https://rebound.example.com/x")

    def test_rejects_private_range(self):
        fake_addrinfo = [(2, 1, 6, "", ("10.0.0.5", 0))]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with patch.object(url_fetcher, "ALLOWED_HOSTS", {"rebound.example.com"}):
                with pytest.raises(url_fetcher.FetchError, match="loopback|private|reserved"):
                    url_fetcher.fetch("https://rebound.example.com/x")

    def test_rejects_link_local(self):
        # 169.254.169.254 — cloud metadata endpoint.
        fake_addrinfo = [(2, 1, 6, "", ("169.254.169.254", 0))]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with patch.object(url_fetcher, "ALLOWED_HOSTS", {"rebound.example.com"}):
                with pytest.raises(url_fetcher.FetchError, match="loopback|private|reserved|link"):
                    url_fetcher.fetch("https://rebound.example.com/x")


class TestRedirectHandling:
    def test_redirect_to_disallowed_host_rejected(self):
        # Allowlisted host returns a 302 to evil.example.com — the second
        # hop must be re-validated and rejected.
        with _patch_resolves_public_ok(), patch("httpx.Client") as mock_client:
            redirect_resp = httpx.Response(
                302, headers={"Location": "https://evil.example.com/x.pdf"}
            )
            redirect_resp.iter_bytes = lambda: iter([])
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = redirect_resp

            with pytest.raises(url_fetcher.FetchError, match="allowlist"):
                url_fetcher.fetch("https://www.irs.gov/redirect")


class TestAllowlistOff:
    """``enforce_allowlist=False`` (advisor web tools) must skip ONLY the
    host allowlist — every other guard stays active."""

    def test_fetches_non_allowlisted_https_host(self):
        with _patch_resolves_public_ok(), patch("httpx.Client") as mock_client:
            mock_resp = httpx.Response(
                200,
                content=b"<html>hi</html>",
                headers={"Content-Type": "text/html"},
            )
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp
            mock_resp.iter_bytes = lambda: iter([b"<html>hi</html>"])

            body, ct, final = url_fetcher.fetch(
                "https://finance.example.com/article", enforce_allowlist=False
            )
            assert body == b"<html>hi</html>"
            assert ct == "text/html"

    def test_still_rejects_http(self):
        with pytest.raises(url_fetcher.FetchError, match="https"):
            url_fetcher.fetch("http://finance.example.com/x", enforce_allowlist=False)

    def test_still_rejects_private_resolution(self):
        fake_addrinfo = [(2, 1, 6, "", ("127.0.0.1", 0))]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with pytest.raises(url_fetcher.FetchError, match="loopback|private|reserved"):
                url_fetcher.fetch("https://rebound.example.com/x", enforce_allowlist=False)

    def test_redirect_to_private_host_rejected(self):
        # First hop is public, redirect target resolves private.
        def fake_resolve(host):
            if host == "rebound.example.com":
                raise url_fetcher.FetchError(
                    f"Refusing to fetch {host}: resolves to 127.0.0.1 "
                    f"(private/loopback/reserved address)"
                )

        with patch.object(url_fetcher, "_check_resolves_public", fake_resolve), patch(
            "httpx.Client"
        ) as mock_client:
            redirect_resp = httpx.Response(
                302, headers={"Location": "https://rebound.example.com/x"}
            )
            redirect_resp.iter_bytes = lambda: iter([])
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = redirect_resp

            with pytest.raises(url_fetcher.FetchError, match="loopback|private|reserved"):
                url_fetcher.fetch("https://public.example.com/redirect", enforce_allowlist=False)

    def test_max_bytes_cap_enforced_mid_stream(self):
        with _patch_resolves_public_ok(), patch("httpx.Client") as mock_client:
            mock_resp = httpx.Response(200, headers={"Content-Type": "text/html"})
            mock_resp.iter_bytes = lambda: iter([b"x" * 1024] * 10)
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp

            with pytest.raises(url_fetcher.FetchError, match="cap mid-stream"):
                url_fetcher.fetch(
                    "https://finance.example.com/big",
                    enforce_allowlist=False,
                    max_bytes=2048,
                )

    def test_oversize_content_length_rejected(self):
        with _patch_resolves_public_ok(), patch("httpx.Client") as mock_client:
            mock_resp = httpx.Response(
                200,
                headers={"Content-Type": "text/html", "Content-Length": "999999"},
            )
            mock_resp.iter_bytes = lambda: iter([])
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp

            with pytest.raises(url_fetcher.FetchError, match="too large"):
                url_fetcher.fetch(
                    "https://finance.example.com/big",
                    enforce_allowlist=False,
                    max_bytes=2048,
                )


# ---------------------------------------------------------------------------
# Endpoint integration — TestClient round-trip.  The fetch itself is
# patched so we don't hit the network.
# ---------------------------------------------------------------------------


_SAMPLE_HTML = (
    b"<html><head><title>Three-fund portfolio</title></head>"
    b"<body><nav>Skip me</nav>"
    b"<main><p>The three-fund portfolio is a passive allocation across "
    b"US stocks, international stocks, and bonds.  Recommended for "
    b"long-horizon investors who want a low-maintenance approach.</p>"
    b"</main><footer>Skip me too</footer></body></html>"
)


class TestImportEndpoint:
    def test_imports_html_through_allowlist(self, client):
        with _mock_embed(), patch(
            "routers.documents.fetch_url",
            return_value=(_SAMPLE_HTML, "text/html", "https://www.bogleheads.org/wiki/Three-fund_portfolio"),
        ):
            resp = client.post("/api/documents/from-url", json={
                "url": "https://www.bogleheads.org/wiki/Three-fund_portfolio",
                "scope": "external",
                "category": "investing",
            })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] is not None
        assert body["status"] == "pending"

    def test_off_allowlist_returns_422(self, client):
        # Don't patch fetch_url — let the real fetcher reject the host.
        resp = client.post("/api/documents/from-url", json={
            "url": "https://evil.example.com/x.pdf",
            "scope": "external",
            "category": "tax",
        })
        assert resp.status_code == 422
        assert "allowlist" in resp.json()["detail"]

    def test_invalid_scope_returns_422(self, client):
        resp = client.post("/api/documents/from-url", json={
            "url": "https://www.irs.gov/pub/irs-pdf/p17.pdf",
            "scope": "bogus",
            "category": "tax",
        })
        assert resp.status_code == 422

    def test_allowed_hosts_endpoint(self, client):
        resp = client.get("/api/documents/allowed-hosts")
        assert resp.status_code == 200
        hosts = resp.json()
        assert "www.irs.gov" in hosts
        assert "www.bogleheads.org" in hosts


class TestReimportVersioning:
    """When the same source URL is re-imported, the backend must:

    * return ``duplicate=True`` if the bytes haven't changed;
    * insert a new versioned row AND mark the prior row ``superseded``
      if the bytes have changed, returning ``replaces_id`` so the UI can
      tell the user the corpus shifted.
    """

    _URL = "https://www.bogleheads.org/wiki/Three-fund_portfolio"
    _ORIGINAL = (
        b"<html><head><title>Three-fund</title></head><body><main>"
        b"<p>Original body about three-fund portfolios that is long "
        b"enough to clear the low-yield warning threshold.  "
        b"More content to ensure the chunker has something to work with.</p>"
        b"</main></body></html>"
    )
    _UPDATED = (
        b"<html><head><title>Three-fund (updated)</title></head><body><main>"
        b"<p>Updated body with new guidance on bond allocation.  This is "
        b"intentionally different content so the content_hash diverges "
        b"from the original import.  Padding for chunker yield.</p>"
        b"</main></body></html>"
    )

    def test_unchanged_reimport_returns_duplicate(self, client):
        with _mock_embed(), patch(
            "routers.documents.fetch_url",
            return_value=(self._ORIGINAL, "text/html", self._URL),
        ):
            first = client.post("/api/documents/from-url", json={
                "url": self._URL, "scope": "external", "category": "investing",
            })
            assert first.status_code == 200
            assert first.json()["id"] is not None

            second = client.post("/api/documents/from-url", json={
                "url": self._URL, "scope": "external", "category": "investing",
            })
        assert second.status_code == 200
        body = second.json()
        assert body["duplicate"] is True
        assert body["id"] is None
        assert body["replaces_id"] is None

    def test_changed_reimport_creates_new_version(self, client):
        with _mock_embed(), patch(
            "routers.documents.fetch_url",
            return_value=(self._ORIGINAL, "text/html", self._URL),
        ):
            first = client.post("/api/documents/from-url", json={
                "url": self._URL, "scope": "external", "category": "investing",
            })
        first_id = first.json()["id"]
        assert first_id is not None

        with _mock_embed(), patch(
            "routers.documents.fetch_url",
            return_value=(self._UPDATED, "text/html", self._URL),
        ):
            second = client.post("/api/documents/from-url", json={
                "url": self._URL, "scope": "external", "category": "investing",
            })
        assert second.status_code == 200
        body = second.json()
        assert body["id"] is not None
        assert body["id"] != first_id
        assert body["replaces_id"] == first_id

        # The old version must be marked superseded so the UI can hide it
        # from the active set; it stays retrievable for older citations.
        from db import documents_repo
        old = documents_repo.get_document(first_id)
        new = documents_repo.get_document(body["id"])
        assert old["status"] == "superseded"
        assert old["metadata"].get("replaced_by_id") == body["id"]
        assert new["metadata"].get("previous_version_id") == first_id


class TestHtmlExtractor:
    def test_strips_boilerplate_keeps_main(self):
        from document_extractor import extract_html

        text, meta = extract_html(_SAMPLE_HTML)
        assert "three-fund" in text.lower()
        assert "Skip me" not in text
        assert meta.get("html_title") == "Three-fund portfolio"

    def test_low_yield_warning(self):
        text, meta = __import__("document_extractor").extract_html(b"<html></html>")
        assert meta.get("warning") == "low_text_yield"


class TestContentTypeDispatch:
    def test_pdf_routed_by_content_type(self):
        from document_extractor import extract_by_content_type
        # Minimal PDF magic — pypdf will fail to parse but the dispatcher
        # should at least pick the PDF branch.  We catch the eventual
        # ExtractionError to confirm routing.
        from document_extractor import ExtractionError
        with pytest.raises(ExtractionError):
            extract_by_content_type(b"%PDF-1.4 not really a pdf", "application/pdf")

    def test_html_routed_by_magic_bytes_when_ct_generic(self):
        from document_extractor import extract_by_content_type
        text, meta = extract_by_content_type(
            _SAMPLE_HTML, "application/octet-stream"
        )
        assert "three-fund" in text.lower()
