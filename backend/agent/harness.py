"""Bounded tool-use loop around ``chat_ollama``.

Single entry point: ``run_agent(messages, registry, system, max_iters)``.
Guards baked in:
- max iterations (default from config)
- empty-reply break (known local-LLM failure mode)
- repeated-identical tool-call break (model loops on a tool it can't use)
- hallucinated tool name -> one corrective re-prompt, then fail closed
- invalid args (Pydantic ValidationError) -> one corrective re-prompt, then skip
- per-tool exception captured and fed back as a tool error message

The loop never raises on LLM/tool failures — it terminates with a
``terminated_reason`` so the caller can decide how to surface the issue.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import ValidationError

import config
from llm_client import chat_ollama, chat_ollama_stream

from agent.schemas import AgentResult, TrajectoryEvent
from agent.tools import Tool, ToolRegistry, TransientToolError

logger = logging.getLogger(__name__)

EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]

_RESULT_PREVIEW_CHARS = 240


def _summarize(value: Any) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) > _RESULT_PREVIEW_CHARS:
        return s[:_RESULT_PREVIEW_CHARS] + "…"
    return s


def _truncate_for_model(value: Any, max_chars: int) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) > max_chars:
        return s[:max_chars] + '... [truncated]"'
    return s


def _tool_call_fingerprint(name: str, args: Any) -> str:
    try:
        return name + "::" + json.dumps(args, sort_keys=True, default=str)
    except Exception:
        return name + "::" + str(args)


async def _emit(on_event: Optional[EventCallback], event: Dict[str, Any]) -> None:
    if on_event is None:
        return
    try:
        await on_event(event)
    except Exception as e:
        logger.warning(f"[agent] event callback failed: {e}")


async def _chat(
    convo: List[Dict[str, Any]],
    system: Optional[str],
    tools_payload: Optional[List[Dict[str, Any]]],
    model: Optional[str],
    on_event: Optional[EventCallback],
) -> Dict[str, Any]:
    """One LLM call. With an event callback, stream and forward content
    tokens as they arrive; otherwise use the blocking call."""
    if on_event is None:
        return await chat_ollama(
            messages=convo, system=system, tools=tools_payload, model=model,
        )

    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    ai_available = False
    async for chunk in chat_ollama_stream(
        messages=convo, system=system, tools=tools_payload, model=model,
    ):
        if chunk["type"] == "token":
            text_parts.append(chunk["text"])
            await _emit(on_event, {"type": "token", "text": chunk["text"]})
        elif chunk["type"] == "tool_calls":
            tool_calls.extend(chunk["tool_calls"])
        elif chunk["type"] == "done":
            ai_available = chunk["ai_available"]
    return {
        "ai_available": ai_available,
        "text": "".join(text_parts),
        "tool_calls": tool_calls,
        "raw": None,
    }


def _parse_call(call: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    fn = (call.get("function") or {})
    name = fn.get("name") or ""
    raw_args = fn.get("arguments")
    # Ollama sometimes returns arguments as JSON string, sometimes dict.
    if isinstance(raw_args, str):
        try:
            args: Dict[str, Any] = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = dict(raw_args or {})
    return name, args


async def run_agent(
    messages: List[Dict[str, Any]],
    registry: ToolRegistry,
    system: Optional[str] = None,
    max_iters: Optional[int] = None,
    model: Optional[str] = None,
    on_event: Optional[EventCallback] = None,
) -> AgentResult:
    """Run the tool-use loop until the model returns a final reply.

    Args:
        messages: Chat history (role/content dicts). The harness appends
            assistant + tool messages as the loop progresses but does NOT
            mutate the caller's list.
        registry: Tool registry providing schemas + handlers.
        system: System prompt prepended on every Ollama call.
        max_iters: Override the configured max-iterations guard.
        model: Override the chat model (else state.OLLAMA_CHAT_MODEL).
        on_event: Optional async callback receiving live progress events
            ({"type": "token"|"tool_call"|"tool_result"|"tool_error", ...}).
            When set, LLM calls stream and content tokens are forwarded.
    """
    limit = max_iters or config.ADVISOR_AGENT_MAX_ITERS
    convo: List[Dict[str, Any]] = list(messages)
    trajectory: List[TrajectoryEvent] = []
    tools_payload = registry.openai_tools()

    seen_fingerprints: set[str] = set()
    transient_retried: set[str] = set()
    last_reply: Optional[str] = None
    terminated = "ok"

    for iteration in range(1, limit + 1):
        result = await _chat(convo, system, tools_payload, model, on_event)

        if not result["ai_available"]:
            terminated = "ollama_unavailable"
            break

        tool_calls = result.get("tool_calls") or []
        reply_text = (result.get("text") or "").strip()

        # No tool calls -> model produced a final reply (or an empty string).
        if not tool_calls:
            if not reply_text:
                terminated = "empty_reply"
                break
            last_reply = reply_text
            trajectory.append(
                TrajectoryEvent(iteration=iteration, kind="final", result_summary=_summarize(reply_text))
            )
            terminated = "ok"
            break

        # Record the assistant turn that issued the tool calls so the next
        # /api/chat sees a consistent transcript.
        convo.append({
            "role": "assistant",
            "content": reply_text,
            "tool_calls": tool_calls,
        })

        # Phase 1 — parse, guard, and validate every call in the batch.
        # ``batch`` collects the executable ones so independent calls can
        # run concurrently in phase 2.
        batch: List[tuple[str, str, Tool, Any]] = []  # (name, fp, tool, validated)
        for call in tool_calls:
            name, args = _parse_call(call)

            trajectory.append(
                TrajectoryEvent(
                    iteration=iteration,
                    kind="tool_call",
                    tool_name=name,
                    arguments=args,
                )
            )
            await _emit(on_event, {"type": "tool_call", "name": name, "arguments": args})

            fingerprint = _tool_call_fingerprint(name, args)
            if fingerprint in seen_fingerprints:
                trajectory.append(
                    TrajectoryEvent(
                        iteration=iteration,
                        kind="terminated",
                        tool_name=name,
                        terminated_reason="repeated_tool_call",
                    )
                )
                terminated = "repeated_tool_call"
                convo.append({
                    "role": "tool",
                    "name": name,
                    "content": "Error: you already called this tool with these "
                               "arguments in this conversation. Use the previous "
                               "result or answer the user directly.",
                })
                break
            seen_fingerprints.add(fingerprint)

            tool = registry.get(name)
            if tool is None:
                msg = (
                    f"Error: tool '{name}' does not exist. Available tools: "
                    f"{', '.join(registry.names())}. Either call one of those "
                    "or answer the user without tools."
                )
                trajectory.append(
                    TrajectoryEvent(iteration=iteration, kind="tool_error", tool_name=name, error="unknown_tool")
                )
                await _emit(on_event, {"type": "tool_error", "name": name, "error": "unknown_tool"})
                convo.append({"role": "tool", "name": name, "content": msg})
                continue

            try:
                validated = tool.args_model.model_validate(args)
            except ValidationError as ve:
                err_msg = (
                    f"Error: arguments for tool '{name}' are invalid: "
                    f"{ve.errors()}. Re-emit the tool call with corrected JSON."
                )
                trajectory.append(
                    TrajectoryEvent(
                        iteration=iteration,
                        kind="tool_error",
                        tool_name=name,
                        error=str(ve.errors()),
                    )
                )
                await _emit(on_event, {"type": "tool_error", "name": name, "error": "invalid_arguments"})
                convo.append({"role": "tool", "name": name, "content": err_msg})
                continue

            batch.append((name, fingerprint, tool, validated))

        # Phase 2 — execute the validated calls concurrently. Results are
        # appended to the transcript in call order regardless of which
        # handler finished first.
        if batch:
            results = await asyncio.gather(
                *(tool.handler(validated) for (_, _, tool, validated) in batch),
                return_exceptions=True,
            )
            for (name, fingerprint, tool, _validated), result_value in zip(batch, results):
                if isinstance(result_value, TransientToolError):
                    if fingerprint not in transient_retried:
                        transient_retried.add(fingerprint)
                        seen_fingerprints.discard(fingerprint)
                        hint = "This looks temporary — you may retry this exact call once."
                    else:
                        hint = "Still failing — answer without this tool and say the lookup is flaky right now."
                    logger.warning(f"[agent] tool {name} transient error: {result_value}")
                    trajectory.append(
                        TrajectoryEvent(
                            iteration=iteration,
                            kind="tool_error",
                            tool_name=name,
                            error=str(result_value),
                        )
                    )
                    await _emit(on_event, {"type": "tool_error", "name": name, "error": str(result_value)})
                    convo.append({
                        "role": "tool",
                        "name": name,
                        "content": f"Error executing tool '{name}': {result_value}. {hint}",
                    })
                elif isinstance(result_value, BaseException):
                    logger.warning(f"[agent] tool {name} raised: {result_value}")
                    trajectory.append(
                        TrajectoryEvent(
                            iteration=iteration,
                            kind="tool_error",
                            tool_name=name,
                            error=str(result_value),
                        )
                    )
                    await _emit(on_event, {"type": "tool_error", "name": name, "error": str(result_value)})
                    convo.append({
                        "role": "tool",
                        "name": name,
                        "content": f"Error executing tool '{name}': {result_value}",
                    })
                else:
                    payload = _truncate_for_model(result_value, tool.result_max_chars)
                    trajectory.append(
                        TrajectoryEvent(
                            iteration=iteration,
                            kind="tool_result",
                            tool_name=name,
                            result_summary=_summarize(result_value),
                        )
                    )
                    await _emit(
                        on_event,
                        {"type": "tool_result", "name": name, "summary": _summarize(result_value)},
                    )
                    convo.append({"role": "tool", "name": name, "content": payload})

        if terminated == "repeated_tool_call":
            break
    else:
        terminated = "max_iterations"
        trajectory.append(
            TrajectoryEvent(
                iteration=limit,
                kind="terminated",
                terminated_reason="max_iterations",
            )
        )

    # Guard trips (repeated call, max iterations) can leave the user with no
    # reply even though tool results are sitting in the transcript. One final
    # tool-free call forces the model to answer from what it already gathered.
    if last_reply is None and terminated in ("repeated_tool_call", "max_iterations"):
        convo.append({
            "role": "tool",
            "name": "system",
            "content": "Answer the user now using the tool results above. "
                       "Do not request any more tools.",
        })
        final = await _chat(convo, system, None, model, on_event)
        if final["ai_available"] and (final.get("text") or "").strip():
            last_reply = final["text"].strip()
            trajectory.append(
                TrajectoryEvent(
                    iteration=limit,
                    kind="final",
                    result_summary=_summarize(last_reply),
                )
            )

    return AgentResult(
        reply=last_reply,
        trajectory=trajectory,
        terminated_reason=terminated,
        iterations=min(limit, max(1, len(set(e.iteration for e in trajectory)) if trajectory else 1)),
    )
