"""Rolling summary of conversation turns that age out of the context window.

Only the last ``state.ADVISOR_MAX_HISTORY`` messages are sent to the LLM
per turn; without compaction, anything older is simply gone. This module
keeps a rolling summary on the conversation dict (``summary`` +
``summary_upto``) so long chats retain continuity. Runs as a FastAPI
BackgroundTasks job after each reply; failures degrade silently — the
next turn just won't have an updated summary.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import state
from llm_client import ask_ollama

logger = logging.getLogger(__name__)

# Don't re-summarize on every turn — wait until this many new messages
# have aged out of the window since the last compaction.
COMPACT_BATCH_SIZE = 6

SUMMARY_SYSTEM_PROMPT = """You maintain a running summary of a conversation
between a user and Fin, their financial-advisor assistant. You get the
existing summary (may be empty) plus the messages that just aged out of the
context window. Produce an UPDATED summary that replaces the old one.

Rules:
- At most 12 short bullet points, most important first.
- Keep: concrete numbers discussed, decisions made, advice given, personal
  context revealed, open questions Fin promised to follow up on.
- Drop: greetings, filler, anything superseded by later messages.
- No preamble, no headings — just the bullets, one per line, starting "- ".
"""


def render_summary_block(conv: Dict[str, Any]) -> str:
    summary = (conv.get("summary") or "").strip()
    if not summary:
        return ""
    return (
        "EARLIER IN THIS CONVERSATION (rolling summary of messages no longer "
        "in your context — treat as accurate history):\n" + summary
    )


def _build_prompt(existing_summary: str, aged: List[Dict[str, Any]]) -> str:
    parts: List[str] = ["=== Existing summary ==="]
    parts.append(existing_summary.strip() or "(none yet)")
    parts.append("")
    parts.append("=== Messages that just left the context window ===")
    for m in aged:
        parts.append(f"{m.get('role', '?')}: {(m.get('content') or '').strip()}")
    parts.append("")
    parts.append("Write the updated summary now.")
    return "\n".join(parts)


async def maybe_compact(conv_id: str) -> bool:
    """Update the rolling summary when enough messages have aged out.

    Returns True when a new summary was written. Idempotent and cheap to
    schedule — short-circuits when the window hasn't shifted enough.
    """
    if conv_id not in state.conversations:
        return False
    conv = state.conversations[conv_id]
    messages = conv.get("messages") or []

    aged_count = len(messages) - state.ADVISOR_MAX_HISTORY
    if aged_count <= 0:
        return False
    covered = int(conv.get("summary_upto") or 0)
    if aged_count - covered < COMPACT_BATCH_SIZE:
        return False

    aged = messages[covered:aged_count]
    result = await ask_ollama(
        prompt=_build_prompt(conv.get("summary") or "", aged),
        system=SUMMARY_SYSTEM_PROMPT,
    )
    if not result.get("ai_available"):
        logger.info("[compaction] Ollama unavailable — skipping")
        return False
    summary = (result.get("text") or "").strip()
    if not summary:
        return False

    conv["summary"] = summary
    conv["summary_upto"] = aged_count
    # PgStore items are snapshots — write back to persist.
    state.conversations[conv_id] = conv
    logger.info(
        f"[compaction] conv={conv_id} summarized {len(aged)} aged messages "
        f"(covered {aged_count}/{len(messages)})"
    )
    return True
