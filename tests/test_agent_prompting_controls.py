from __future__ import annotations

from src.agent_core import Agent, normalize_permission_mode, normalize_thinking_level


def test_normalize_permission_mode() -> None:
    assert normalize_permission_mode("default") == "default"
    assert normalize_permission_mode("accept_edits") == "accept_edits"
    assert normalize_permission_mode("bypass") == "bypass"
    assert normalize_permission_mode("invalid") == "default"


def test_normalize_thinking_level() -> None:
    assert normalize_thinking_level("none") == "none"
    assert normalize_thinking_level("think") == "think"
    assert normalize_thinking_level("think_hard") == "think_hard"
    assert normalize_thinking_level("ultrathink") == "ultrathink"
    assert normalize_thinking_level("invalid") == "none"


def test_agent_set_session_controls_persists_values() -> None:
    agent = Agent()
    session_id = "sess-controls"

    agent.set_session_controls(
        session_id,
        permission_mode="accept_edits",
        thinking_level="think_hard",
    )

    assert agent.session_data[session_id]["permission_mode"] == "accept_edits"
    assert agent.session_data[session_id]["thinking_level"] == "think_hard"


def test_agent_compaction_reduces_history(monkeypatch) -> None:
    monkeypatch.setenv("AMICABLE_COMPACTION_TRIGGER_MESSAGES", "5")
    monkeypatch.setenv("DEEPAGENTS_SUMMARIZATION_KEEP_MESSAGES", "2")

    agent = Agent()
    session_id = "sess-compaction"
    agent.session_data[session_id] = {
        "_conversation_history": [
            {"role": "user", "text": "one"},
            {"role": "assistant", "text": "two"},
            {"role": "user", "text": "three"},
            {"role": "assistant", "text": "four"},
            {"role": "user", "text": "five"},
            {"role": "assistant", "text": "six"},
        ],
        "_conversation_summary": "",
        "_last_qa_failure": "build failed",
    }

    compacted, meta = agent._maybe_compact_user_text(
        session_id=session_id,
        user_text="new request",
    )

    assert meta is not None
    assert "Compacted conversation context" in compacted
    assert len(agent.session_data[session_id]["_conversation_history"]) == 2
