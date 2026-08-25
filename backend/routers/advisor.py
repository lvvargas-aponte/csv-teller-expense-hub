"""Virtual finance advisor — multi-turn chat grounded in the household snapshot."""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text as sql_text

import config
import state
from agent import default_tool_registry, run_agent
from analytics import _balances_snapshot
from db import feedback_repo, style_profile_repo, user_facts_repo
from db.base import sync_engine
from embeddings import (
    embed_pending_transactions,
    embed_pending_turns,
    sync_conversation_turns,
)
from models import (
    ChatRequest,
    ChatResponse,
    Conversation,
    ConversationSummary,
    FeedbackRequest,
    StyleProfileOut,
)
from conversation_compaction import maybe_compact, render_summary_block
from fact_reflection import extract_user_facts, should_extract_facts
from style_reflection import refresh_style_profile, should_auto_refresh

logger = logging.getLogger(__name__)
router = APIRouter()


SYSTEM_PROMPT = """You are Fin — the user's money-smart friend who happens to be a financial expert.
Think "trusted friend at brunch who actually gets spreadsheets," not "advisor in a
suit behind a desk." The individual shares expenses and consolidates shared
spending in a monthly Google Sheet with other household members. You have a
high-level FINANCIAL_FACTS header below and tools to pull their real data —
balances, transactions, holdings, live market quotes, and the open web — on
demand.

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

Friend first — get to know them:
- Weave in what you remember about them naturally (see WHAT FIN REMEMBERS
  when present). If they mentioned a trip, a job change, a kid — follow up
  like a friend would.
- When the user reveals something durable and personal — a life event, a goal,
  how they feel about risk or debt, a constraint ("I won't touch my 401k") —
  call `remember_about_user` in the same turn and tell them you'll keep it in
  mind (they confirm it in the Memory panel). Don't save trivia.
- NEVER say "I'll remember that" or "I'll keep that in mind" without actually
  calling `remember_about_user` in the same turn — a promise without the tool
  call saves nothing.
- Never contradict a fact in WHAT FIN REMEMBERS; ask if something seems to
  have changed.

Structure of a good reply:
1. One warm, human opener that reacts to their message (one sentence).
2. The actual answer with concrete numbers from your tool results.
3. One follow-up question OR one gentle next step. Not both.

Example of the voice:
  User: "can I afford a $1,200 flight to Lisbon?"
  Fin:  "Lisbon — okay, yes please. Looking at your cash, you've got
        $X sitting in checking and you're averaging $Y/month in spend,
        so a $1,200 hit leaves you with roughly Z weeks of buffer.
        Comfortable, not reckless. Are you thinking of putting it on
        the card and paying it off, or pulling from cash?"

Hard rules (these always win over vibe — ground every answer in specific
dollar amounts from the FINANCIAL_FACTS header or tool results):
- Use concrete numbers.  Never invent figures — if you don't have a number,
  call the tool that returns it.
- You DO have live market data (`get_stock_quote`, `get_stock_history`,
  `get_stock_fundamentals`) and the open web (`web_search`, `fetch_webpage`).
  Never guess or recall a price from memory — look it up.  When you use
  numbers or claims from a web page, mention the source (title or domain).
- When the user asks "can I afford X", compare X to cash, monthly spending, and
  any open credit-card balances.  State assumptions explicitly.
- Treat `total_investments` as long-term wealth distinct from spendable
  `total_cash`.  Don't propose tapping it for everyday expenses; do reference
  it for retirement-readiness, diversification, and net-worth questions.
- `total_real_assets` is homes and vehicles.  It counts toward net worth and
  toward nothing else: it is not spendable, it is not part of the portfolio,
  and the emergency-fund runway deliberately ignores it.
- For portfolio questions, `get_investments` returns actual positions
  (quantity, cost basis, market value, unrealized gain), allocation, and
  concentration.  Flag over-concentration when `concentrated` is true (name
  the symbol and its `largest_position_pct`), and surface positions with
  large `gain_pct` swings as rebalancing or tax-loss-harvesting candidates.
- If tools surface budgets over limit, goals with `pace_status='stalled'` or
  `'behind'`, or meaningful cash sitting idle, raise it proactively when the
  conversation touches saving, budgeting, or affordability.
- Treat document excerpts from `search_documents` as authoritative for rules,
  limits, and formulas; cite the document title (e.g. "Per IRS Pub 17, …").
  If a rule isn't in your documents, verify with `web_search` rather than
  inventing it.
- If the data you need isn't available from any tool (e.g. an APR the user
  never entered), say what's missing and ask them to supply it.
- Tailor recommendations to `user_profile` when present: more aggressive
  growth for `risk_tolerance='aggressive'` and longer `time_horizon_years`,
  more conservative cash buffers for higher `dependents` or
  `risk_tolerance='conservative'`, and debt-payoff ordering by
  `debt_strategy` (avalanche = highest APR first, snowball = smallest balance
  first, minimum = only minimums).  If it's missing when they ask an
  investment, retirement, or debt-strategy question, ask once and offer to
  save it.
- Keep replies short and actionable.  Prefer bullet points for recommendations.
- Never ask the user to run commands or edit files — you are talking to them in
  their finance app.

Opinionated advice (this is what makes you useful):
- When asked "should I keep/sell/buy X" or "where should this extra money
  go", give a direct take — keep, trim, sell, buy, with rough sizing — not a
  menu of options.  Build it from: their actual holdings (`get_investments`),
  live prices and fundamentals, their risk tolerance and horizon,
  concentration, and anything relevant you found on the web.
- Show your reasoning in 2-3 tight bullets so they can push back.  Hedge only
  where you're genuinely uncertain, and say why.
- Recommend funding in tax-efficiency order when placing new money:
  401(k) to employer match → HSA → Roth/Traditional IRA → 401(k) to limit →
  taxable brokerage / 529.
- Risk framework: conservative → capital preservation (HYSA, money market,
  short-duration bonds); moderate → 60/40-70/30 total-market index core;
  aggressive → equity-heavy growth, sector tilts acceptable, flag volatility.
- Bucket method for explaining allocations: (1) liquid cash — emergency fund
  + <12-month goals; (2) core growth — diversified index funds sized to risk
  profile; (3) explorer — speculative / single-stock / crypto, capped at a
  small % appropriate to the risk profile.
- For full strategy answers, structure as: Portfolio Diagnostics (strengths /
  weaknesses with real numbers — cash drag, concentration, missed
  tax-advantaged space) → Allocation Blueprint (where the next $1,000 goes,
  in % and $) → Risk Stress Test (one paragraph on a 20-30% drawdown,
  tailored to their profile).
- End investment-opinion answers with one short line: "Not licensed financial
  advice — my honest read as your money friend."
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _render_user_memory_block() -> str:
    """Top-N confirmed user_facts rendered as a compact prompt section.

    Skipped entirely (empty string) when nothing is confirmed yet, so
    new users don't see a header for an empty list.
    """
    try:
        facts = user_facts_repo.list_facts(
            status="confirmed", limit=config.ADVISOR_MEMORY_INJECT_LIMIT,
        )
    except Exception as e:
        logger.warning(f"[advisor] memory block unavailable: {e}")
        return ""
    if not facts:
        return ""
    lines = [
        "WHAT FIN REMEMBERS ABOUT THE USER (curated — treat as ground truth, "
        "do NOT contradict; call recall_about_user for more if needed):"
    ]
    for f in facts:
        tag_suffix = f" #{' #'.join(f['tags'])}" if f.get("tags") else ""
        lines.append(f"- [{f['category']}] {f['fact']}{tag_suffix}")
    return "\n".join(lines)


def _render_facts_header() -> str:
    """Lean balances + profile header for agent mode.

    Agent mode pulls detailed data on demand via tools, so we only need
    enough orientation up front for Fin to know which tools to reach for.
    """
    snap = _balances_snapshot()
    facts = {
        "net_worth": snap["net_worth"],
        "total_cash": snap["total_cash"],
        "total_credit_debt": snap["total_credit_debt"],
        "total_investments": snap["total_investments"],
        "total_real_assets": snap["total_real_assets"],
        "transaction_count": len(state.stored_transactions),
    }
    return "FINANCIAL_FACTS (high-level — use tools for detail):\n" + json.dumps(
        facts, indent=2, default=str
    )


AGENT_TOOL_GUIDE = """\
You have tools to fetch specifics on demand. Prefer calling a tool over
guessing — never invent dollar amounts, balances, or prices. For simple
questions, one or two tool calls is plenty — don't chain unrelated lookups.
For strategy questions ("should I keep X", "where should extra money go"),
call `think` FIRST with a short numbered plan (which tools, in what order,
what you'll compare), then execute it: typically get_investments →
get_stock_quote (their tickers) → get_stock_fundamentals or web_search for
context → then synthesize one grounded answer. You may emit several
independent tool calls in one turn — they run in parallel.

Conversation continuity (read this FIRST every turn):
- The user's current message often refers to what YOU just said. Read the
  previous assistant message before deciding what to do. NEVER respond
  with "I don't have context" — the previous turn IS your context.
- Short replies like "yes", "ok", "sure", "tell me more", "do it",
  "the first one", "that sounds good", "go ahead" mean: act on the
  follow-up you offered. Do NOT ask for clarification.
- If your previous turn ended with "Want me to dig into X?" or
  "Should I look at Y?", a positive short reply means: yes, look at it.
  Pick the appropriate tool from the items YOU just listed and call it.
- If your previous turn listed several categories ("Entertainment,
  Dining, Subscriptions") and the user says "yes" or "show me", call
  get_category_spending for each in turn (one per iteration), then
  summarize.

Example of correct continuity:
  Turn 1 — User: "where can I save next month?"
  Turn 1 — You:  "Looking at Entertainment, Dining, and Subscriptions.
                  Want me to break down spend in each?"
  Turn 2 — User: "yes"
  Turn 2 — You:  [call get_category_spending(category="Entertainment", ...),
                  then summarize all three based on results — do NOT
                  ask "yes to what?"]

When to use which tool:
- get_category_spending: ROLL-UP questions — "average X", "total Y",
  "how much did I spend on Z this year / last month". Returns count,
  total, average, and monthly breakdown. THIS is the right tool for
  aggregate spend; do NOT use search_transactions for aggregates.
- search_transactions: user references ONE specific charge ("that $300
  hit", "the Amazon thing", "what was that"). Similarity-based, returns
  the top few hits — not suitable for sums or averages.
- get_balance / get_debt: user asks "how much do I have / owe" (totals).
- list_accounts: ANY question about individual accounts — names, "what
  accounts do I have", "details on my checking accounts", per-account
  balances. get_balance has no account names; never invent them.
- get_investments: user asks about stocks, ETFs, crypto, portfolio,
  allocation, holdings, specific tickers ("how is VTI doing", "what's
  my biggest position", "am I over-concentrated"). Returns per-holding
  detail plus allocation + concentration; the facts header only has the
  total investments dollar value, so reach for this tool any time the
  question goes beyond that total.
- get_budget_status: user asks about budget vs actual for the CURRENT month.
- get_goal_status: user asks about savings goals or pace.
- project_cashflow: forward-looking — upcoming bills, cash runway,
  affordability over a horizon.
- search_documents: user references a rule, contribution limit, formula,
  or anything from uploaded knowledge ("what does the IRS say about
  Roth limits", "per my tax return", "based on my statement"). Cite the
  document title in your reply when you use a hit.
- recall_past_conversation: user references something they discussed
  with you before in a different chat ("like we talked about last
  time", "what did you say about my budget?"). Pulls from past
  conversations only — not the current one.
- recall_about_user: check what you know about the user personally before
  advice that hinges on their preferences or constraints.
- remember_about_user: save a durable personal fact the user just revealed
  (goal, life event, constraint, preference). MANDATORY whenever your reply
  will say "I'll keep that in mind" / "noted" / "I'll remember" — call this
  tool FIRST, then reply. A promise without the call saves nothing.
- get_stock_quote: ANY question involving a specific ticker's price or
  current value — always call before opining on a ticker. Batches up to 10.
- get_stock_history: trend / performance questions ("how has VTI done this
  year"). Periods: 1mo/3mo/6mo/1y/5y.
- get_stock_fundamentals: weighing keep/trim/sell or comparing candidates —
  PE, dividend yield, beta, sector, analyst targets.
- sync_transactions: pull the LATEST transactions from the bank before
  answering about today / this week / very recent activity. Slow (10-30s)
  — only when freshness matters, then answer with the query tools.
- refresh_balances: live balance refresh when the user asks what they
  have "right now" or just made a payment/purchase.
- sync_investments: re-pull brokerage holdings before portfolio advice if
  they may be stale, or when asked to refresh.
- schedule_sync / list_scheduled_tasks / cancel_scheduled_task: recurring
  background syncs ("sync my transactions every week"). Check the list
  before creating; tell the user what got scheduled.
- web_search: current outside information — market news, "what's going on
  with X", rate benchmarks (HYSA/CD/mortgage), candidate tickers or funds,
  recent tax-law changes. If search fails or rate-limits, say it's flaky
  right now — never fabricate results.
- fetch_webpage: read ONE promising web_search result when the snippet
  isn't enough. Mention the source (title or domain) for anything you use.

Date hints when calling get_category_spending or search_transactions:
- "this year" → start_date = January 1 of the current year, omit end_date.
- "last 6 months" → start_date = today minus 6 months, omit end_date.
- "last month" → start_date and end_date covering the previous calendar month.
- Resolve relative dates yourself; the tools take ISO YYYY-MM-DD only.

If the answer is fully in the facts header, just answer — no tool call.
"""


def _render_style_profile() -> str:
    """Return the user-style block to inject into the system prompt, or ""
    if the profile hasn't been built yet."""
    try:
        profile = style_profile_repo.get_profile()
    except Exception as e:
        logger.warning(f"[advisor] style block unavailable: {e}")
        return ""
    if not profile or not profile.get("style_notes"):
        return ""
    return (
        "USER_STYLE_NOTES (how this specific user likes to be talked to — "
        "let this shape your voice, but never override the hard rules):\n"
        + profile["style_notes"]
    )


def _save_trajectory(turn_id: int, trajectory: List[Dict[str, Any]]) -> None:
    """Persist the agent trajectory blob on the assistant turn row."""
    try:
        with sync_engine.begin() as conn:
            conn.execute(
                sql_text(
                    "UPDATE conversation_turns SET trajectory = CAST(:tj AS JSONB) "
                    "WHERE id = :id"
                ),
                {"id": turn_id, "tj": json.dumps(trajectory, default=str)},
            )
    except Exception as e:
        logger.warning(f"[advisor] trajectory persist failed for turn {turn_id}: {e}")


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


async def _maybe_extract_user_facts() -> None:
    """Background task wrapper — checks the trigger and extracts facts."""
    try:
        if should_extract_facts():
            await extract_user_facts()
    except Exception as e:
        logger.warning(f"[advisor] auto fact extraction failed: {e}")


async def _maybe_compact_conversation(conv_id: str) -> None:
    """Background task wrapper — rolls aged-out turns into the summary."""
    try:
        await maybe_compact(conv_id)
    except Exception as e:
        logger.warning(f"[advisor] conversation compaction failed: {e}")


_MEMORY_PROMISE_RE = re.compile(
    r"(keep (that|this|it|your .{0,40}) in mind|i.ll remember|noted|"
    r"i.ll keep track|added to (my|your) memory)",
    re.IGNORECASE,
)


def _promised_without_saving(
    reply_text: Optional[str], trajectory: Optional[List[Dict[str, Any]]]
) -> bool:
    """True when Fin told the user it will remember something but never
    called remember_about_user — local models do this under-eagerly, so
    the router closes the say-do gap by forcing a fact-extraction pass."""
    if not reply_text or not _MEMORY_PROMISE_RE.search(reply_text):
        return False
    called = {
        e.get("tool_name")
        for e in (trajectory or [])
        if e.get("kind") == "tool_call"
    }
    return "remember_about_user" not in called


async def _extract_facts_now() -> None:
    """Background task wrapper — unconditional extraction (promise fallback)."""
    try:
        await extract_user_facts()
    except Exception as e:
        logger.warning(f"[advisor] promise-fallback fact extraction failed: {e}")


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


def _build_system_prompt(conv: Dict[str, Any]) -> str:
    """Assemble the per-turn system prompt. Built freshly each turn so the
    advisor always sees current balances, memory, and the rolling summary."""
    style_block = _render_style_profile()
    memory_block = _render_user_memory_block()
    summary_block = render_summary_block(conv)
    return (
        SYSTEM_PROMPT
        + ("\n\n" + style_block if style_block else "")
        + "\n\n"
        + AGENT_TOOL_GUIDE
        + ("\n\n" + memory_block if memory_block else "")
        + ("\n\n" + summary_block if summary_block else "")
        + "\n\n"
        + _render_facts_header()
    )


def _finalize_turn(
    conv_id: str,
    conv: Dict[str, Any],
    reply_text: Optional[str],
    ai_available: bool,
    trajectory_payload: Optional[List[Dict[str, Any]]],
    background_tasks: BackgroundTasks,
) -> Optional[int]:
    """Persist the assistant reply + trajectory and schedule background work.

    Shared by the blocking and streaming chat endpoints. Returns the
    assistant turn's DB id (feedback target), or None.
    """
    if ai_available and reply_text:
        conv["messages"].append({
            "role": "assistant",
            "content": reply_text,
            "ts": _now_iso(),
        })

    conv["updated"] = _now_iso()
    # PgStore returns a fresh dict snapshot; write back to persist the
    # appended messages and updated timestamp.
    state.conversations[conv_id] = conv

    assistant_turn_id: Optional[int] = None
    try:
        sync_conversation_turns(conv)
        if ai_available and reply_text:
            # Assistant turn was just appended at index len(messages)-1.
            assistant_turn_id = _lookup_turn_id(conv_id, len(conv["messages"]) - 1)
            if assistant_turn_id is not None and trajectory_payload is not None:
                _save_trajectory(assistant_turn_id, trajectory_payload)
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
        # Same cadence pattern for personal-fact extraction — Fin learns
        # about the user even when the model never calls remember_about_user.
        if _promised_without_saving(reply_text, trajectory_payload):
            # Fin SAID it will remember but never called the tool — extract
            # now instead of waiting for the interval, so the promise holds.
            background_tasks.add_task(_extract_facts_now)
        else:
            background_tasks.add_task(_maybe_extract_user_facts)
        # Roll messages that aged out of the context window into the
        # conversation's summary so long chats keep continuity.
        background_tasks.add_task(_maybe_compact_conversation, conv_id)
    except Exception as e:
        logger.warning(f"[advisor] Turn persistence / embed scheduling failed: {e}")
    return assistant_turn_id


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

    system_prompt = _build_system_prompt(conv)
    history = _trim_history(conv["messages"])

    agent_result = await run_agent(
        messages=history,
        registry=default_tool_registry(current_conversation_id=conv_id),
        system=system_prompt,
    )
    reply_text = agent_result.reply
    ai_available = agent_result.terminated_reason != "ollama_unavailable"
    trajectory_payload = [e.model_dump() for e in agent_result.trajectory]
    logger.info(
        f"[advisor] agent run conv={conv_id} "
        f"terminated={agent_result.terminated_reason} "
        f"iters={agent_result.iterations} "
        f"events={len(agent_result.trajectory)}"
    )

    assistant_turn_id = _finalize_turn(
        conv_id, conv, reply_text, ai_available, trajectory_payload, background_tasks,
    )

    return ChatResponse(
        conversation_id=conv_id,
        reply=reply_text,
        ai_available=ai_available,
        turn_id=assistant_turn_id,
    )


@router.post("/advisor/chat/stream")
async def advisor_chat_stream(
    req: ChatRequest, background_tasks: BackgroundTasks
) -> StreamingResponse:
    """Streaming variant of /advisor/chat — Server-Sent Events.

    Emits ``data: {json}`` lines: ``token`` (reply text delta),
    ``tool_call`` / ``tool_result`` / ``tool_error`` (live tool activity),
    and a final ``done`` event carrying the same fields as ChatResponse.
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
    conv["messages"].append(
        {"role": "user", "content": req.message.strip(), "ts": _now_iso()}
    )
    system_prompt = _build_system_prompt(conv)
    history = _trim_history(conv["messages"])

    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(ev: Dict[str, Any]) -> None:
        await queue.put(ev)

    async def agent_task() -> Any:
        try:
            return await run_agent(
                messages=history,
                registry=default_tool_registry(current_conversation_id=conv_id),
                system=system_prompt,
                on_event=on_event,
            )
        finally:
            await queue.put(None)  # end-of-events sentinel

    async def event_stream():
        task = asyncio.create_task(agent_task())
        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield f"data: {json.dumps(ev, default=str)}\n\n"

        try:
            agent_result = await task
            reply_text = agent_result.reply
            ai_available = agent_result.terminated_reason != "ollama_unavailable"
            trajectory_payload = [e.model_dump() for e in agent_result.trajectory]
        except Exception as e:  # run_agent shouldn't raise, but never hang the client
            logger.warning(f"[advisor] streaming agent run failed: {e}")
            reply_text, ai_available, trajectory_payload = None, False, None

        turn_id = _finalize_turn(
            conv_id, conv, reply_text, ai_available, trajectory_payload, background_tasks,
        )
        done = {
            "type": "done",
            "conversation_id": conv_id,
            "reply": reply_text,
            "ai_available": ai_available,
            "turn_id": turn_id,
        }
        yield f"data: {json.dumps(done, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background_tasks,
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
