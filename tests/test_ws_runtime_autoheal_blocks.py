from __future__ import annotations

import pytest

pytest.importorskip("dotenv")

from src.runtimes.ws_server import _runtime_autoheal_user_content_blocks


def test_runtime_autoheal_blocks_include_image_when_available():
    blocks = _runtime_autoheal_user_content_blocks(
        "Fix this error",
        {"ok": True, "image_base64": "abcd", "mime_type": "image/jpeg"},
    )
    assert blocks is not None
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "image"
    assert blocks[1]["base64"] == "abcd"


def test_runtime_autoheal_blocks_return_none_without_image():
    assert _runtime_autoheal_user_content_blocks("Fix this error", None) is None
    assert (
        _runtime_autoheal_user_content_blocks(
            "Fix this error", {"ok": False, "error": "failed"}
        )
        is None
    )
