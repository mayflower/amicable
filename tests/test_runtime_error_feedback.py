from __future__ import annotations

from src.runtime_error_feedback import build_runtime_error_feedback_prompt


def test_console_error_prompt_includes_args_preview_and_hint():
    prompt = build_runtime_error_feedback_prompt(
        err={
            "kind": "console_error",
            "message": "boom",
            "source": "console",
            "level": "error",
            "args_preview": '{"foo":"bar"}',
        }
    )
    assert "Kind: console_error" in prompt
    assert "Console args preview" in prompt
    assert "Fix the underlying code path" in prompt


def test_runtime_bridge_missing_prompt_includes_restore_hint():
    prompt = build_runtime_error_feedback_prompt(
        err={
            "kind": "runtime_bridge_missing",
            "message": "probe failed",
            "source": "bridge",
        }
    )
    assert "Kind: runtime_bridge_missing" in prompt
    assert "/amicable-runtime.js" in prompt


def test_graphql_error_prompt_keeps_existing_hint_and_preview_logs():
    prompt = build_runtime_error_feedback_prompt(
        err={
            "kind": "graphql_error",
            "message": "field 'todos' not found in type: 'query_root'",
        },
        preview_logs="line1\nline2",
    )
    assert "Hasura table/field is missing or not tracked" in prompt
    assert "Preview logs (tail):" in prompt
