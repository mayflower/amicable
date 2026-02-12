from __future__ import annotations

import asyncio

from src.agent_core import Agent, MessageType, _safe_trace_payload


class _FakeController:
    def __init__(self) -> None:
        self.received_input = None

    async def astream_events(self, input_value, **_kwargs):
        self.received_input = input_value
        yield {
            "event": "on_chain_end",
            "name": "controller",
            "data": {
                "output": {
                    "messages": [{"role": "assistant", "content": "done"}],
                }
            },
        }


def test_send_feedback_accepts_multimodal_user_content_blocks():
    agent = Agent()
    controller = _FakeController()

    session_id = "sess-multimodal"
    agent.session_data[session_id] = {"exists": True}
    agent._deep_agent = object()
    agent._deep_controller = controller
    agent._session_manager = object()

    async def _run():
        out = []
        async for msg in agent.send_feedback(
            session_id=session_id,
            feedback="runtime error detected",
            user_content_blocks=[
                {"type": "text", "text": "runtime error detected"},
                {
                    "type": "image",
                    "base64": "abcd",
                    "mime_type": "image/jpeg",
                },
            ],
        ):
            out.append(msg)
        return out

    msgs = asyncio.run(_run())
    kinds = [m.get("type") for m in msgs]
    assert MessageType.UPDATE_IN_PROGRESS.value in kinds
    assert MessageType.AGENT_FINAL.value in kinds
    assert controller.received_input is not None
    first = controller.received_input["messages"][0]
    assert first[0] == "user"
    assert isinstance(first[1], list)
    assert first[1][1]["type"] == "image"


def test_safe_trace_payload_redacts_base64_fields():
    payload = _safe_trace_payload(
        {
            "type": "image",
            "base64": "abcdefghijklmnopqrstuvwxyz",
            "nested": {"image_base64": "123456789"},
        }
    )
    assert payload["base64"].startswith("<redacted:")
    assert payload["nested"]["image_base64"].startswith("<redacted:")
