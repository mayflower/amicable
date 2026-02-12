from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def _thread_id_from_config() -> str | None:
    try:
        from langgraph.config import get_config as _lg_get_config

        config = _lg_get_config()
    except Exception:
        return None

    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable") or {}
    if not isinstance(configurable, dict):
        return None
    thread_id = configurable.get("thread_id")
    return thread_id if isinstance(thread_id, str) and thread_id else None


def _screenshot_tool_result(
    *,
    session_id: str | None,
    path: str,
    full_page: bool,
    timeout_s: int,
    capture_fn: Callable[..., dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not session_id:
        artifact = {
            "ok": False,
            "error": "missing thread_id in runtime config",
        }
        return (
            [
                {
                    "type": "text",
                    "text": "Could not capture preview screenshot: missing session context.",
                }
            ],
            artifact,
        )

    try:
        result = capture_fn(
            session_id=session_id,
            path=path,
            full_page=full_page,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        artifact = {
            "ok": False,
            "error": str(exc),
        }
        return (
            [
                {
                    "type": "text",
                    "text": f"Could not capture preview screenshot: {exc}",
                }
            ],
            artifact,
        )

    image_b64 = result.get("image_base64")
    artifact = {k: v for k, v in result.items() if k != "image_base64"}
    if result.get("ok") and isinstance(image_b64, str) and image_b64:
        target_url = str(result.get("target_url") or "")
        text = (
            f"Captured preview screenshot from {target_url}."
            if target_url
            else "Captured preview screenshot."
        )
        content = [
            {"type": "text", "text": text},
            {
                "type": "image",
                "base64": image_b64,
                "mime_type": str(result.get("mime_type") or "image/jpeg"),
            },
        ]
        return content, artifact

    err = str(result.get("error") or "unknown error")
    return (
        [{"type": "text", "text": f"Could not capture preview screenshot: {err}"}],
        artifact,
    )


def get_screenshot_tools(
    *, capture_fn: Callable[..., dict[str, Any]]
) -> list[Any]:
    from langchain_core.tools import tool  # type: ignore

    @tool(response_format="content_and_artifact")
    def capture_preview_screenshot(
        path: str = "/",
        full_page: bool = True,
        timeout_s: int = 15,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Capture a screenshot of the running preview for visual debugging.

        Args:
            path: Optional preview path (for example `/`, `/dashboard`, `/settings?tab=profile`).
            full_page: If true, capture the full scrollable page; otherwise capture viewport only.
            timeout_s: Navigation timeout in seconds.
        """
        return _screenshot_tool_result(
            session_id=_thread_id_from_config(),
            path=path,
            full_page=bool(full_page),
            timeout_s=max(1, int(timeout_s)),
            capture_fn=capture_fn,
        )

    return [capture_preview_screenshot]
