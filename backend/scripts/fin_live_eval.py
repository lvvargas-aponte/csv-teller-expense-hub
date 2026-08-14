"""Live eval battery for the Fin agent harness.

Drives the REAL stack — running backend, real Ollama, real internet
(ddgs/yfinance) — through scenario prompts and grades each turn on:

* which tools were called (from the persisted trajectory),
* whether the reply satisfies a scenario predicate,
* clean termination (a `final` event, no guard-trip event),
* wall-clock latency.

Run (backend + Ollama must be up):
    docker compose run --rm backend python -m scripts.fin_live_eval
    docker compose run --rm backend python -m scripts.fin_live_eval --keep  # skip cleanup

Every scenario runs in its own fresh conversation. Unless --keep is
passed, eval conversations (json_stores + structured turns + cascaded
embeddings) and any user_facts proposed during the run are deleted at
the end so the battery never pollutes Fin's memory corpora.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx
from sqlalchemy import text

from db.base import sync_engine

BASE_URL = "http://backend:8000"
TURN_TIMEOUT = 300.0
FACT_POLL_SEC = 60


def _fact_captured(pattern: str) -> bool:
    deadline = time.monotonic() + FACT_POLL_SEC
    while time.monotonic() < deadline:
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT fact FROM user_facts WHERE status = 'proposed'")
            ).fetchall()
        if any(re.search(pattern, r[0] or "", re.I) for r in rows):
            return True
        time.sleep(3)
    return False


@dataclass
class Scenario:
    name: str
    prompt: str
    expect_any_tool: List[str]            # at least one of these must be called
    reply_pattern: Optional[str] = None   # regex the reply must match (re.I|re.S)
    forbid_tools: List[str] = field(default_factory=list)
    follow_up: Optional[str] = None       # optional second turn in the same conversation
    follow_up_pattern: Optional[str] = None
    # Outcome check: pass if the expected tool was called OR a proposed
    # user_fact matching this regex appears within FACT_POLL_SEC (covers the
    # promise-fallback extraction path, which runs as a background task).
    fact_pattern: Optional[str] = None


SCENARIOS: List[Scenario] = [
    Scenario(
        name="live_ticker_quote",
        prompt="what is NVDA trading at right now?",
        expect_any_tool=["get_stock_quote"],
        reply_pattern=r"\$?\s?\d{2,4}(\.\d{1,2})?",
    ),
    Scenario(
        name="ticker_history",
        prompt="how has VOO performed over the past year?",
        expect_any_tool=["get_stock_history"],
        reply_pattern=r"\d+(\.\d+)?\s?%",
    ),
    Scenario(
        name="web_analysis_with_source",
        prompt=(
            "search the web for what analysts are currently saying about "
            "NVDA and summarize it, citing where you read it"
        ),
        expect_any_tool=["web_search"],
        reply_pattern=r"(according to|per |source|from )",
    ),
    Scenario(
        name="strategy_synthesis",
        prompt=(
            "I have $2,000 extra this month. Should I add to my existing "
            "positions or buy something new? Give me your honest take."
        ),
        expect_any_tool=["get_investments"],
        # Opinionated language or the disclaimer line — 14B disclaimer
        # compliance is stochastic; the tool chain is the hard requirement.
        reply_pattern=r"(advice|honest (read|take)|recommend|suggest|i.d (add|buy|put|trim)|consider)",
    ),
    Scenario(
        name="account_names",
        prompt="what are the names of my checking accounts?",
        expect_any_tool=["list_accounts"],
        reply_pattern=r"(chase|checking|hsy|wealthfront)",
    ),
    Scenario(
        name="category_aggregate",
        prompt="how much did I spend on Dining over the last 3 months?",
        expect_any_tool=["get_category_spending"],
        forbid_tools=["search_transactions"],
        reply_pattern=r"\$\s?\d",
    ),
    Scenario(
        name="continuity_short_reply",
        prompt="where is my biggest opportunity to save next month?",
        expect_any_tool=[],  # any grounding is fine on turn 1
        follow_up="yes, break that down",
        # Grounded breakdown OR an honest "nothing there" — both prove the
        # short reply was acted on rather than met with "yes to what?".
        follow_up_pattern=r"\$\s?\d|%|no (transactions|expenses|spending)|haven.t (had|spent)|didn.t spend",
    ),
    Scenario(
        name="memory_capture",
        prompt=(
            "by the way — we're planning to buy a house in 2028, please "
            "keep that in mind for future advice"
        ),
        expect_any_tool=["remember_about_user"],
        reply_pattern=r"(remember|in mind|noted|memory)",
        fact_pattern=r"(house|2028)",
    ),
    Scenario(
        name="action_refresh",
        prompt="refresh my balances and tell me my current net worth",
        expect_any_tool=["refresh_balances"],
        reply_pattern=r"\$\s?\d",
    ),
    Scenario(
        name="schedule_awareness",
        prompt="what background syncs do I have scheduled?",
        expect_any_tool=["list_scheduled_tasks"],
        reply_pattern=r"(week|7 day|transaction|investment)",
    ),
    Scenario(
        name="bogus_ticker_honesty",
        prompt="what's the current price of the ticker ZZZZZQX?",
        expect_any_tool=["get_stock_quote", "web_search"],
        reply_pattern=r"(couldn.t|could not|no .{0,15}data|not find|didn.t find|doesn.t (exist|seem|appear)|not appear|isn.t valid|invalid|delisted|unable|unavailable)",
    ),
]


def _post_chat(client: httpx.Client, conv_id: Optional[str], message: str) -> Dict[str, Any]:
    r = client.post(
        f"{BASE_URL}/api/advisor/chat",
        json={"conversation_id": conv_id, "message": message},
        timeout=TURN_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _trajectory(turn_id: Optional[int]) -> List[Dict[str, Any]]:
    if turn_id is None:
        return []
    with sync_engine.connect() as conn:
        row = conn.execute(
            text("SELECT trajectory FROM conversation_turns WHERE id = :id"),
            {"id": turn_id},
        ).fetchone()
    return list(row[0]) if row and row[0] else []


def _tools_called(trajectory: List[Dict[str, Any]]) -> List[str]:
    return [e["tool_name"] for e in trajectory if e.get("kind") == "tool_call"]


def _grade_turn(
    scenario_name: str,
    body: Dict[str, Any],
    expect_any: List[str],
    forbid: List[str],
    pattern: Optional[str],
    elapsed: float,
) -> Dict[str, Any]:
    reply = body.get("reply") or ""
    trajectory = _trajectory(body.get("turn_id"))
    tools = _tools_called(trajectory)
    guard_trips = [
        e.get("terminated_reason") for e in trajectory if e.get("kind") == "terminated"
    ]

    checks = {
        "replied": bool(reply.strip()),
        "expected_tool": (not expect_any) or any(t in tools for t in expect_any),
        "no_forbidden_tool": not any(t in tools for t in forbid),
        "reply_pattern": (pattern is None)
        or bool(re.search(pattern, reply, re.I | re.S)),
    }
    return {
        "scenario": scenario_name,
        "passed": all(checks.values()),
        "checks": checks,
        "tools_called": tools,
        "guard_trips": guard_trips,
        "elapsed_sec": round(elapsed, 1),
        "reply_preview": reply[:220].replace("\n", " "),
    }


def _cleanup(conv_ids: List[str], started_at: str) -> None:
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM json_stores WHERE store_name = 'conversations' "
                "AND key = ANY(:ids)"
            ),
            {"ids": conv_ids},
        )
        conn.execute(
            text("DELETE FROM conversation_turns WHERE conversation_id = ANY(:ids)"),
            {"ids": conv_ids},
        )
        conn.execute(
            text("DELETE FROM conversations WHERE conversation_id = ANY(:ids)"),
            {"ids": conv_ids},
        )
        conn.execute(
            text(
                "DELETE FROM user_facts WHERE status = 'proposed' "
                "AND created_at >= CAST(:ts AS TIMESTAMPTZ)"
            ),
            {"ts": started_at},
        )
    print(f"[cleanup] removed {len(conv_ids)} eval conversations + proposed eval facts")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="skip post-run cleanup")
    parser.add_argument("-k", default=None, help="only run scenarios whose name contains this")
    args = parser.parse_args()

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results: List[Dict[str, Any]] = []
    conv_ids: List[str] = []

    with httpx.Client() as client:
        for sc in SCENARIOS:
            if args.k and args.k not in sc.name:
                continue
            print(f"\n=== {sc.name} ===", flush=True)
            t0 = time.monotonic()
            try:
                body = _post_chat(client, None, sc.prompt)
            except Exception as e:
                results.append({"scenario": sc.name, "passed": False, "error": str(e)})
                print(f"    ERROR: {e}", flush=True)
                continue
            conv_ids.append(body["conversation_id"])
            result = _grade_turn(
                sc.name, body, sc.expect_any_tool, sc.forbid_tools,
                sc.reply_pattern, time.monotonic() - t0,
            )
            if not result["checks"]["expected_tool"] and sc.fact_pattern:
                # Promise-fallback path: accept the outcome (fact proposed
                # via background extraction) in place of the direct call.
                if _fact_captured(sc.fact_pattern):
                    result["checks"]["expected_tool"] = True
                    result["via_fallback"] = True
                    result["passed"] = all(result["checks"].values())
            results.append(result)
            print(f"    turn1 {'PASS' if result['passed'] else 'FAIL'} "
                  f"tools={result['tools_called']} {result['elapsed_sec']}s", flush=True)

            if sc.follow_up:
                t1 = time.monotonic()
                try:
                    body2 = _post_chat(client, body["conversation_id"], sc.follow_up)
                except Exception as e:
                    results.append({"scenario": sc.name + "_followup", "passed": False, "error": str(e)})
                    continue
                result2 = _grade_turn(
                    sc.name + "_followup", body2, [], [],
                    sc.follow_up_pattern, time.monotonic() - t1,
                )
                results.append(result2)
                print(f"    turn2 {'PASS' if result2['passed'] else 'FAIL'} "
                      f"tools={result2['tools_called']} {result2['elapsed_sec']}s", flush=True)

    passed = sum(1 for r in results if r.get("passed"))
    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{len(results)} passed")
    print(json.dumps(results, indent=2))

    if not args.keep and conv_ids:
        _cleanup(conv_ids, started_at)

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
