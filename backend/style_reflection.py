"""Build/refresh the advisor's style profile from real conversations.

Reads recent user messages + thumbed-up assistant replies, asks Ollama
to summarize them into a 6-bullet style guide, and upserts the result
into ``advisor_style_profile``. All-local — uses ``llm_client.ask_ollama``,
which is the only sanctioned LLM path per the architecture rules.

Runs as a FastAPI ``BackgroundTasks`` job or via a manual endpoint, so
failures (Ollama down, empty corpus) degrade silently — the next chat
turn just won't have an updated profile.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import text

from db.base import sync_engine
from db import feedback_repo, style_profile_repo
from llm_client import ask_ollama

logger = logging.getLogger(__name__)


RECENT_USER_MSG_LIMIT = 30
LIKED_REPLIES_LIMIT = 20


REFLECTION_SYSTEM_PROMPT = """You build short style guides for AI assistants.
You will be given samples of how a user talks plus replies the assistant gave
that the user marked as "good". Your job: write a concise 6-bullet style
guide describing how the assistant should talk to THIS specific user.

Rules for the guide you produce:
- Output exactly 6 bullets, each one short sentence.
- Focus on voice, tone, level of detail, humor, formality — NOT on
  financial advice.
- Describe what works, not what to avoid (positive framing).
- Be specific. "Likes concise responses" is too generic. "Reacts well when
  the answer leads with the number, then one warm sentence" is better.
- If the samples are too thin to draw real conclusions, write 3 bullets
  with light hedging instead of inventing patterns.
- No preamble. No headings. Just the bullets, one per line, starting with "- ".
"""


def _fetch_recent_user_messages(limit: int) -> List[str]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT content FROM conversation_turns "
                "WHERE role = 'user' "
                "ORDER BY ts DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()
    return [r[0] for r in rows if r[0]]


def _build_reflection_prompt(
    user_msgs: List[str], liked_replies: List[str]
) -> str:
    parts: List[str] = []
    parts.append("=== Recent user messages ===")
    if user_msgs:
        for i, m in enumerate(user_msgs, 1):
            parts.append(f"{i}. {m.strip()}")
    else:
        parts.append("(none yet)")
    parts.append("")
    parts.append("=== Assistant replies the user marked good ===")
    if liked_replies:
        for i, r in enumerate(liked_replies, 1):
            parts.append(f"{i}. {r.strip()}")
    else:
        parts.append("(none yet — base the guide on the user messages alone)")
    parts.append("")
    parts.append("Write the 6-bullet style guide now.")
    return "\n".join(parts)


async def refresh_style_profile() -> bool:
    """Regenerate the style profile from current data.

    Returns True if the profile was written, False if skipped (no data
    or Ollama unavailable). Idempotent — safe to call repeatedly.
    """
    user_msgs = _fetch_recent_user_messages(RECENT_USER_MSG_LIMIT)
    if not user_msgs:
        logger.info("[style_reflection] no user messages yet — skipping")
        return False

    liked = feedback_repo.get_positive_turn_contents(LIKED_REPLIES_LIMIT)
    prompt = _build_reflection_prompt(user_msgs, liked)
    result = await ask_ollama(prompt=prompt, system=REFLECTION_SYSTEM_PROMPT)

    if not result.get("ai_available"):
        logger.info("[style_reflection] Ollama unavailable — skipping")
        return False

    notes = (result.get("text") or "").strip()
    if not notes:
        logger.info("[style_reflection] Ollama returned empty text — skipping")
        return False

    turn_count = style_profile_repo.total_user_turn_count()
    style_profile_repo.upsert_profile(notes, turn_count)
    logger.info(
        f"[style_reflection] profile refreshed ({len(user_msgs)} user msgs, "
        f"{len(liked)} liked replies, turn_count={turn_count})"
    )
    return True


REFLECTION_TURN_INTERVAL = 10


def should_auto_refresh() -> bool:
    """True when we've crossed the next REFLECTION_TURN_INTERVAL boundary
    since the last refresh."""
    current = style_profile_repo.total_user_turn_count()
    if current == 0:
        return False
    profile = style_profile_repo.get_profile()
    last = profile["turn_count_at_last_update"] if profile else 0
    return (current - last) >= REFLECTION_TURN_INTERVAL
