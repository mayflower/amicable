from __future__ import annotations

import pytest

from src.deepagents_backend.preview_screenshot import (
    build_preview_target_url,
    capture_preview_screenshot,
    normalize_preview_path,
)


def test_normalize_preview_path_normalizes_relative_input():
    assert normalize_preview_path("dashboard") == "/dashboard"
    assert normalize_preview_path("/dashboard/../settings") == "/settings"


def test_normalize_preview_path_rejects_absolute_urls():
    with pytest.raises(ValueError):
        normalize_preview_path("https://example.com/")


def test_capture_preview_screenshot_falls_back_to_second_url():
    calls: list[str] = []

    def fake_capture(**kwargs):
        target = kwargs["target_url"]
        calls.append(target)
        if "internal.invalid" in target:
            raise RuntimeError("boom")
        return b"jpg-bytes", 1234, 567

    result = capture_preview_screenshot(
        source_urls=["http://internal.invalid:3000/", "https://preview.example.com/"],
        path="/",
        capture_fn=fake_capture,
    )

    assert result.ok is True
    assert result.target_url == "https://preview.example.com/"
    assert result.width == 1234
    assert result.height == 567
    assert len(calls) == 2


def test_build_preview_target_url_keeps_query_and_fragment():
    out = build_preview_target_url(
        "https://preview.example.com/",
        path="/dashboard?tab=ui#pane",
    )
    assert out == "https://preview.example.com/dashboard?tab=ui#pane"
