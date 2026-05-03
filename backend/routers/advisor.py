"""Virtual finance advisor — multi-turn chat grounded in the household snapshot."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

import state
from analytics import build_financial_snapshot
from embeddings import (
    embed_pending_transactions,
    embed_pending_turns,
    format_rag_context,
    format_txn_rag_context,
    retrieve_similar,
    retrieve_similar_transactions,
    sync_conversation_turns,
)
from llm_client import chat_ollama
from models import (
    ChatRequest,
    ChatResponse,
    Conversation,
    ConversationSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter()


SYSTEM_PROMPT = """You are a warm, concrete household finance advisor.
The household is two people sharing expenses and consolidating shared spending in a
monthly Google Sheet.  You have structured access to their real financial data in
the `FINANCIAL_SNAPSHOT` JSON below.  Ground every answer in specific dollar amounts
and category names from that data.

Rules:
- Use concrete numbers.  Never invent figures that aren't in the snapshot.
- When the user asks "can I afford X", compare X to cash, monthly spending, and
  any open credit-card balances.  State assumptions explicitly.
- Treat `total_investments` as long-term wealth distinct from spendable
  `total_cash`.  Don't propose tapping it for everyday expenses; do reference
  it for retirement-readiness, diversification, and net-worth questions.
- When `balance_trend.available` is true, frame answers about cash, savings, or
  net worth with the direction (`label`) and the most recent delta
  (`delta_30d`).  If `available` is false, do not invent a trend.
- When `income.monthly_estimate > 0`, treat that figure as the household's
  monthly take-home and use it for affordability / debt-ratio reasoning.
  Only ask the user to confirm income when `income.confidence` is `"low"` or
  `"none"`.  Reference `income.sources[0].sample_description` when the user
  asks where the number came from.
- When asked about fairness of shared expenses, look at
  `shared_split_recent.per_person` and point out imbalances.  Cross-reference
  `recurring_inbound_transfers`: if a person owes more than they've actually
  Venmo'd / Zelled back (their entries' `total_received`), flag the gap with
  the merchant key and last-seen date.
- When `budgets` is present, compare current_month_spent to monthly_limit and
  call out categories that are over_budget or above 80% used.
- When `goals` is present, reference progress_pct and monthly_required so the
  user knows whether they're on pace.  Treat emergency_fund as the top priority.
  When a goal has `pace_status='stalled'` or `'behind'`, raise it proactively
  in any response touching saving, budgeting, or affordability — say what
  `actual_monthly_contribution` is vs `monthly_required` so the gap is
  concrete.  When `pace_status='ahead'`, acknowledge the surplus and ask
  whether it should be redirected (e.g. faster debt payoff).
- When `recurring_charges` is present, sum estimated_monthly_cost and surface
  the largest items if the user asks about subscriptions or "where is my money
  going".
- When `Related past transactions` is present, treat it as a memory of specific
  charges the user may be referring to.  Reference them by date and merchant
  when answering "what was that..." or "find me..." style questions.
- If the data you need isn't in the snapshot (e.g. APRs on credit cards, income),
  say what's missing and ask the user to supply it.
- When `user_profile` is present, tailor recommendations to it: more aggressive
  growth advice for `risk_tolerance='aggressive'` and longer `time_horizon_years`,
  more conservative emergency-fund / cash-buffer advice for higher `dependents`
  or `risk_tolerance='conservative'`, and order debt-payoff suggestions by
  `debt_strategy` (`avalanche` = highest APR first, `snowball` = smallest balance
  first, `minimum` = only minimums).  When `user_profile` is missing and the
  user asks an investment, retirement, or debt-strategy question, ask once for
  the relevant fields and offer to save them.
- Keep replies short and actionable.  Prefer bullet points for recommendations.
- Never ask the user to run commands or edit files — you are talking to them in
  their finance app.
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _render_snapshot(snapshot: Dict[str, Any]) -> str:
    """Format the financial snapshot for inclusion in the system prompt."""
    return "FINANCIAL_SNAPSHOT:\n" + json.dumps(snapshot, indent=2, default=str)


