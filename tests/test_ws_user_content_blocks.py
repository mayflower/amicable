from __future__ import annotations

import pytest

pytest.importorskip("dotenv")
pytest.importorskip("fastapi")

from src.runtimes.ws_server import _sanitize_user_content_blocks


def test_sanitize_user_content_blocks_accepts_image_block():
    blocks, err = _sanitize_user_content_blocks(
        [
            {
                "type": "image",
                "base64": "abcd",
                "mime_type": "image/png",
            }
        ]
    )
    assert err is None
    assert blocks is not None
    assert blocks[0]["type"] == "image"


def test_sanitize_user_content_blocks_rejects_invalid_mime_type():
    blocks, err = _sanitize_user_content_blocks(
        [
            {
                "type": "image",
                "base64": "abcd",
                "mime_type": "application/pdf",
            }
        ]
    )
    assert blocks is None
    assert isinstance(err, str)
    assert "mime_type" in err


def test_sanitize_user_content_blocks_rejects_oversized_base64(monkeypatch):
    monkeypatch.setenv("AMICABLE_USER_IMAGE_MAX_BASE64_CHARS", "1500")
    blocks, err = _sanitize_user_content_blocks(
        [
            {
                "type": "image",
                "base64": "x" * 2000,
                "mime_type": "image/png",
            }
        ]
    )
    assert blocks is None
    assert isinstance(err, str)
    assert "too large" in err


def test_sanitize_user_content_blocks_rejects_too_many_images(monkeypatch):
    monkeypatch.setenv("AMICABLE_USER_IMAGE_MAX_BLOCKS", "1")
    blocks, err = _sanitize_user_content_blocks(
        [
            {"type": "image", "base64": "a", "mime_type": "image/png"},
            {"type": "image", "base64": "b", "mime_type": "image/jpeg"},
        ]
    )
    assert blocks is None
    assert isinstance(err, str)
    assert "too many images" in err
