from __future__ import annotations

import asyncio
import json
import os
import re
from typing import TYPE_CHECKING, Any

from src.design.types import DesignApproach

if TYPE_CHECKING:
    import httpx

_JSON_OBJECT_RE = re.compile(r"\{.*\}", flags=re.DOTALL)
_JSON_ARRAY_RE = re.compile(r"\[.*\]", flags=re.DOTALL)


class DesignConfigError(RuntimeError):
    pass


class DesignGenerationError(RuntimeError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def is_design_enabled() -> bool:
    return _env_bool("AMICABLE_DESIGN_ENABLED", True)


def _api_key() -> str:
    return (os.environ.get("AMICABLE_DESIGN_GEMINI_API_KEY") or "").strip()


def _text_model() -> str:
    return (os.environ.get("AMICABLE_DESIGN_GEMINI_TEXT_MODEL") or "").strip()


def _image_model() -> str:
    return (os.environ.get("AMICABLE_DESIGN_GEMINI_IMAGE_MODEL") or "").strip()


def timeout_s() -> int:
    return max(5, _env_int("AMICABLE_DESIGN_TIMEOUT_S", 45))


def max_image_base64_chars() -> int:
    return max(100_000, _env_int("AMICABLE_DESIGN_MAX_IMAGE_BASE64_CHARS", 4_000_000))


def validate_design_config() -> str | None:
    if not _api_key():
        return "missing AMICABLE_DESIGN_GEMINI_API_KEY"
    if not _text_model():
        return "missing AMICABLE_DESIGN_GEMINI_TEXT_MODEL"
    if not _image_model():
        return "missing AMICABLE_DESIGN_GEMINI_IMAGE_MODEL"
    return None


def _extract_text_parts(payload: dict[str, Any]) -> str:
    out: list[str] = []
    for cand in payload.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            txt = part.get("text")
            if isinstance(txt, str) and txt.strip():
                out.append(txt.strip())
    return "\n".join(out).strip()


def _extract_inline_image(payload: dict[str, Any]) -> tuple[str, str] | None:
    for cand in payload.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData")
            if not isinstance(inline, dict):
                inline = part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            data = inline.get("data")
            if not isinstance(data, str) or not data:
                continue
            mime = inline.get("mimeType")
            if not isinstance(mime, str):
                mime = inline.get("mime_type")
            return data, (mime if isinstance(mime, str) and mime else "image/png")
    return None


def _extract_json(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass

    m_obj = _JSON_OBJECT_RE.search(raw)
    if m_obj:
        try:
            return json.loads(m_obj.group(0))
        except Exception:
            pass

    m_arr = _JSON_ARRAY_RE.search(raw)
    if m_arr:
        try:
            return json.loads(m_arr.group(0))
        except Exception:
            pass
    return None


def _fallback_approaches(*, instruction: str) -> list[dict[str, str]]:
    safe = (instruction or "").strip()
    return [
        {
            "title": "Clear Task-First Flow",
            "rationale": "Prioritize faster completion and reduced cognitive load.",
            "render_prompt": (
                "Re-layout the UI around a primary task funnel with explicit hierarchy, "
                "strong CTA prominence, clearer spacing, and better scannability."
            ),
        },
        {
            "title": "Guided and Trust-Building",
            "rationale": "Increase confidence using contextual guidance and progressive disclosure.",
            "render_prompt": (
                "Re-layout the UI with onboarding cues, helper text, and segmented sections "
                "that guide users step by step without overwhelming them."
            ),
        },
    ] if not safe else [
        {
            "title": "User-Driven Simplification",
            "rationale": "Incorporates the latest refinement request while keeping usability first.",
            "render_prompt": (
                "Apply this refinement request while preserving IA and improving clarity: "
                f"{safe}"
            ),
        },
        {
            "title": "Alternative Visual Emphasis",
            "rationale": "Offers a distinct visual direction for the same intent.",
            "render_prompt": (
                "Provide a distinct second direction for the same refinement request, focused on "
                "strong hierarchy and discoverability: "
                f"{safe}"
            ),
        },
    ]


def _normalize_two_approaches(raw: Any, *, instruction: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    items: list[Any] = []
    if isinstance(raw, dict):
        possible = raw.get("approaches")
        if isinstance(possible, list):
            items = possible
    elif isinstance(raw, list):
        items = raw

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        rationale = str(item.get("rationale") or "").strip()
        render_prompt = str(item.get("render_prompt") or item.get("prompt") or "").strip()
        if not title:
            title = f"Approach {idx + 1}"
        if not rationale:
            rationale = "Usability-forward design direction."
        if not render_prompt:
            render_prompt = (
                "Improve usability and visual hierarchy for this app while keeping core IA intact."
            )
        candidates.append(
            {
                "title": title[:120],
                "rationale": rationale[:400],
                "render_prompt": render_prompt[:1200],
            }
        )

    if len(candidates) < 2:
        return _fallback_approaches(instruction=instruction)
    return candidates[:2]


async def _post_generate_content(
    *,
    client: httpx.AsyncClient,
    model: str,
    text_prompt: str,
    image_base64: str | None,
    image_mime_type: str | None,
    request_image_output: bool,
) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts: list[dict[str, Any]] = [{"text": text_prompt}]
    if image_base64 and image_mime_type:
        parts.append(
            {
                "inlineData": {
                    "mimeType": image_mime_type,
                    "data": image_base64,
                }
            }
        )

    body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
    }
    if request_image_output:
        body["generationConfig"] = {
            "responseModalities": ["TEXT", "IMAGE"],
        }

    try:
        res = await client.post(url, params={"key": _api_key()}, json=body)
    except Exception as exc:
        raise DesignGenerationError(f"gemini request failed: {exc}") from exc

    data: dict[str, Any]
    try:
        data = res.json()
    except Exception:
        data = {}

    if res.status_code >= 400:
        msg = str((data.get("error") or {}).get("message") or "").strip()
        raise DesignGenerationError(
            f"gemini request failed ({res.status_code}): {msg or 'unknown error'}"
        )
    return data


def _approach_prompt(
    *,
    viewport_width: int,
    viewport_height: int,
    app_context: str,
    instruction: str,
) -> str:
    return (
        "You are a senior product designer.\n"
        "Given the current app screenshot and viewport, recommend exactly two different design approaches.\n"
        "Goal: improve usability and visual design for the current application type and expected user base.\n"
        "Preserve core information architecture.\n"
        "Return JSON only with shape:\n"
        '{ "approaches": ['
        '{"title":"...","rationale":"...","render_prompt":"..."},'
        '{"title":"...","rationale":"...","render_prompt":"..."}'
        "] }\n"
        f"Viewport: {viewport_width}x{viewport_height}\n"
        f"Application context: {app_context or '<unknown>'}\n"
        f"User refinement: {instruction or '<none>'}\n"
        "Ensure the two approaches are meaningfully distinct."
    )


def _render_prompt(
    *,
    approach_title: str,
    approach_rationale: str,
    approach_render_prompt: str,
    viewport_width: int,
    viewport_height: int,
    app_context: str,
) -> str:
    return (
        "Generate a redesigned UI mockup image based on the attached screenshot.\n"
        "Keep the same product purpose and plausible interaction model, but improve usability.\n"
        f"Target viewport: {viewport_width}x{viewport_height}.\n"
        f"Approach title: {approach_title}\n"
        f"Approach rationale: {approach_rationale}\n"
        f"Design directive: {approach_render_prompt}\n"
        f"Application context: {app_context or '<unknown>'}\n"
        "Output should be one coherent layout concept for this approach."
    )


async def generate_design_approaches(
    *,
    screenshot_base64: str,
    screenshot_mime_type: str,
    viewport_width: int,
    viewport_height: int,
    app_context: str = "",
    instruction: str = "",
) -> list[DesignApproach]:
    import httpx

    err = validate_design_config()
    if err:
        raise DesignConfigError(err)

    async with httpx.AsyncClient(timeout=timeout_s()) as client:
        text_resp = await _post_generate_content(
            client=client,
            model=_text_model(),
            text_prompt=_approach_prompt(
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                app_context=app_context,
                instruction=instruction,
            ),
            image_base64=screenshot_base64,
            image_mime_type=screenshot_mime_type,
            request_image_output=False,
        )
        raw_text = _extract_text_parts(text_resp)
        parsed = _extract_json(raw_text)
        normalized = _normalize_two_approaches(parsed, instruction=instruction)

        async def _render_one(i: int, item: dict[str, str]) -> DesignApproach:
            img_resp = await _post_generate_content(
                client=client,
                model=_image_model(),
                text_prompt=_render_prompt(
                    approach_title=item["title"],
                    approach_rationale=item["rationale"],
                    approach_render_prompt=item["render_prompt"],
                    viewport_width=viewport_width,
                    viewport_height=viewport_height,
                    app_context=app_context,
                ),
                image_base64=screenshot_base64,
                image_mime_type=screenshot_mime_type,
                request_image_output=True,
            )
            extracted = _extract_inline_image(img_resp)
            if extracted is None:
                raise DesignGenerationError("gemini image response missing inline image")
            image_b64, image_mime = extracted
            if len(image_b64) > max_image_base64_chars():
                raise DesignGenerationError("generated image exceeds max allowed size")
            return DesignApproach(
                approach_id=f"approach_{i + 1}",
                title=item["title"],
                rationale=item["rationale"],
                render_prompt=item["render_prompt"],
                image_base64=image_b64,
                mime_type=image_mime,
                width=int(viewport_width),
                height=int(viewport_height),
            )

        try:
            out = await asyncio.gather(
                *[_render_one(i, item) for i, item in enumerate(normalized[:2])]
            )
        except Exception as exc:
            raise DesignGenerationError(str(exc)) from exc
    return out
