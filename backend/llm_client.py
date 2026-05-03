"""Shared Ollama LLM client.

Centralizes the httpx + retry/error handling pattern used by all routers that
call the local Ollama server.  Callers receive a uniform response:

    {"ai_available": bool, "text": Optional[str], "raw": Optional[dict]}

`ai_available=False` means the server was unreachable or returned an error —
callers should degrade gracefully (show raw data without AI commentary).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

import state

logger = logging.getLogger(__name__)


async def ask_ollama(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    format: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Single-turn generation via Ollama's /api/generate endpoint.

    Args:
        prompt: The user-facing prompt text.
        system: Optional system prompt prepended to the conversation.
        model: Override the default model (falls back to state.OLLAMA_MODEL).
        format: Optional Ollama response format hint (e.g. "json").
        timeout: Override the default HTTP timeout.

    Returns:
        {"ai_available": bool, "text": str | None, "raw": dict | None}
    """
    body: Dict[str, Any] = {
        "model": model or state.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        body["system"] = system
    if format:
        body["format"] = format

    try:
        async with httpx.AsyncClient(timeout=timeout or state.OLLAMA_TIMEOUT_SEC) as client:
            resp = await client.post(f"{state.OLLAMA_BASE_URL}/api/generate", json=body)
            resp.raise_for_status()
            raw = resp.json()
            return {"ai_available": True, "text": raw.get("response"), "raw": raw}
    except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as e:
        logger.info(f"[llm_client] Ollama not reachable: {e}")
        return {"ai_available": False, "text": None, "raw": None}
    except Exception as e:
        logger.warning(f"[llm_client] Unexpected error calling Ollama: {e}")
        return {"ai_available": False, "text": None, "raw": None}


async def chat_ollama(
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Multi-turn chat via Ollama's /api/chat endpoint.

    `messages` is a list of {"role": "user"|"assistant", "content": str} dicts.
    If `system` is provided, it is prepended as a role=system message.
    """
    payload_messages: List[Dict[str, str]] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    body: Dict[str, Any] = {
        "model": model or state.OLLAMA_CHAT_MODEL,
        "messages": payload_messages,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout or state.OLLAMA_TIMEOUT_SEC) as client:
            resp = await client.post(f"{state.OLLAMA_BASE_URL}/api/chat", json=body)
            resp.raise_for_status()
            raw = resp.json()
            msg = raw.get("message") or {}
            return {"ai_available": True, "text": msg.get("content"), "raw": raw}
    except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as e:
        logger.info(f"[llm_client] Ollama chat not reachable: {e}")
        return {"ai_available": False, "text": None, "raw": None}
    except Exception as e:
        logger.warning(f"[llm_client] Unexpected error calling Ollama chat: {e}")
        return {"ai_available": False, "text": None, "raw": None}


async def embed_ollama(
    text: str,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate an embedding via Ollama's /api/embeddings endpoint.

    Returns ``{"ai_available": bool, "embedding": list[float] | None, "raw": dict | None}``.
    On any failure (Ollama down, model missing, timeout) ``ai_available`` is
    False and ``embedding`` is None — callers should degrade gracefully.
    """
    body: Dict[str, Any] = {
        "model": model or state.OLLAMA_EMBED_MODEL,
        "prompt": text,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout or state.OLLAMA_TIMEOUT_SEC) as client:
            resp = await client.post(f"{state.OLLAMA_BASE_URL}/api/embeddings", json=body)
            resp.raise_for_status()
            raw = resp.json()
            return {"ai_available": True, "embedding": raw.get("embedding"), "raw": raw}
    except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as e:
        logger.info(f"[llm_client] Ollama embeddings not reachable: {e}")
        return {"ai_available": False, "embedding": None, "raw": None}
    except Exception as e:
        logger.warning(f"[llm_client] Unexpected error calling Ollama embeddings: {e}")
        return {"ai_available": False, "embedding": None, "raw": None}
