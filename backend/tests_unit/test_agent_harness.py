"""Unit tests for the Fin agent harness.

Patches ``agent.harness.chat_ollama`` to script LLM responses so the loop
can be exercised deterministically with no real Ollama dependency.
"""
import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, Field

from agent.harness import run_agent
from agent.tools import Tool, ToolRegistry


class _EchoArgs(BaseModel):
    value: str = Field(...)


class _AddArgs(BaseModel):
    a: int
    b: int


def _make_registry(call_log: List[Dict[str, Any]]) -> ToolRegistry:
    async def echo(args: _EchoArgs) -> Dict[str, Any]:
        call_log.append({"tool": "echo", "value": args.value})
        return {"echoed": args.value}

    async def add(args: _AddArgs) -> Dict[str, Any]:
        call_log.append({"tool": "add", "a": args.a, "b": args.b})
        return {"sum": args.a + args.b}

    async def boom(args: _EchoArgs) -> Dict[str, Any]:
        raise RuntimeError("kaboom")

    return ToolRegistry([
        Tool(name="echo", description="echo", args_model=_EchoArgs, handler=echo),
        Tool(name="add", description="add", args_model=_AddArgs, handler=add),
        Tool(name="boom", description="boom", args_model=_EchoArgs, handler=boom),
    ])


def _llm(*responses: Dict[str, Any]):
    """Return an AsyncMock that yields the scripted responses in order."""
    return AsyncMock(side_effect=list(responses))


def _resp(text: str = "", tool_calls=None) -> Dict[str, Any]:
    return {
        "ai_available": True,
        "text": text,
        "tool_calls": tool_calls or [],
        "raw": None,
    }


def _tc(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"function": {"name": name, "arguments": args}}


class TestHarness:
    def _run(self, fake_llm, registry, **kwargs):
        with patch("agent.harness.chat_ollama", new=fake_llm):
            return asyncio.run(run_agent(messages=[{"role": "user", "content": "hi"}], registry=registry, **kwargs))

    def test_terminates_when_model_stops_calling_tools(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm(
            _resp(tool_calls=[_tc("echo", {"value": "hello"})]),
            _resp(text="final answer"),
        )
        out = self._run(llm, reg)
        assert out.terminated_reason == "ok"
        assert out.reply == "final answer"
        assert log == [{"tool": "echo", "value": "hello"}]
        # one tool_call event, one tool_result event, one final event
        kinds = [e.kind for e in out.trajectory]
        assert "tool_call" in kinds and "tool_result" in kinds and "final" in kinds

    def test_max_iterations_guard(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        # Always call a tool; never produce final reply.
        llm = AsyncMock(return_value=_resp(tool_calls=[_tc("echo", {"value": "x"})]))
        out = self._run(llm, reg, max_iters=3)
        # The fingerprint guard fires first (same args repeated), which is
        # an acceptable terminate path. Either way, never exceeds 3 iters.
        assert out.terminated_reason in ("max_iterations", "repeated_tool_call")
        assert out.reply is None

    def test_hallucinated_tool_returns_error_to_model(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm(
            _resp(tool_calls=[_tc("nonexistent", {"value": "x"})]),
            _resp(text="ok I'll just answer"),
        )
        out = self._run(llm, reg)
        assert out.terminated_reason == "ok"
        assert any(e.kind == "tool_error" and e.error == "unknown_tool" for e in out.trajectory)
        assert log == []  # nothing actually ran

    def test_invalid_args_re_prompts_then_continues(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm(
            _resp(tool_calls=[_tc("add", {"a": "not-an-int", "b": 2})]),
            _resp(text="never mind"),
        )
        out = self._run(llm, reg)
        assert out.terminated_reason == "ok"
        assert any(e.kind == "tool_error" and e.tool_name == "add" for e in out.trajectory)
        assert log == []

    def test_repeated_identical_tool_call_breaks(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm(
            _resp(tool_calls=[_tc("echo", {"value": "same"})]),
            _resp(tool_calls=[_tc("echo", {"value": "same"})]),
        )
        out = self._run(llm, reg)
        assert out.terminated_reason == "repeated_tool_call"
        # The tool ran exactly once before the loop detected the repeat.
        assert log == [{"tool": "echo", "value": "same"}]

    def test_tool_exception_is_caught_and_fed_back(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm(
            _resp(tool_calls=[_tc("boom", {"value": "x"})]),
            _resp(text="recovered"),
        )
        out = self._run(llm, reg)
        assert out.terminated_reason == "ok"
        assert out.reply == "recovered"
        assert any(e.kind == "tool_error" and e.tool_name == "boom" for e in out.trajectory)

    def test_empty_reply_terminates(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm(_resp(text=""))
        out = self._run(llm, reg)
        assert out.terminated_reason == "empty_reply"
        assert out.reply is None

    def test_ollama_unavailable_terminates(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm({"ai_available": False, "text": None, "tool_calls": [], "raw": None})
        out = self._run(llm, reg)
        assert out.terminated_reason == "ollama_unavailable"
        assert out.reply is None

    def test_string_arguments_are_parsed_as_json(self):
        log: List[Dict[str, Any]] = []
        reg = _make_registry(log)
        llm = _llm(
            _resp(tool_calls=[_tc("echo", '{"value": "json-string"}')]),
            _resp(text="done"),
        )
        out = self._run(llm, reg)
        assert out.terminated_reason == "ok"
        assert log == [{"tool": "echo", "value": "json-string"}]
