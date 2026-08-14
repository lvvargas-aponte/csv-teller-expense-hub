"""Web tools for the Fin agent — DuckDuckGo search + guarded page fetch.

``fetch_webpage`` reuses ``url_fetcher.fetch`` with the host allowlist
off; the scheme, DNS/private-IP, and redirect guards still apply. Page
bytes route through ``document_extractor`` so HTML and PDF both come
back as readable text.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import config
import url_fetcher
from document_extractor import extract_by_content_type

from agent.schemas import FetchWebpageArgs, WebSearchArgs
from agent.tools import TransientToolError

_PAGE_TEXT_MAX_CHARS = 8000


def _ddgs_search(query: str, max_results: int) -> List[Dict[str, str]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in ddgs.text(query, max_results=max_results)
        ]


async def _web_search(args: WebSearchArgs) -> Dict[str, Any]:
    limit = min(args.max_results, config.WEB_SEARCH_MAX_RESULTS)
    try:
        results = await asyncio.to_thread(_ddgs_search, args.query, limit)
    except Exception as e:
        # DuckDuckGo scraping rate-limits and captchas intermittently —
        # worth one retry rather than giving up on the answer.
        raise TransientToolError(f"web search failed: {e}") from e
    return {"query": args.query, "count": len(results), "results": results}


async def _fetch_webpage(args: FetchWebpageArgs) -> Dict[str, Any]:
    try:
        body, content_type, final_url = await asyncio.to_thread(
            lambda: url_fetcher.fetch(
                args.url,
                enforce_allowlist=False,
                max_bytes=config.ADVISOR_FETCH_MAX_BYTES,
                total_timeout=config.ADVISOR_FETCH_TIMEOUT_SEC,
            )
        )
    except url_fetcher.FetchError as e:
        if "Network error" in str(e):
            raise TransientToolError(str(e)) from e
        raise
    text, meta = extract_by_content_type(body, content_type, hint_url=final_url)
    truncated = len(text) > _PAGE_TEXT_MAX_CHARS
    return {
        "url": final_url,
        "title": meta.get("html_title") or meta.get("pdf_title") or "",
        "content": text[:_PAGE_TEXT_MAX_CHARS],
        "truncated": truncated,
    }


def build_web_tools() -> list:
    from agent.tools import Tool

    return [
        Tool(
            name="web_search",
            description=(
                "Search the public web (DuckDuckGo). Use for anything that "
                "needs current outside information: market news ('what's "
                "going on with NVDA'), rate benchmarks (savings/mortgage/CD "
                "rates), picking candidate tickers or funds, recent tax-law "
                "changes. Returns titles, URLs, and snippets — follow up "
                "with fetch_webpage on the most promising result when the "
                "snippet isn't enough."
            ),
            args_model=WebSearchArgs,
            handler=_web_search,
            result_max_chars=8000,
        ),
        Tool(
            name="fetch_webpage",
            description=(
                "Fetch and read one https:// page, usually a web_search "
                "result. Returns the page's main text. Mention the source "
                "(title or domain) when you use numbers or claims from it."
            ),
            args_model=FetchWebpageArgs,
            handler=_fetch_webpage,
            result_max_chars=8000,
        ),
    ]
