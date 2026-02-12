from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit, urlunsplit

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class PreviewScreenshotResult:
    ok: bool
    path: str
    target_url: str | None
    source_url: str | None
    mime_type: str
    image_bytes: bytes | None
    width: int | None
    height: int | None
    error: str | None
    attempted_urls: list[str]


def normalize_preview_path(path: str | None) -> str:
    raw = (path or "/").strip()
    if not raw:
        raw = "/"

    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        raise ValueError("path must be relative to the preview root")

    normalized_path = posixpath.normpath("/" + parsed.path.lstrip("/"))
    if normalized_path.startswith("/.."):
        raise ValueError("path must not traverse above preview root")

    if normalized_path == "/.":
        normalized_path = "/"

    return urlunsplit(("", "", normalized_path, parsed.query, parsed.fragment))


def build_preview_target_url(base_url: str, *, path: str = "/") -> str:
    base = (base_url or "").strip()
    if not base:
        raise ValueError("base_url is required")

    parsed_base = urlsplit(base)
    if not parsed_base.scheme or not parsed_base.netloc:
        raise ValueError("base_url must be an absolute URL")

    normalized_path = normalize_preview_path(path)
    base_with_slash = base if base.endswith("/") else (base + "/")
    return urljoin(base_with_slash, normalized_path)


def _capture_single_url(
    *,
    target_url: str,
    timeout_ms: int,
    full_page: bool,
    viewport_width: int,
    viewport_height: int,
) -> tuple[bytes, int | None, int | None]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                context = browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height}
                )
                page = context.new_page()
                # `networkidle` is unreliable for dev servers (for example Vite HMR keeps websockets open).
                page.goto(target_url, wait_until="load", timeout=timeout_ms)
                page.wait_for_timeout(250)
                image_bytes = page.screenshot(
                    type="jpeg",
                    quality=70,
                    full_page=full_page,
                    animations="disabled",
                )
                dims = page.evaluate(
                    """() => ({
                      width: Math.max(document.documentElement.scrollWidth || 0, window.innerWidth || 0),
                      height: Math.max(document.documentElement.scrollHeight || 0, window.innerHeight || 0)
                    })"""
                )
                width = dims.get("width") if isinstance(dims, dict) else None
                height = dims.get("height") if isinstance(dims, dict) else None
                return image_bytes, int(width or 0) or None, int(height or 0) or None
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(f"preview navigation timed out for {target_url}") from exc


def capture_preview_screenshot(
    *,
    source_urls: list[str],
    path: str = "/",
    timeout_ms: int = 15_000,
    full_page: bool = True,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    capture_fn: Callable[..., tuple[bytes, int | None, int | None]] | None = None,
) -> PreviewScreenshotResult:
    normalized_path = normalize_preview_path(path)

    attempted_urls: list[str] = []
    last_error: str | None = None
    capture = capture_fn or _capture_single_url

    for source in source_urls:
        if not isinstance(source, str) or not source.strip():
            continue
        try:
            target_url = build_preview_target_url(source, path=normalized_path)
        except Exception as exc:
            last_error = str(exc)
            continue

        attempted_urls.append(target_url)
        try:
            image_bytes, width, height = capture(
                target_url=target_url,
                timeout_ms=timeout_ms,
                full_page=full_page,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
            )
            return PreviewScreenshotResult(
                ok=True,
                path=normalized_path,
                target_url=target_url,
                source_url=source,
                mime_type="image/jpeg",
                image_bytes=image_bytes,
                width=width,
                height=height,
                error=None,
                attempted_urls=attempted_urls,
            )
        except Exception as exc:
            last_error = str(exc)

    return PreviewScreenshotResult(
        ok=False,
        path=normalized_path,
        target_url=None,
        source_url=None,
        mime_type="image/jpeg",
        image_bytes=None,
        width=None,
        height=None,
        error=last_error or "no preview URL was available for screenshot capture",
        attempted_urls=attempted_urls,
    )
