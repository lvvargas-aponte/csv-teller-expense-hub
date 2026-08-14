"""Unit tests for the Fin web tools — ddgs and url_fetcher are mocked,
no network, no DB."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.schemas import FetchWebpageArgs, WebSearchArgs
from agent.web_tools import (
    _PAGE_TEXT_MAX_CHARS,
    _fetch_webpage,
    _web_search,
    build_web_tools,
)


def _run(coro):
    return asyncio.run(coro)


def _install_fake_ddgs(results):
    fake_instance = MagicMock()
    fake_instance.text.return_value = results
    fake_instance.__enter__ = MagicMock(return_value=fake_instance)
    fake_instance.__exit__ = MagicMock(return_value=False)
    fake_module = ModuleType("ddgs")
    fake_module.DDGS = MagicMock(return_value=fake_instance)
    return patch.dict(sys.modules, {"ddgs": fake_module}), fake_instance


class TestWebSearch:
    def test_returns_shape(self):
        patcher, inst = _install_fake_ddgs([
            {"title": "NVDA earnings", "href": "https://ex.com/a", "body": "beat estimates"},
            {"title": "NVDA outlook", "href": "https://ex.com/b", "body": "analysts split"},
        ])
        with patcher:
            out = _run(_web_search(WebSearchArgs(query="NVDA earnings")))
        assert out["query"] == "NVDA earnings"
        assert out["count"] == 2
        assert out["results"][0] == {
            "title": "NVDA earnings", "url": "https://ex.com/a", "snippet": "beat estimates",
        }

    def test_max_results_capped_by_config(self):
        patcher, inst = _install_fake_ddgs([])
        with patcher, patch("agent.web_tools.config") as cfg:
            cfg.WEB_SEARCH_MAX_RESULTS = 3
            _run(_web_search(WebSearchArgs(query="x", max_results=10)))
        inst.text.assert_called_once_with("x", max_results=3)


class TestFetchWebpage:
    def _fetch_patch(self, body=b"<html><body><main><p>hello world</p></main></body></html>"):
        return patch(
            "agent.web_tools.url_fetcher.fetch",
            return_value=(body, "text/html", "https://ex.com/final"),
        )

    def test_returns_extracted_text(self):
        with self._fetch_patch() as fetch_mock:
            out = _run(_fetch_webpage(FetchWebpageArgs(url="https://ex.com/a")))
        assert out["url"] == "https://ex.com/final"
        assert "hello world" in out["content"]
        assert out["truncated"] is False

    def test_passes_allowlist_off_and_config_limits(self):
        with self._fetch_patch() as fetch_mock, patch("agent.web_tools.config") as cfg:
            cfg.ADVISOR_FETCH_MAX_BYTES = 1234
            cfg.ADVISOR_FETCH_TIMEOUT_SEC = 9.0
            _run(_fetch_webpage(FetchWebpageArgs(url="https://ex.com/a")))
        kwargs = fetch_mock.call_args.kwargs
        assert kwargs["enforce_allowlist"] is False
        assert kwargs["max_bytes"] == 1234
        assert kwargs["total_timeout"] == 9.0

    def test_truncates_long_pages(self):
        long_para = "word " * 5000
        body = f"<html><body><main><p>{long_para}</p></main></body></html>".encode()
        with self._fetch_patch(body=body):
            out = _run(_fetch_webpage(FetchWebpageArgs(url="https://ex.com/a")))
        assert out["truncated"] is True
        assert len(out["content"]) == _PAGE_TEXT_MAX_CHARS


class TestBuildWebTools:
    def test_two_tools_with_raised_result_cap(self):
        tools = build_web_tools()
        assert [t.name for t in tools] == ["web_search", "fetch_webpage"]
        assert all(t.result_max_chars == 8000 for t in tools)
