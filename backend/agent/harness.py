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

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

import config
from llm_client import chat_ollama

from agent.schemas import AgentResult, TrajectoryEvent
from agent.tools import ToolRegistry

logger = logging.getLogger(__name__)

_RESULT_PREVIEW_CHARS = 240
_TOOL_RESULT_MAX_CHARS = 4000  # cap what we feed back to the model per call


def _summarize(value: Any) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) > _RESULT_PREVIEW_CHARS:
        return s[:_RESULT_PREVIEW_CHARS] + "…"
    return s


def _truncate_for_model(value: Any) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) > _TOOL_RESULT_MAX_CHARS:
        return s[:_TOOL_RESULT_MAX_CHARS] + '... [truncated]"'
    return s


def _tool_call_fingerprint(name: str, args: Any) -> str:
    try:
        return name + "::" + json.dumps(args, sort_keys=True, default=str)
    except Exception:
        return name + "::" + str(args)


async def run_agent(
    messages: List[Dict[str, Any]],
    registry: ToolRegistry,
    system: Optional[str] = None,
    max_iters: Optional[int] = None,
    model: Optional[str] = None,
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
    """
    limit = max_iters or config.ADVISOR_AGENT_MAX_ITERS
    convo: List[Dict[str, Any]] = list(messages)
    trajectory: List[TrajectoryEvent] = []
    tools_payload = registry.openai_tools()

    seen_fingerprints: set[str] = set()
    last_reply: Optional[str] = None
    terminated = "ok"

    for iteration in range(1, limit + 1):
        result = await chat_ollama(
            messages=convo,
            system=system,
            tools=tools_payload,
            model=model,
        )

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

        for call in tool_calls:
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

            trajectory.append(
                TrajectoryEvent(
                    iteration=iteration,
                    kind="tool_call",
                    tool_name=name,
                    arguments=args,
                )
            )

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
                convo.append({"role": "tool", "name": name, "content": err_msg})
                continue

            try:
                result_value = await tool.handler(validated)
            except Exception as e:
                logger.warning(f"[agent] tool {name} raised: {e}")
                trajectory.append(
                    TrajectoryEvent(
                        iteration=iteration,
                        kind="tool_error",
                        tool_name=name,
                        error=str(e),
                    )
                )
                convo.append({
                    "role": "tool",
                    "name": name,
                    "content": f"Error executing tool '{name}': {e}",
                })
                continue

            payload = _truncate_for_model(result_value)
            trajectory.append(
                TrajectoryEvent(
                    iteration=iteration,
                    kind="tool_result",
                    tool_name=name,
                    result_summary=_summarize(result_value),
                )
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

    return AgentResult(
        reply=last_reply,
        trajectory=trajectory,
        terminated_reason=terminated,
        iterations=min(limit, max(1, len(set(e.iteration for e in trajectory)) if trajectory else 1)),
    )
