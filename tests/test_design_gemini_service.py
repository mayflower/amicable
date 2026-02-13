from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("httpx")

from src.design import gemini_design


def _set_env(monkeypatch) -> None:
    monkeypatch.setenv("AMICABLE_DESIGN_GEMINI_API_KEY", "k")
    monkeypatch.setenv("AMICABLE_DESIGN_GEMINI_TEXT_MODEL", "text-model")
    monkeypatch.setenv("AMICABLE_DESIGN_GEMINI_IMAGE_MODEL", "image-model")


def test_validate_design_config_missing(monkeypatch) -> None:
    monkeypatch.delenv("AMICABLE_DESIGN_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AMICABLE_DESIGN_GEMINI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("AMICABLE_DESIGN_GEMINI_IMAGE_MODEL", raising=False)
    err = gemini_design.validate_design_config()
    assert isinstance(err, str)


def test_generate_design_approaches_falls_back_when_json_is_malformed(monkeypatch) -> None:
    _set_env(monkeypatch)

    async def _fake_post_generate_content(**kwargs):
        model = kwargs["model"]
        if model == "text-model":
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "not-json"},
                            ]
                        }
                    }
                ]
            }
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": "abcd",
                                }
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(gemini_design, "_post_generate_content", _fake_post_generate_content)

    out = asyncio.run(
        gemini_design.generate_design_approaches(
            screenshot_base64="abcd",
            screenshot_mime_type="image/png",
            viewport_width=1280,
            viewport_height=800,
            app_context="todo app",
            instruction="make it cleaner",
        )
    )
    assert len(out) == 2
    assert out[0].approach_id == "approach_1"
    assert out[1].approach_id == "approach_2"
    assert out[0].image_base64 == "abcd"


def test_generate_design_approaches_maps_provider_errors(monkeypatch) -> None:
    _set_env(monkeypatch)

    async def _boom(**_kwargs):
        raise gemini_design.DesignGenerationError("provider failed")

    monkeypatch.setattr(gemini_design, "_post_generate_content", _boom)

    with pytest.raises(gemini_design.DesignGenerationError):
        asyncio.run(
            gemini_design.generate_design_approaches(
                screenshot_base64="abcd",
                screenshot_mime_type="image/png",
                viewport_width=1280,
                viewport_height=800,
            )
        )
