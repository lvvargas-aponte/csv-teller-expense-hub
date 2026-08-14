"""Rolling conversation compaction — in-memory stores, mocked Ollama."""
import asyncio
from unittest.mock import AsyncMock, patch

import state
import conversation_compaction
from conversation_compaction import (
    COMPACT_BATCH_SIZE,
    maybe_compact,
    render_summary_block,
)


def _run(coro):
    return asyncio.run(coro)


def _mock_ask(text="- talked about NVDA\n- user is saving for a house"):
    return patch(
        "conversation_compaction.ask_ollama",
        new=AsyncMock(return_value={"ai_available": True, "text": text, "raw": None}),
    )


def _seed_conv(conv_id: str, n_messages: int, summary=None, summary_upto=0):
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}", "ts": "t"}
        for i in range(n_messages)
    ]
    conv = {
        "conversation_id": conv_id,
        "created": "t", "updated": "t",
        "messages": messages,
    }
    if summary is not None:
        conv["summary"] = summary
        conv["summary_upto"] = summary_upto
    state.conversations[conv_id] = conv
    return conv


class TestMaybeCompact:
    def test_short_conversation_is_left_alone(self):
        _seed_conv("conv_short", state.ADVISOR_MAX_HISTORY)
        with _mock_ask() as ask:
            assert _run(maybe_compact("conv_short")) is False
        ask.assert_not_awaited()

    def test_compacts_once_batch_of_aged_messages_accumulates(self):
        n = state.ADVISOR_MAX_HISTORY + COMPACT_BATCH_SIZE
        _seed_conv("conv_long", n)
        with _mock_ask() as ask:
            assert _run(maybe_compact("conv_long")) is True
        ask.assert_awaited_once()
        conv = state.conversations["conv_long"]
        assert "NVDA" in conv["summary"]
        assert conv["summary_upto"] == COMPACT_BATCH_SIZE

    def test_short_circuits_until_next_batch(self):
        n = state.ADVISOR_MAX_HISTORY + COMPACT_BATCH_SIZE
        _seed_conv("conv_done", n, summary="- old summary", summary_upto=COMPACT_BATCH_SIZE)
        with _mock_ask() as ask:
            assert _run(maybe_compact("conv_done")) is False
        ask.assert_not_awaited()

    def test_rolls_existing_summary_forward(self):
        n = state.ADVISOR_MAX_HISTORY + 2 * COMPACT_BATCH_SIZE
        _seed_conv("conv_roll", n, summary="- earlier stuff", summary_upto=COMPACT_BATCH_SIZE)
        captured = {}

        async def capture(prompt, system=None, **_kw):
            captured["prompt"] = prompt
            return {"ai_available": True, "text": "- merged summary", "raw": None}

        with patch("conversation_compaction.ask_ollama", new=capture):
            assert _run(maybe_compact("conv_roll")) is True
        # The existing summary and only the NEWLY aged slice go to the LLM.
        assert "- earlier stuff" in captured["prompt"]
        assert f"msg {COMPACT_BATCH_SIZE}" in captured["prompt"]
        assert "msg 0" not in captured["prompt"].split("=== Messages")[1]
        conv = state.conversations["conv_roll"]
        assert conv["summary"] == "- merged summary"
        assert conv["summary_upto"] == 2 * COMPACT_BATCH_SIZE

    def test_ollama_down_leaves_summary_untouched(self):
        n = state.ADVISOR_MAX_HISTORY + COMPACT_BATCH_SIZE
        _seed_conv("conv_down", n)
        with patch(
            "conversation_compaction.ask_ollama",
            new=AsyncMock(return_value={"ai_available": False, "text": None, "raw": None}),
        ):
            assert _run(maybe_compact("conv_down")) is False
        assert "summary" not in state.conversations["conv_down"]

    def test_unknown_conversation_is_noop(self):
        assert _run(maybe_compact("conv_nope")) is False


class TestRenderSummaryBlock:
    def test_empty_when_no_summary(self):
        assert render_summary_block({"messages": []}) == ""

    def test_renders_block(self):
        block = render_summary_block({"summary": "- bought VOO"})
        assert "EARLIER IN THIS CONVERSATION" in block
        assert "- bought VOO" in block