def _trim_history(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Keep only the last N turns (role+content), dropping timestamps."""
    tail = messages[-state.ADVISOR_MAX_HISTORY:]
    return [{"role": m["role"], "content": m["content"]} for m in tail]


def _conversation_preview(messages: List[Dict[str, Any]]) -> str:
    """Return the first user message, trimmed to 80 chars."""
    for m in messages:
        if m.get("role") == "user":
            content = (m.get("content") or "").strip().replace("\n", " ")
            return content[:80] + ("…" if len(content) > 80 else "")
    return ""


@router.post("/advisor/chat", response_model=ChatResponse)
async def advisor_chat(req: ChatRequest, background_tasks: BackgroundTasks):
    """Send a user message and receive the advisor's reply.

    Creates a new conversation when conversation_id is omitted or unknown.
    Persists both user and assistant messages to ``json_stores`` (PgStore)
    AND to the structured ``conversation_turns`` table so embeddings have
    a stable FK target for RAG retrieval in future turns.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty")

    conv_id = req.conversation_id
    if not conv_id or conv_id not in state.conversations:
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        state.conversations[conv_id] = {
            "conversation_id": conv_id,
            "created": _now_iso(),
            "updated": _now_iso(),
            "messages": [],
        }

    conv = state.conversations[conv_id]
    user_msg = {"role": "user", "content": req.message.strip(), "ts": _now_iso()}
    conv["messages"].append(user_msg)

    # Build grounded system prompt freshly each turn so the advisor always
    # sees the current snapshot (txns/balances may have changed mid-chat).
    snapshot = build_financial_snapshot()
    system_prompt = SYSTEM_PROMPT + "\n\n" + _render_snapshot(snapshot)

    # Phase 6: retrieve semantically similar past turns (excluding this conv)
    # and append as a context block. Silent no-op if Ollama embeddings are
    # unavailable or nothing crosses the cosine threshold.
    try:
        rag_hits = await retrieve_similar(req.message, exclude_conv_id=conv_id)
        rag_block = format_rag_context(rag_hits)
        if rag_block:
            system_prompt += "\n\n" + rag_block
            logger.info(f"[advisor] RAG retrieved {len(rag_hits)} similar turns")
    except Exception as e:
        logger.warning(f"[advisor] RAG retrieval failed: {e}")

    # Transaction-level RAG: surface specific historical charges that look
    # related to the user's question (e.g. "what was that $300 charge?").
    try:
        txn_hits = await retrieve_similar_transactions(req.message)
        txn_block = format_txn_rag_context(txn_hits)
        if txn_block:
            system_prompt += "\n\n" + txn_block
            logger.info(f"[advisor] RAG retrieved {len(txn_hits)} similar transactions")
    except Exception as e:
        logger.warning(f"[advisor] Transaction RAG retrieval failed: {e}")

    history = _trim_history(conv["messages"])

    result = await chat_ollama(messages=history, system=system_prompt)
    reply_text = result["text"] if result["ai_available"] else None

    if result["ai_available"] and reply_text:
        conv["messages"].append({
            "role": "assistant",
            "content": reply_text,
            "ts": _now_iso(),
        })

    conv["updated"] = _now_iso()
    # PgStore returns a fresh dict snapshot; write back to persist the
    # appended messages and updated timestamp.
    state.conversations[conv_id] = conv

    # Phase 6: mirror the updated conversation into the structured tables
    # and schedule background embedding of any newly-added turns. The
    # response returns immediately; embeddings populate asynchronously.
    try:
        sync_conversation_turns(conv)
        background_tasks.add_task(embed_pending_turns, conv_id)
        # Catch up on any newly-uploaded / edited transactions so the next
        # chat turn can semantically find them. Idempotent and short-circuits
        # when nothing has drifted.
        background_tasks.add_task(embed_pending_transactions)
    except Exception as e:
        logger.warning(f"[advisor] Turn persistence / embed scheduling failed: {e}")

    return ChatResponse(
        conversation_id=conv_id,
        reply=reply_text,
        ai_available=result["ai_available"],
    )


@router.get("/advisor/conversations", response_model=List[ConversationSummary])
async def list_conversations():
    """List all conversations, most recent first."""
    out: List[ConversationSummary] = []
    for conv in state.conversations.values():
        msgs = conv.get("messages", [])
        out.append(ConversationSummary(
            conversation_id=conv["conversation_id"],
            created=conv.get("created", ""),
            updated=conv.get("updated", ""),
            message_count=len(msgs),
            preview=_conversation_preview(msgs),
        ))
    out.sort(key=lambda c: c.updated, reverse=True)
    return out


@router.get("/advisor/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Return the full message history for one conversation."""
    conv = state.conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Conversation(**conv)


@router.delete("/advisor/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str):
    """Remove a conversation permanently."""
    if conversation_id not in state.conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    del state.conversations[conversation_id]
    state._conversations_store.save()
