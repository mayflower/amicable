from __future__ import annotations

import html
import ipaddress
import logging
import os
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

logger = logging.getLogger(__name__)

_DEFAULT_SEARCH_USER_AGENT = (
    "Mozilla/5.0 (compatible; AmicableWebTools/1.0; +https://example.invalid)"
)


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using default %d", name, raw, default)
        return int(default)


def web_tools_enabled() -> bool:
    return _env_bool("AMICABLE_WEB_TOOLS_ENABLED", True)


def web_fetch_model() -> str:
    return (
        os.environ.get("AMICABLE_WEB_FETCH_MODEL")
        or "anthropic:claude-haiku-4-5"
    ).strip()


def web_fetch_timeout_s() -> int:
    return max(1, _env_int("AMICABLE_WEB_FETCH_TIMEOUT_S", 20))


def web_fetch_max_content_chars() -> int:
    return max(1000, _env_int("AMICABLE_WEB_FETCH_MAX_CONTENT_CHARS", 25000))


def web_search_timeout_s() -> int:
    return max(1, _env_int("AMICABLE_WEB_SEARCH_TIMEOUT_S", 10))


def web_search_max_results() -> int:
    return max(1, _env_int("AMICABLE_WEB_SEARCH_MAX_RESULTS", 8))


def web_fetch_max_response_bytes() -> int:
    return max(100_000, _env_int("AMICABLE_WEB_FETCH_MAX_RESPONSE_BYTES", 5_000_000))


