from __future__ import annotations

from dataclasses import dataclass

import pytest

import src.deepagents_backend.web_tools as web_tools


@dataclass
class _FakeResponse:
    text: str
    status_code: int = 200
    url: str = "https://example.com/"
    content: bytes = b""

    def __post_init__(self):
        if not self.content and self.text:
            self.content = self.text.encode("utf-8")

    def close(self):
        pass


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def get(self, *_args, **_kwargs):
        return self._response


# ---------------------------------------------------------------------------
# WebSearch tests
# ---------------------------------------------------------------------------


def test_websearch_parses_duckduckgo_results(monkeypatch):
    ddg_html = """
    <a class="result__a" href="https://example.com/a">Example Title</a>
    <a class="result__snippet">Example snippet text.</a>
    """

    def _fake_http_get(**kwargs):
        assert "duckduckgo" in kwargs["url"]
        return _FakeResponse(text=ddg_html)

    monkeypatch.setattr(web_tools, "_http_get", _fake_http_get)
    result = web_tools._search_web(query="example", session=object())

    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Example Title"
    assert result["results"][0]["url"] == "https://example.com/a"
    assert result["results"][0]["snippet"] == "Example snippet text."
    assert result["results"][0]["page_age"] is None
    assert "warnings" not in result


def test_websearch_uses_brave_fallback_on_duckduckgo_challenge(monkeypatch):
    ddg_challenge_html = """
    <div class="anomaly-modal">Unfortunately, bots use DuckDuckGo too.</div>
    """
    brave_html = """
    <div class="snippet" data-pos="0">
      <a class="svelte-14r20fy l1" href="https://fallback.example.com/p">
        <div class="title">Fallback Result</div>
      </a>
      <div class="generic-snippet">
        <div class="content">
          <span class="t-secondary">March 8, 2024 -</span>
          Brave fallback snippet.
        </div>
      </div>
    </div>
    """
    calls: list[str] = []

    def _fake_http_get(**kwargs):
        calls.append(kwargs["url"])
        if "duckduckgo" in kwargs["url"]:
            return _FakeResponse(text=ddg_challenge_html)
        if "search.brave.com" in kwargs["url"]:
            return _FakeResponse(text=brave_html)
        raise AssertionError("unexpected url")

    monkeypatch.setattr(web_tools, "_http_get", _fake_http_get)
    result = web_tools._search_web(query="fallback", session=object())

    assert any("duckduckgo" in c for c in calls)
    assert any("search.brave.com" in c for c in calls)
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Fallback Result"
    assert result["results"][0]["url"] == "https://fallback.example.com/p"
    assert result["results"][0]["page_age"] == "March 8, 2024"
    assert "DuckDuckGo challenge detected" in result["warnings"]


def test_websearch_domain_allow_and_block_filters():
    results = [
        web_tools._SearchResult("A", "https://docs.python.org/3/", "a"),
        web_tools._SearchResult("B", "https://sub.example.com/path", "b"),
        web_tools._SearchResult("C", "https://blocked.example.com/path", "c"),
    ]

    filtered = web_tools._apply_domain_filters(
        results,
        allowed_domains=["example.com", "python.org"],
        blocked_domains=["blocked.example.com"],
    )

    urls = [r.url for r in filtered]
    assert "https://docs.python.org/3/" in urls
    assert "https://sub.example.com/path" in urls
    assert "https://blocked.example.com/path" not in urls


def test_websearch_dedupes_and_enforces_max_results(monkeypatch):
    ddg_html = """
    <a class="result__a" href="https://example.com/a">A1</a>
    <a class="result__snippet">Snippet A1</a>
    <a class="result__a" href="https://example.com/a">A2 duplicate</a>
    <a class="result__snippet">Snippet A2</a>
    <a class="result__a" href="https://example.com/b">B</a>
    <a class="result__snippet">Snippet B</a>
    <a class="result__a" href="https://example.com/c">C</a>
    <a class="result__snippet">Snippet C</a>
    """

    monkeypatch.setattr(web_tools, "_http_get", lambda **_kw: _FakeResponse(text=ddg_html))
    monkeypatch.setattr(web_tools, "web_search_max_results", lambda: 2)

    result = web_tools._search_web(query="dedupe test", session=object())

    assert len(result["results"]) == 2
    assert result["results"][0]["url"] == "https://example.com/a"
    assert result["results"][1]["url"] == "https://example.com/b"


