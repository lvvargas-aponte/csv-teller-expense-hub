"""Proactively extract durable personal facts from recent conversation.

Mirrors ``style_reflection``: runs as a FastAPI BackgroundTasks job every
``FACT_REFLECTION_TURN_INTERVAL`` user turns, reads recent user messages,
asks Ollama (JSON mode) for durable personal facts, dedups against
existing facts of ANY status (so rejected facts are never re-proposed),
and inserts survivors as ``status='proposed'`` for the user to confirm
in the memory panel. All-local via ``llm_client.ask_ollama``; failures
degrade silently.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from db import fact_reflection_repo, style_profile_repo, user_facts_repo
from db.base import sync_engine
from embeddings import embed_pending_user_facts, retrieve_similar_facts
from llm_client import ask_ollama

logger = logging.getLogger(__name__)


FACT_REFLECTION_TURN_INTERVAL = 8
RECENT_USER_MSG_LIMIT = 20
DUPLICATE_DISTANCE = 0.25

VALID_CATEGORIES = set(user_facts_repo.VALID_CATEGORIES)


EXTRACTION_SYSTEM_PROMPT = """You extract durable personal facts about a user
from their messages to a financial-advisor assistant.

A durable fact is something worth remembering months from now: a life event
("expecting a baby in March"), a goal ("wants to reach FI by 45"), a
constraint ("refuses to touch the 401k"), a preference ("prefers index funds
over single stocks"), or a behavioral pattern ("panic-checks the market when
it dips").

Do NOT extract: transient context ("busy this week"), financial data the app
already tracks (balances, transactions, budgets), questions, or anything the
user merely asked about without revealing something personal.

Output STRICT JSON, nothing else:
{"facts": [{"fact": "<one short sentence>",
            "category": "preference|constraint|goal|life_event|pattern",
            "tags": ["<up to 3 short tags>"],
            "sensitive": true|false,
            "source_index": <number of the message the fact came from>}]}

Return {"facts": []} when nothing qualifies — that is the common case.
Mark sensitive=true for medical, relationship, or income details.
"""


def _fetch_recent_user_turns(limit: int) -> List[Tuple[int, str]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, content FROM conversation_turns "
                "WHERE role = 'user' "
                "ORDER BY ts DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()
    return [(int(r[0]), r[1]) for r in rows if r[1]]


def _build_extraction_prompt(turns: List[Tuple[int, str]]) -> str:
    parts = ["=== Recent user messages (newest first) ==="]
    for i, (_turn_id, content) in enumerate(turns, 1):
        parts.append(f"{i}. {content.strip()}")
    parts.append("")
    parts.append("Extract the durable personal facts now as JSON.")
    return "\n".join(parts)


def _parse_candidates(raw_text: str) -> List[Dict[str, Any]]:
    """Defensive parse — tolerate a bare list or garbage without raising."""
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        logger.info("[fact_reflection] Ollama returned non-JSON — skipping")
        return []
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        candidates = data.get("facts") or []
    else:
        return []
    out: List[Dict[str, Any]] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        fact = (c.get("fact") or "").strip()
        category = c.get("category")
        if not fact or category not in VALID_CATEGORIES:
            continue
        out.append(c)
    return out


async def _is_duplicate(fact: str) -> bool:
    hits = await retrieve_similar_facts(
        query=fact, status=None, k=1, threshold=DUPLICATE_DISTANCE,
    )
    return bool(hits)


async def extract_user_facts() -> int:
    """Scan recent user turns and propose new personal facts.

    Returns the number of facts inserted. Advances the watermark even
    when nothing is found so the same window isn't rescanned every turn.
    """
    turns = _fetch_recent_user_turns(RECENT_USER_MSG_LIMIT)
    if not turns:
        return 0

    result = await ask_ollama(
        prompt=_build_extraction_prompt(turns),
        system=EXTRACTION_SYSTEM_PROMPT,
        format="json",
    )
    if not result.get("ai_available"):
        logger.info("[fact_reflection] Ollama unavailable — skipping")
        return 0

    candidates = _parse_candidates(result.get("text") or "")
    created = 0
    for c in candidates:
        fact = c["fact"].strip()
        if await _is_duplicate(fact):
            continue
        source_turn_id: Optional[int] = None
        idx = c.get("source_index")
        if isinstance(idx, int) and 1 <= idx <= len(turns):
            source_turn_id = turns[idx - 1][0]
        user_facts_repo.create_fact(
            fact=fact,
            category=c["category"],
            tags=[str(t) for t in (c.get("tags") or [])][:3],
            sensitive=bool(c.get("sensitive")),
            status="proposed",
            confidence=0.5,
            source_turn_id=source_turn_id,
        )
        created += 1

    if created:
        await embed_pending_user_facts()

    turn_count = style_profile_repo.total_user_turn_count()
    fact_reflection_repo.set_turn_count_at_last_scan(turn_count)
    logger.info(
        f"[fact_reflection] scanned {len(turns)} turns, "
        f"{len(candidates)} candidates, {created} proposed"
    )
    return created


def should_extract_facts() -> bool:
    """True when we've crossed the next FACT_REFLECTION_TURN_INTERVAL
    boundary since the last scan."""
    current = style_profile_repo.total_user_turn_count()
    if current == 0:
        return False
    last = fact_reflection_repo.get_turn_count_at_last_scan()
    return (current - last) >= FACT_REFLECTION_TURN_INTERVAL