def web_search_user_agent() -> str:
    raw = (os.environ.get("AMICABLE_WEB_SEARCH_USER_AGENT") or "").strip()
    return raw or _DEFAULT_SEARCH_USER_AGENT


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_url(url: str) -> bool:
    """Return True if the URL resolves to a private/loopback/link-local address."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not hostname:
        return True
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM):
            addr = ipaddress.ip_address(info[4][0])
            if any(addr in net for net in _BLOCKED_NETWORKS):
                return True
    except (socket.gaierror, ValueError, OSError):
        return True  # fail closed on resolution errors
    return False


@dataclass
class _SearchResult:
    title: str
    url: str
    snippet: str
    page_age: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "page_age": self.page_age,
        }


def _strip_tags(value: str) -> str:
    no_scripts = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", value)
    no_tags = re.sub(r"(?s)<[^>]+>", " ", no_scripts)
    return html.unescape(no_tags)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", _strip_tags(value)).strip()


def _normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return ""
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


def _result_key(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{host}{path}?{parsed.query}"


def _decode_duckduckgo_href(href: str) -> str:
    raw = str(href or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            qs = parse_qs(parsed.query)
            uddg = qs.get("uddg")
            if uddg and uddg[0]:
                return unquote(uddg[0])
        return raw
    if raw.startswith("/l/?") or raw.startswith("https://duckduckgo.com/l/?"):
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg")
        if uddg and uddg[0]:
            return unquote(uddg[0])
    return raw


def _normalize_domain_pattern(domain: str) -> str:
    d = str(domain or "").strip().lower()
    if not d:
        return ""
    if "://" in d:
        d = urlparse(d).hostname or ""
    d = d.lstrip(".")
    if d.startswith("*."):
        d = d[2:]
    return d


def _host_matches_domain(host: str, domain_pattern: str) -> bool:
    host_l = str(host or "").strip().lower()
    pat = _normalize_domain_pattern(domain_pattern)
    if not host_l or not pat:
        return False
    return host_l == pat or host_l.endswith(f".{pat}")


def _url_matches_any_domain(url: str, domain_patterns: list[str]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return any(_host_matches_domain(host, pat) for pat in domain_patterns)


def _parse_duckduckgo_results(html_text: str) -> list[_SearchResult]:
    out: list[_SearchResult] = []
    for match in re.finditer(
        r'(?is)<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html_text,
    ):
        href = _decode_duckduckgo_href(match.group(1))
        url = _normalize_url(href)
        if not url:
            continue
        title = _normalize_text(match.group(2))
        if not title:
            continue

        tail = html_text[match.end() : match.end() + 1600]
        snippet_match = re.search(
            r'(?is)<(?:a|div)[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div)>',
            tail,
        )
        snippet = _normalize_text(snippet_match.group(1)) if snippet_match else ""
        if not snippet:
            snippet = ""

        age_match = re.search(
            r'(?is)<span[^>]*class="[^"]*result__timestamp[^"]*"[^>]*>(.*?)</span>',
            tail,
        )
        page_age = _normalize_text(age_match.group(1)) if age_match else None
        if page_age == "":
            page_age = None

        out.append(_SearchResult(title=title, url=url, snippet=snippet, page_age=page_age))
    return out


def _parse_brave_results(html_text: str) -> list[_SearchResult]:
    out: list[_SearchResult] = []
    for match in re.finditer(
        r'(?is)<a[^>]*class="[^"]*\bl1\b[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html_text,
    ):
        href = html.unescape(match.group(1))
        url = _normalize_url(href)
        if not url:
            continue

        anchor_html = match.group(2)
        title_match = re.search(
            r'(?is)<div[^>]*class="[^"]*\btitle\b[^"]*"[^>]*>(.*?)</div>',
            anchor_html,
        )
        title_raw = title_match.group(1) if title_match else anchor_html
        title = _normalize_text(title_raw)
        if not title:
            continue

        tail = html_text[match.end() : match.end() + 2800]
        snippet_match = re.search(
            (
                r'(?is)<div[^>]*class="[^"]*generic-snippet[^"]*"[^>]*>.*?'
                r'<div[^>]*class="[^"]*\bcontent\b[^"]*"[^>]*>(.*?)</div>'
            ),
            tail,
        )
        snippet = _normalize_text(snippet_match.group(1)) if snippet_match else ""

        age_match = re.search(
            r'(?is)<span[^>]*class="[^"]*t-secondary[^"]*"[^>]*>([^<]{3,80})</span>',
            tail,
        )
        page_age = _normalize_text(age_match.group(1)) if age_match else None
        if page_age:
            page_age = page_age.rstrip("-").strip() or None

        out.append(_SearchResult(title=title, url=url, snippet=snippet, page_age=page_age))
    return out


def _is_duckduckgo_challenge(html_text: str) -> bool:
    lower = html_text.lower()
    return (
        "anomaly-modal" in lower
        or "bots use duckduckgo too" in lower
        or "challenge-form" in lower
    )


def _dedupe_results(results: list[_SearchResult]) -> list[_SearchResult]:
    seen: set[str] = set()
    out: list[_SearchResult] = []
    for item in results:
        key = _result_key(item.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _apply_domain_filters(
    results: list[_SearchResult],
    *,
    allowed_domains: list[str] | None,
    blocked_domains: list[str] | None,
) -> list[_SearchResult]:
    allowed = [
        _normalize_domain_pattern(v) for v in (allowed_domains or []) if v and str(v).strip()
    ]
    blocked = [
        _normalize_domain_pattern(v) for v in (blocked_domains or []) if v and str(v).strip()
    ]

    out: list[_SearchResult] = []
    for item in results:
        if allowed and not _url_matches_any_domain(item.url, allowed):
            continue
        if blocked and _url_matches_any_domain(item.url, blocked):
            continue
        out.append(item)
    return out


def _http_get(
    *,
    url: str,
    params: dict[str, str],
    timeout_s: int,
    session: Any,
    user_agent: str,
) -> Any:
    return session.get(
        url,
        params=params,
        timeout=float(timeout_s),
        headers={"User-Agent": user_agent},
        allow_redirects=True,
    )


def _search_web(
    *,
    query: str,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    session: Any | None = None,
) -> dict[str, list[dict[str, str | None]]]:
    q = str(query or "").strip()
    if not q:
        return {"results": []}

    timeout_s = web_search_timeout_s()
    ua = web_search_user_agent()
    http = session or _new_http_session()

    results: list[_SearchResult] = []
    warnings: list[str] = []

    ddg_html = ""
    ddg_challenge = False
    try:
        ddg_resp = _http_get(
            url="https://html.duckduckgo.com/html/",
            params={"q": q},
            timeout_s=timeout_s,
            session=http,
            user_agent=ua,
        )
        ddg_html = ddg_resp.text or ""
        ddg_challenge = _is_duckduckgo_challenge(ddg_html)
        if ddg_challenge:
            warnings.append("DuckDuckGo challenge detected")
        else:
            results = _parse_duckduckgo_results(ddg_html)
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for query=%r: %s", q, exc)
        warnings.append("DuckDuckGo search failed")
        results = []

    if ddg_challenge or not results:
        try:
            brave_resp = _http_get(
                url="https://search.brave.com/search",
                params={"q": q, "source": "web"},
                timeout_s=timeout_s,
                session=http,
                user_agent=ua,
            )
            results = _parse_brave_results(brave_resp.text or "")
        except Exception as exc:
            logger.warning("Brave search failed for query=%r: %s", q, exc)
            warnings.append("Brave search failed")
            results = []

    if not results and len(warnings) >= 2:
        logger.error("Both search providers failed for query=%r", q)

    filtered = _apply_domain_filters(
        _dedupe_results(results),
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
    )
    limited = filtered[: web_search_max_results()]
    out: dict[str, Any] = {"results": [r.to_dict() for r in limited]}
    if warnings:
        out["warnings"] = warnings
    return out


_trafilatura_import_warned = False


def _extract_with_trafilatura(html_text: str) -> str:
    global _trafilatura_import_warned
    try:
        import trafilatura
    except ImportError:
        if not _trafilatura_import_warned:
            logger.error("trafilatura is not installed; content extraction degraded")
            _trafilatura_import_warned = True
        return ""

    try:
        markdown = trafilatura.extract(
            html_text,
            output_format="markdown",
            include_links=True,
            include_formatting=True,
            favor_recall=True,
        )
    except Exception:
        logger.warning("trafilatura markdown extraction failed", exc_info=True)
        markdown = None
    if isinstance(markdown, str) and markdown.strip():
        return markdown.strip()

    try:
        plain = trafilatura.extract(
            html_text,
            output_format="txt",
            include_links=True,
            favor_recall=True,
        )
    except Exception:
        logger.warning("trafilatura plaintext extraction failed", exc_info=True)
        plain = None
    if isinstance(plain, str) and plain.strip():
        return plain.strip()
    return ""


def _fallback_text_from_html(html_text: str) -> str:
    return _normalize_text(html_text)


def _coerce_model_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return str(content).strip()


def _answer_from_small_model(*, model: str, prompt_text: str) -> tuple[str | None, str | None]:
    try:
        from langchain.chat_models import init_chat_model  # type: ignore
    except ImportError as exc:
        logger.error("Failed to import langchain chat_models: %s", exc)
        return None, "model init unavailable"

    try:
        llm = init_chat_model(model)
    except Exception as exc:
        logger.error("Failed to init model %s: %s", model, exc)
        return None, "model init failed"

    try:
        msg = llm.invoke(prompt_text)
    except Exception as exc:
        logger.warning("Model invocation failed for %s: %s", model, exc)
        return None, "model invocation failed"

    text = _coerce_model_text(getattr(msg, "content", ""))
    if not text:
        return None, "model returned empty response"
    return text, None


def _build_webfetch_prompt(
    *,
    user_prompt: str,
    source_url: str,
    final_url: str,
    content: str,
) -> str:
    return (
        "You answer questions strictly from provided page content.\n"
        "Rules:\n"
        "- Use only the provided page content.\n"
        "- If the answer is not present, say exactly: "
        "'Not found in the provided page content.'\n"
        "- Keep the answer concise and factual.\n\n"
        f"Source URL: {source_url}\n"
        f"Final URL: {final_url}\n"
        f"Question: {user_prompt.strip()}\n\n"
        "Page content:\n"
        f"{content}"
    )


def _web_fetch(
    *,
    url: str,
    prompt: str,
    session: Any | None = None,
) -> dict[str, str | int]:
    src_url = str(url or "").strip()
    user_prompt = str(prompt or "").strip()
    if not src_url:
        return {
            "response": "Invalid URL: empty input.",
            "url": "",
            "final_url": "",
            "status_code": 0,
        }

    normalized_src = _normalize_url(src_url)
    if not normalized_src:
        return {
            "response": "Invalid URL: only http(s) URLs are supported.",
            "url": src_url,
            "final_url": src_url,
            "status_code": 0,
        }

    if _is_private_url(normalized_src):
        logger.warning("Blocked SSRF attempt to private URL: %s", normalized_src)
        return {
            "response": "URL points to a private or internal address and cannot be fetched.",
            "url": normalized_src,
            "final_url": normalized_src,
            "status_code": 0,
        }

    http = session or _new_http_session()
    final_url = normalized_src
    status_code = 0
    html_text = ""
    max_bytes = web_fetch_max_response_bytes()
    try:
        resp = http.get(
            normalized_src,
            timeout=float(web_fetch_timeout_s()),
            allow_redirects=True,
            headers={"User-Agent": web_search_user_agent()},
            stream=True,
        )
        status_code = int(resp.status_code)
        final_url = str(resp.url or normalized_src)
        raw_bytes = resp.content[:max_bytes]
        resp.close()
        html_text = raw_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("WebFetch HTTP request failed for url=%s: %s", normalized_src, exc)
        return {
            "response": "Web fetch failed due to a network error.",
            "url": normalized_src,
            "final_url": final_url,
            "status_code": 0,
        }

    if status_code >= 400:
        logger.info("WebFetch got HTTP %d for %s", status_code, normalized_src)
        return {
            "response": f"HTTP {status_code} error fetching the URL.",
            "url": normalized_src,
            "final_url": final_url,
            "status_code": status_code,
        }

    extracted = _extract_with_trafilatura(html_text)
    if not extracted:
        extracted = _fallback_text_from_html(html_text)
    if not extracted:
        extracted = "No readable page content extracted."

    max_chars = web_fetch_max_content_chars()
    bounded = extracted[:max_chars]
    model_prompt = _build_webfetch_prompt(
        user_prompt=user_prompt,
        source_url=normalized_src,
        final_url=final_url,
        content=bounded,
    )
    answer, model_err = _answer_from_small_model(
        model=web_fetch_model(),
        prompt_text=model_prompt,
    )
    if answer is None:
        snippet = bounded[:800]
        fallback = (
            "Could not run the configured small model for page QA. "
            f"{model_err or 'unknown model error'}\n\n"
            "Extracted page snippet:\n"
            f"{snippet}"
        ).strip()
        return {
            "response": fallback,
            "url": normalized_src,
            "final_url": final_url,
            "status_code": status_code,
        }

    return {
        "response": answer,
        "url": normalized_src,
        "final_url": final_url,
        "status_code": status_code,
    }


def _new_http_session() -> Any:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests dependency is not available") from exc
    return requests.Session()


def get_web_tools() -> list[Any]:
    if not web_tools_enabled():
        return []

    from langchain_core.tools import tool  # type: ignore

    @tool("WebSearch")
    def web_search(
        query: str,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> dict[str, list[dict[str, str | None]]]:
        """Search the public web and return normalized result entries.

        Args:
            query: The search query string.
            allowed_domains: Optional domain allowlist (exact host or parent domain).
            blocked_domains: Optional domain denylist (exact host or parent domain).
        """
        return _search_web(
            query=query,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )

    @tool("WebFetch")
    def web_fetch(url: str, prompt: str) -> dict[str, str | int]:
        """Fetch a URL and answer a prompt using extracted page content.

        Args:
            url: The source URL to fetch.
            prompt: The question to answer from the fetched page content.
        """
        return _web_fetch(url=url, prompt=prompt)

    return [web_search, web_fetch]
