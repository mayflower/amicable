from __future__ import annotations

from src.deepagents_backend.screenshot_tools import _screenshot_tool_result


def test_screenshot_tool_result_includes_image_block_on_success():
    def fake_capture(**_kwargs):
        return {
            "ok": True,
            "image_base64": "abcd",
            "mime_type": "image/jpeg",
            "target_url": "https://preview.example.com/",
            "width": 100,
            "height": 200,
            "error": None,
        }

    content, artifact = _screenshot_tool_result(
        session_id="sess-1",
        path="/",
        full_page=True,
        timeout_s=10,
        capture_fn=fake_capture,
    )

    assert len(content) == 2
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image"
    assert content[1]["base64"] == "abcd"
    assert "image_base64" not in artifact
    assert artifact["ok"] is True


def test_screenshot_tool_result_returns_text_only_on_failure():
    def fake_capture(**_kwargs):
        return {
            "ok": False,
            "error": "capture failed",
            "target_url": None,
            "mime_type": "image/jpeg",
        }

    content, artifact = _screenshot_tool_result(
        session_id="sess-1",
        path="/",
        full_page=True,
        timeout_s=10,
        capture_fn=fake_capture,
    )

    assert len(content) == 1
    assert content[0]["type"] == "text"
    assert "capture failed" in content[0]["text"]
    assert artifact["ok"] is False