def test_websearch_returns_empty_for_blank_query():
    result = web_tools._search_web(query="")
    assert result == {"results": []}

    result2 = web_tools._search_web(query="   ")
    assert result2 == {"results": []}


def test_websearch_falls_back_to_brave_on_ddg_exception(monkeypatch):
    brave_html = """
    <a class="svelte-14r20fy l1" href="https://brave-result.example.com/">
      <div class="title">Brave Result</div>
    </a>
    """

    def _fake_http_get(**kwargs):
        if "duckduckgo" in kwargs["url"]:
            raise ConnectionError("DDG unreachable")
        return _FakeResponse(text=brave_html)

    monkeypatch.setattr(web_tools, "_http_get", _fake_http_get)
    result = web_tools._search_web(query="fallback test", session=object())

    assert len(result["results"]) == 1
    assert result["results"][0]["url"] == "https://brave-result.example.com/"
    assert "DuckDuckGo search failed" in result["warnings"]


def test_websearch_surfaces_warnings_when_both_providers_fail(monkeypatch):
    def _fake_http_get(**_kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr(web_tools, "_http_get", _fake_http_get)
    result = web_tools._search_web(query="both fail", session=object())

    assert result["results"] == []
    assert len(result["warnings"]) == 2
    assert "DuckDuckGo search failed" in result["warnings"]
    assert "Brave search failed" in result["warnings"]


# ---------------------------------------------------------------------------
# WebFetch tests
# ---------------------------------------------------------------------------


def test_webfetch_uses_trafilatura_content_and_model_prompt(monkeypatch):
    fake_response = _FakeResponse(
        text="<html><body>ignored</body></html>",
        status_code=200,
        url="https://example.com/final",
    )
    fake_session = _FakeSession(fake_response)
    captured_prompt: dict[str, str] = {}

    monkeypatch.setattr(web_tools, "_extract_with_trafilatura", lambda _html: "# Title\n\nMarkdown body.")
    monkeypatch.setattr(web_tools, "_is_private_url", lambda _url: False)

    def _fake_answer(*, model: str, prompt_text: str):
        captured_prompt["model"] = model
        captured_prompt["prompt_text"] = prompt_text
        return "Grounded answer", None

    monkeypatch.setattr(web_tools, "_answer_from_small_model", _fake_answer)

    out = web_tools._web_fetch(
        url="https://example.com/start",
        prompt="What is this page about?",
        session=fake_session,
    )

    assert out["response"] == "Grounded answer"
    assert out["url"] == "https://example.com/start"
    assert out["final_url"] == "https://example.com/final"
    assert out["status_code"] == 200
    assert "What is this page about?" in captured_prompt["prompt_text"]
    assert "Markdown body." in captured_prompt["prompt_text"]


def test_webfetch_returns_schema_stable_payload_on_model_failure(monkeypatch):
    fake_response = _FakeResponse(
        text="<html><body>body</body></html>",
        status_code=200,
        url="https://example.com/final",
    )
    fake_session = _FakeSession(fake_response)

    monkeypatch.setattr(web_tools, "_extract_with_trafilatura", lambda _html: "Extracted fallback content.")
    monkeypatch.setattr(web_tools, "_is_private_url", lambda _url: False)
    monkeypatch.setattr(web_tools, "_answer_from_small_model", lambda **_kw: (None, "model invocation failed"))

    out = web_tools._web_fetch(
        url="https://example.com/start",
        prompt="Question?",
        session=fake_session,
    )

    assert set(out.keys()) == {"response", "url", "final_url", "status_code"}
    assert out["url"] == "https://example.com/start"
    assert out["final_url"] == "https://example.com/final"
    assert out["status_code"] == 200
    assert "Could not run the configured small model" in str(out["response"])


def test_webfetch_preserves_original_and_final_urls(monkeypatch):
    fake_response = _FakeResponse(
        text="<html><body>body</body></html>",
        status_code=302,
        url="https://redirected.example.org/landing",
    )
    fake_session = _FakeSession(fake_response)

    monkeypatch.setattr(web_tools, "_extract_with_trafilatura", lambda _html: "Page content.")
    monkeypatch.setattr(web_tools, "_is_private_url", lambda _url: False)
    monkeypatch.setattr(web_tools, "_answer_from_small_model", lambda **_kw: ("Answer", None))

    out = web_tools._web_fetch(
        url="https://origin.example.org/start",
        prompt="Question?",
        session=fake_session,
    )

    assert out["url"] == "https://origin.example.org/start"
    assert out["final_url"] == "https://redirected.example.org/landing"
    # 302 is not >= 400, so it proceeds with content extraction
    assert out["response"] == "Answer"


def test_webfetch_rejects_empty_url():
    out = web_tools._web_fetch(url="", prompt="anything")
    assert out["response"] == "Invalid URL: empty input."
    assert out["status_code"] == 0


def test_webfetch_rejects_non_http_url():
    out = web_tools._web_fetch(url="ftp://evil.example.com/file", prompt="anything")
    assert "only http(s) URLs are supported" in out["response"]
    assert out["status_code"] == 0


def test_webfetch_rejects_private_url(monkeypatch):
    monkeypatch.setattr(web_tools, "_is_private_url", lambda _url: True)
    out = web_tools._web_fetch(url="https://internal.local/secret", prompt="anything")
    assert "private or internal" in out["response"]
    assert out["status_code"] == 0


def test_webfetch_returns_error_on_http_exception(monkeypatch):
    class _ExplodingSession:
        def get(self, *_a, **_kw):
            raise ConnectionError("DNS resolution failed")

    monkeypatch.setattr(web_tools, "_is_private_url", lambda _url: False)
    out = web_tools._web_fetch(
        url="https://unreachable.example.com/",
        prompt="anything",
        session=_ExplodingSession(),
    )
    assert out["status_code"] == 0
    assert "network error" in out["response"]
    assert out["url"] == "https://unreachable.example.com/"


def test_webfetch_returns_error_on_http_4xx(monkeypatch):
    fake_response = _FakeResponse(text="Not Found", status_code=404, url="https://example.com/gone")
    monkeypatch.setattr(web_tools, "_is_private_url", lambda _url: False)

    out = web_tools._web_fetch(
        url="https://example.com/gone",
        prompt="anything",
        session=_FakeSession(fake_response),
    )
    assert out["status_code"] == 404
    assert "HTTP 404" in out["response"]


def test_webfetch_uses_html_fallback_when_trafilatura_empty(monkeypatch):
    fake_response = _FakeResponse(
        text="<html><body><p>Plain body text</p></body></html>",
        status_code=200,
        url="https://example.com/",
    )
    captured: dict[str, str] = {}

    monkeypatch.setattr(web_tools, "_extract_with_trafilatura", lambda _html: "")
    monkeypatch.setattr(web_tools, "_is_private_url", lambda _url: False)

    def _fake_answer(*, model: str, prompt_text: str):
        captured["prompt_text"] = prompt_text
        return "Fallback answer", None

    monkeypatch.setattr(web_tools, "_answer_from_small_model", _fake_answer)

    out = web_tools._web_fetch(
        url="https://example.com/",
        prompt="What?",
        session=_FakeSession(fake_response),
    )
    assert out["response"] == "Fallback answer"
    assert "Plain body text" in captured["prompt_text"]


# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------


def test_decode_duckduckgo_href_extracts_uddg_parameter():
    href = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Freal.example.com%2Fpage&rut=abc"
    assert web_tools._decode_duckduckgo_href(href) == "https://real.example.com/page"


def test_decode_duckduckgo_href_returns_direct_url_unchanged():
    assert web_tools._decode_duckduckgo_href("https://example.com/direct") == "https://example.com/direct"


def test_decode_duckduckgo_href_handles_empty():
    assert web_tools._decode_duckduckgo_href("") == ""


def test_coerce_model_text_handles_content_block_list():
    assert web_tools._coerce_model_text([{"type": "text", "text": "Hello"}]) == "Hello"
    assert web_tools._coerce_model_text("plain string") == "plain string"
    assert web_tools._coerce_model_text([{"type": "text", "text": ""}]) == ""
    assert web_tools._coerce_model_text(42) == "42"


def test_get_web_tools_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setenv("AMICABLE_WEB_TOOLS_ENABLED", "0")
    assert web_tools.get_web_tools() == []


def test_is_private_url_blocks_loopback():
    assert web_tools._is_private_url("http://127.0.0.1:8888/exec") is True


def test_is_private_url_blocks_metadata():
    assert web_tools._is_private_url("http://169.254.169.254/latest/meta-data/") is True


def test_normalize_url_rejects_file_scheme():
    assert web_tools._normalize_url("file:///etc/passwd") == ""


def test_normalize_url_rejects_ftp_scheme():
    assert web_tools._normalize_url("ftp://evil.example.com/file") == ""
