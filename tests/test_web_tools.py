from __future__ import annotations

from dataclasses import dataclass

import src.deepagents_backend.web_tools as web_tools


@dataclass
class _FakeResponse:
    text: str
    status_code: int = 200
    url: str = "https://example.com/"


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def get(self, *_args, **_kwargs):
        return self._response


def test_websearch_parses_duckduckgo_results():
    ddg_html = """
    <a class="result__a" href="https://example.com/a">Example Title</a>
    <a class="result__snippet">Example snippet text.</a>
    """

    def _fake_http_get(**kwargs):
        assert "duckduckgo" in kwargs["url"]
        return _FakeResponse(text=ddg_html)

    original = web_tools._http_get
    web_tools._http_get = _fake_http_get
    try:
        result = web_tools._search_web(query="example", session=object())
    finally:
        web_tools._http_get = original

    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Example Title"
    assert result["results"][0]["url"] == "https://example.com/a"
    assert result["results"][0]["snippet"] == "Example snippet text."
    assert result["results"][0]["page_age"] is None


def test_websearch_uses_brave_fallback_on_duckduckgo_challenge():
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

    original = web_tools._http_get
    web_tools._http_get = _fake_http_get
    try:
        result = web_tools._search_web(query="fallback", session=object())
    finally:
        web_tools._http_get = original

    assert any("duckduckgo" in c for c in calls)
    assert any("search.brave.com" in c for c in calls)
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Fallback Result"
    assert result["results"][0]["url"] == "https://fallback.example.com/p"
    assert result["results"][0]["page_age"] == "March 8, 2024"


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


def test_websearch_dedupes_and_enforces_max_results():
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

    def _fake_http_get(**_kwargs):
        return _FakeResponse(text=ddg_html)

    original_http_get = web_tools._http_get
    original_max_results = web_tools.web_search_max_results
    web_tools._http_get = _fake_http_get
    web_tools.web_search_max_results = lambda: 2
    try:
        result = web_tools._search_web(query="dedupe test", session=object())
    finally:
        web_tools._http_get = original_http_get
        web_tools.web_search_max_results = original_max_results

    assert len(result["results"]) == 2
    assert result["results"][0]["url"] == "https://example.com/a"
    assert result["results"][1]["url"] == "https://example.com/b"


def test_webfetch_uses_trafilatura_content_and_model_prompt():
    fake_response = _FakeResponse(
        text="<html><body>ignored</body></html>",
        status_code=200,
        url="https://example.com/final",
    )
    fake_session = _FakeSession(fake_response)
    captured_prompt: dict[str, str] = {}

    original_extract = web_tools._extract_with_trafilatura
    original_answer = web_tools._answer_from_small_model
    web_tools._extract_with_trafilatura = lambda _html: "# Title\n\nMarkdown body."

    def _fake_answer_from_small_model(*, model: str, prompt_text: str):
        captured_prompt["model"] = model
        captured_prompt["prompt_text"] = prompt_text
        return "Grounded answer", None

    web_tools._answer_from_small_model = _fake_answer_from_small_model
    try:
        out = web_tools._web_fetch(
            url="https://example.com/start",
            prompt="What is this page about?",
            session=fake_session,
        )
    finally:
        web_tools._extract_with_trafilatura = original_extract
        web_tools._answer_from_small_model = original_answer

    assert out["response"] == "Grounded answer"
    assert out["url"] == "https://example.com/start"
    assert out["final_url"] == "https://example.com/final"
    assert out["status_code"] == 200
    assert "What is this page about?" in captured_prompt["prompt_text"]
    assert "Markdown body." in captured_prompt["prompt_text"]


def test_webfetch_returns_schema_stable_payload_on_model_failure():
    fake_response = _FakeResponse(
        text="<html><body>body</body></html>",
        status_code=200,
        url="https://example.com/final",
    )
    fake_session = _FakeSession(fake_response)

    original_extract = web_tools._extract_with_trafilatura
    original_answer = web_tools._answer_from_small_model
    web_tools._extract_with_trafilatura = lambda _html: "Extracted fallback content."
    web_tools._answer_from_small_model = lambda **_kwargs: (
        None,
        "model invocation failed",
    )
    try:
        out = web_tools._web_fetch(
            url="https://example.com/start",
            prompt="Question?",
            session=fake_session,
        )
    finally:
        web_tools._extract_with_trafilatura = original_extract
        web_tools._answer_from_small_model = original_answer

    assert set(out.keys()) == {"response", "url", "final_url", "status_code"}
    assert out["url"] == "https://example.com/start"
    assert out["final_url"] == "https://example.com/final"
    assert out["status_code"] == 200
    assert "Could not run the configured small model" in str(out["response"])


def test_webfetch_preserves_original_and_final_urls():
    fake_response = _FakeResponse(
        text="<html><body>body</body></html>",
        status_code=302,
        url="https://redirected.example.org/landing",
    )
    fake_session = _FakeSession(fake_response)

    original_extract = web_tools._extract_with_trafilatura
    original_answer = web_tools._answer_from_small_model
    web_tools._extract_with_trafilatura = lambda _html: "Page content."
    web_tools._answer_from_small_model = lambda **_kwargs: ("Answer", None)
    try:
        out = web_tools._web_fetch(
            url="https://origin.example.org/start",
            prompt="Question?",
            session=fake_session,
        )
    finally:
        web_tools._extract_with_trafilatura = original_extract
        web_tools._answer_from_small_model = original_answer

    assert out["url"] == "https://origin.example.org/start"
    assert out["final_url"] == "https://redirected.example.org/landing"
    assert out["status_code"] == 302
    assert out["response"] == "Answer"
