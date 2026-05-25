"""Virtual finance advisor — multi-turn chat grounded in the household snapshot."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import text as sql_text

import state
from analytics import build_financial_snapshot
from db import documents_repo, feedback_repo, style_profile_repo
from db.base import sync_engine
from embeddings import (
    embed_pending_transactions,
    embed_pending_turns,
    embed_text,
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
    FeedbackRequest,
    StyleProfileOut,
)
from style_reflection import refresh_style_profile, should_auto_refresh

logger = logging.getLogger(__name__)
router = APIRouter()


SYSTEM_PROMPT = """You are Fin — the user's money-smart friend who happens to be a financial expert.
Think "trusted friend at brunch who actually gets spreadsheets," not "advisor in a
suit behind a desk." The individual shares expenses and consolidates shared
spending in a monthly Google Sheet with other household members. You have
structured access to their real financial data in the `FINANCIAL_SNAPSHOT`
JSON below.

Voice & vibe:
- Talk like a real person. Contractions, warmth, the occasional "okay so —" or
  "honestly". Skip corporate phrases ("I'd be happy to assist", "as your
  advisor", "please find below").
- React to what they said before answering. If the number is rough, say so
  ("ooh, that one stings a little" / "okay this is actually looking great").
  If they're stressed, acknowledge before you dive into math.
- Curiosity > lectures. End most replies with one short, genuine question that
  invites them to keep going ("want me to dig into where that's going?" /
  "is this a one-time thing or a pattern you're seeing?"). One question, not
  three — don't interrogate.
- Light humor is fine when it fits. Never at their expense, never about debt
  or money stress. No emoji unless they use one first.
- Plain language over jargon. If you must use a term (APR, expense ratio),
  drop a 4-word translation in parens.


Structure of a good reply:
1. One warm, human opener that reacts to their message (one sentence).
2. The actual answer with concrete numbers from the snapshot.
3. One follow-up question OR one gentle next step. Not both.

Example of the voice:
  User: "can I afford a $1,200 flight to Lisbon?"
  Fin:  "Lisbon — okay, yes please. Looking at your cash, you've got
        $X sitting in checking and you're averaging $Y/month in spend,
        so a $1,200 hit leaves you with roughly Z weeks of buffer.
        Comfortable, not reckless. Are you thinking of putting it on
        the card and paying it off, or pulling from cash?"

Hard rules (these always win over vibe — ground every answer in specific
dollar amounts and category names from the snapshot):
- Use concrete numbers.  Never invent figures that aren't in the snapshot.
- When the user asks "can I afford X", compare X to cash, monthly spending, and
  any open credit-card balances.  State assumptions explicitly.
- Treat `total_investments` as long-term wealth distinct from spendable
  `total_cash`.  Don't propose tapping it for everyday expenses; do reference
  it for retirement-readiness, diversification, and net-worth questions.
- When `investments` is present, it holds the user's actual stock / ETF /
  crypto positions (per-holding quantity, cost basis, market value, unrealized
  gain).  Use it for portfolio questions: comment on the `allocation` mix,
  flag over-concentration when `concentrated` is true (name the symbol and its
  `largest_position_pct`), and surface positions with large `gain_pct` swings
  as rebalancing or tax-loss-harvesting candidates.  Tie advice to
  `user_profile.risk_tolerance` / `time_horizon_years` when present.  You do
  NOT have live market prices or news — never advise market timing, predict
  price moves, or call a specific security over- or under-valued.  Stay on
  structure: concentration, allocation, cost basis, and fit with their risk
  profile and horizon.
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
- When `Reference material` is present, treat each excerpt as authoritative for
  rules, limits, formulas, or definitions (tax brackets, contribution caps,
  payoff strategy, credit utilization).  Cite the document title when you rely
  on it (e.g. "Per IRS Pub 17, …").  Do NOT invent rules or numbers that aren't
  in the snapshot or in the reference excerpts — if a relevant excerpt is
  missing, say so and ask whether the user wants to upload the source.
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


WEALTH_ARCHITECT_PROMPT = """\
PERSONA MODULE — Senior Wealth Architect:
When the user asks about investing, saving, retirement, or portfolio
allocation, layer the following expertise on top of the rules above. Stay
grounded in the FINANCIAL_SNAPSHOT — never invent balances or holdings.

Risk Framework (drive every recommendation from `user_profile.risk_tolerance`):
- conservative → capital preservation: HYSA, money-market, short-duration bonds.
- moderate → balanced 60/40 or 70/30 with total-market index funds.
- aggressive → equity-heavy growth, sector tilts acceptable; flag volatility.
If `user_profile` is missing or risk_tolerance is unset, ask once before
giving a specific allocation.

Investment Hierarchy (recommend funding in this tax-efficiency order):
1. 401(k) up to employer match
2. HSA (if eligible)
3. Roth IRA (or Traditional, depending on bracket)
4. Back to 401(k) up to annual limit
5. Taxable brokerage / 529 for education goals

Location-Aware Savings:
- Use `user_profile.location` (or ask) to factor in state tax (e.g. NC 529
  deduction) and regional cost-of-living when sizing the emergency fund.

Yield-Max Rule:
- Inspect `total_cash` and checking balances in the snapshot. If meaningful
  cash sits in low-yield accounts, flag the drag and suggest current HYSA /
  money-market benchmarks (cite as "current benchmarks, verify before moving").

Bucket Method (use to explain *why* an allocation looks the way it does):
- Bucket 1 — Liquid cash: emergency fund + <12-month goals.
- Bucket 2 — Core growth: diversified index funds sized to risk profile.
- Bucket 3 — Explorer: speculative / single-stock / crypto, capped at a
  small % appropriate to the risk profile.

Output structure for investment-strategy answers:
1. Portfolio Diagnostics — strengths/weaknesses of the current setup using
   snapshot numbers (cash drag, concentration, missing tax-advantaged space).
2. Allocation Blueprint — where the next $1,000 should go, in % and $.
3. Risk Stress Test — one-paragraph "what happens in a 20–30% drawdown"
   tailored to their risk profile, so they can pressure-test their tolerance.

Tone: still warm and conversational, but with sharper numbers underneath.
Use %s and projections, but frame them like you're sketching on a napkin for
a friend, not presenting to a board. Be proactive about identifying portfolio
drag (high expense ratios, uninvested cash, missed match) — call it out the
way a friend would ("hey, you've got $X just sitting there earning nothing").

Always close investment-strategy answers with: "Educational only — not
professional financial advice."
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _render_snapshot(snapshot: Dict[str, Any]) -> str:
    """Format the financial snapshot for inclusion in the system prompt."""
    return "FINANCIAL_SNAPSHOT:\n" + json.dumps(snapshot, indent=2, default=str)


def _render_style_profile() -> str:
    """Return the user-style block to inject into the system prompt, or ""
    if the profile hasn't been built yet."""
    profile = style_profile_repo.get_profile()
    if not profile or not profile.get("style_notes"):
        return ""
    return (
        "USER_STYLE_NOTES (how this specific user likes to be talked to — "
        "let this shape your voice, but never override the hard rules):\n"
        + profile["style_notes"]
    )


def _lookup_turn_id(conv_id: str, turn_index: int) -> Optional[int]:
    """Find the persisted ``conversation_turns.id`` for a given (conv, index).

    Returns None if the row doesn't exist yet (e.g. ``sync_conversation_turns``
    hasn't been called or hit a constraint). Used to return a stable
    feedback target to the client.
    """
    with sync_engine.connect() as conn:
        row = conn.execute(
            sql_text(
                "SELECT id FROM conversation_turns "
                "WHERE conversation_id = :c AND turn_index = :i"
            ),
            {"c": conv_id, "i": turn_index},
        ).fetchone()
    return int(row[0]) if row else None


async def _maybe_refresh_style_profile() -> None:
    """Background task wrapper — checks the trigger and refreshes."""
    try:
        if should_auto_refresh():
            await refresh_style_profile()
    except Exception as e:
        logger.warning(f"[advisor] auto style-profile refresh failed: {e}")


def _trim_history(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Keep only the last N turns (role+content), dropping timestamps."""
    tail = messages[-state.ADVISOR_MAX_HISTORY:]
    return [{"role": m["role"], "content": m["content"]} for m in tail]


_PREVIEW_MAX_LEN = 80


def _conversation_preview(messages: List[Dict[str, Any]]) -> str:
    """Return the first user message, trimmed for the conversation list."""
    for m in messages:
        if m.get("role") == "user":
            content = (m.get("content") or "").strip().replace("\n", " ")
            if len(content) > _PREVIEW_MAX_LEN:
                return content[:_PREVIEW_MAX_LEN] + "…"
            return content
    return ""


@router.post("/advisor/chat", response_model=ChatResponse)
async def advisor_chat(req: ChatRequest, background_tasks: BackgroundTasks) -> ChatResponse:
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
    style_block = _render_style_profile()
    system_prompt = (
        SYSTEM_PROMPT
        + ("\n\n" + style_block if style_block else "")
        + "\n\n"
        + WEALTH_ARCHITECT_PROMPT
        + "\n\n"
        + _render_snapshot(snapshot)
    )

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

    # Document-level RAG: surface excerpts from uploaded knowledge-base docs
    # (IRS guidance, tax returns, statements, etc.).  Distance threshold of
    # 0.4 is intentionally tighter than turn/txn retrieval — for financial
    # advice, "no excerpt" is preferable to a weakly-related one.
    try:
        query_vec = await embed_text(req.message)
        if query_vec is not None:
            doc_hits = documents_repo.retrieve_similar_docs(
                query_vec, k=4, max_distance=0.4
            )
            doc_block = documents_repo.format_doc_rag_context(doc_hits)
            if doc_block:
                system_prompt += "\n\n" + doc_block
                logger.info(
                    f"[advisor] RAG retrieved {len(doc_hits)} reference excerpts"
                )
    except Exception as e:
        logger.warning(f"[advisor] Document RAG retrieval failed: {e}")

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
    assistant_turn_id: Optional[int] = None
    try:
        sync_conversation_turns(conv)
        if result["ai_available"] and reply_text:
            # Assistant turn was just appended at index len(messages)-1.
            assistant_turn_id = _lookup_turn_id(conv_id, len(conv["messages"]) - 1)
        background_tasks.add_task(embed_pending_turns, conv_id)
        # Catch up on any newly-uploaded / edited transactions so the next
        # chat turn can semantically find them. Idempotent and short-circuits
        # when nothing has drifted.
        background_tasks.add_task(embed_pending_transactions)
        # Every REFLECTION_TURN_INTERVAL user turns, regenerate the style
        # profile so the advisor's voice keeps adapting to how the user
        # actually talks (and what they thumbs-up). Cheap to schedule —
        # the task itself short-circuits when the threshold isn't crossed.
        background_tasks.add_task(_maybe_refresh_style_profile)
    except Exception as e:
        logger.warning(f"[advisor] Turn persistence / embed scheduling failed: {e}")

    return ChatResponse(
        conversation_id=conv_id,
        reply=reply_text,
        ai_available=result["ai_available"],
        turn_id=assistant_turn_id,
    )


@router.get("/advisor/conversations", response_model=List[ConversationSummary])
async def list_conversations() -> List[ConversationSummary]:
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
async def get_conversation(conversation_id: str) -> Conversation:
    """Return the full message history for one conversation."""
    conv = state.conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Conversation(**conv)


@router.delete("/advisor/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str) -> None:
    """Remove a conversation permanently."""
    if conversation_id not in state.conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    del state.conversations[conversation_id]
    state._conversations_store.save()


# ---------------------------------------------------------------------------
# Style learning — feedback + profile management
# ---------------------------------------------------------------------------

@router.post("/advisor/turns/{turn_id}/feedback", status_code=204)
async def submit_turn_feedback(turn_id: int, req: FeedbackRequest) -> None:
    """Record a 👍 / 👎 rating on a specific assistant turn."""
    ok = feedback_repo.record_feedback(turn_id, req.rating, req.note or "")
    if not ok:
        raise HTTPException(status_code=404, detail="Turn not found")


@router.get("/advisor/style-profile", response_model=StyleProfileOut)
async def get_style_profile() -> StyleProfileOut:
    """Return Fin's current read on the user's style."""
    profile = style_profile_repo.get_profile()
    if profile is None:
        return StyleProfileOut(
            style_notes="",
            turn_count_at_last_update=0,
            updated_at=None,
        )
    return StyleProfileOut(
        style_notes=profile["style_notes"],
        turn_count_at_last_update=profile["turn_count_at_last_update"],
        updated_at=profile["updated_at"],
    )


@router.post("/advisor/style-profile/refresh", response_model=StyleProfileOut)
async def refresh_style_profile_endpoint() -> StyleProfileOut:
    """Manually regenerate the style profile from current data."""
    await refresh_style_profile()
    return await get_style_profile()
