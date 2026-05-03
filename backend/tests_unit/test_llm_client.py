"""Tests for backend/llm_client.py — the shared Ollama client.

Uses asyncio.run() rather than pytest-asyncio so these tests work in the
default test environment.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from llm_client import ask_ollama, chat_ollama


def _mock_httpx(response_json=None, raise_connect_error=False, raise_other=False):
    """Build a context-managed mock of httpx.AsyncClient."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_json or {}
    mock_resp.raise_for_status = MagicMock()

    mock_instance = AsyncMock()
    if raise_connect_error:
        mock_instance.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    elif raise_other:
        mock_instance.post = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        mock_instance.post = AsyncMock(return_value=mock_resp)
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    return mock_instance


def test_ask_ollama_returns_text_on_success():
    mock_instance = _mock_httpx(response_json={"response": "hello world"})
    with patch("httpx.AsyncClient", return_value=mock_instance):
        result = asyncio.run(ask_ollama("hi"))
    assert result["ai_available"] is True
    assert result["text"] == "hello world"
    assert result["raw"] == {"response": "hello world"}


def test_ask_ollama_degrades_on_connect_error():
    mock_instance = _mock_httpx(raise_connect_error=True)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        result = asyncio.run(ask_ollama("hi"))
    assert result["ai_available"] is False
    assert result["text"] is None


def test_ask_ollama_degrades_on_unexpected_error():
    mock_instance = _mock_httpx(raise_other=True)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        result = asyncio.run(ask_ollama("hi"))
    assert result["ai_available"] is False
    assert result["text"] is None


def test_chat_ollama_returns_message_content():
    mock_instance = _mock_httpx(
        response_json={"message": {"role": "assistant", "content": "hi back"}}
    )
    with patch("httpx.AsyncClient", return_value=mock_instance):
        result = asyncio.run(chat_ollama([{"role": "user", "content": "hi"}]))
    assert result["ai_available"] is True
    assert result["text"] == "hi back"


def test_chat_ollama_prepends_system_prompt():
    mock_instance = _mock_httpx(
        response_json={"message": {"role": "assistant", "content": "ok"}}
    )
    with patch("httpx.AsyncClient", return_value=mock_instance):
        asyncio.run(chat_ollama(
            [{"role": "user", "content": "hi"}],
            system="you are a test",
        ))
    sent_body = mock_instance.post.call_args.kwargs["json"]
    assert sent_body["messages"][0] == {"role": "system", "content": "you are a test"}
    assert sent_body["messages"][1] == {"role": "user", "content": "hi"}
    assert sent_body["stream"] is False


def test_chat_ollama_degrades_on_connect_error():
    mock_instance = _mock_httpx(raise_connect_error=True)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        result = asyncio.run(chat_ollama([{"role": "user", "content": "hi"}]))
    assert result["ai_available"] is False
    assert result["text"] is None
