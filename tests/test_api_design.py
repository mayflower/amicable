from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("dotenv")
pytest.importorskip("fastapi")

from src.design.session_state import clear_state
from src.design.types import DesignApproach


@dataclass
class _FakeProject:
    project_id: str
    slug: str
    template_id: str
    project_prompt: str = "Task management app for small teams."


class _FakeAgent:
    async def init(
        self,
        session_id: str,
        template_id: str | None = None,
        slug: str | None = None,
    ) -> bool:
        _ = session_id, template_id, slug
        return True

    async def capture_preview_screenshot(self, **_kwargs):
        return {
            "ok": True,
            "path": "/",
            "target_url": "https://preview.example.com/",
            "mime_type": "image/jpeg",
            "width": 1280,
            "height": 800,
            "image_base64": "abcd",
            "error": None,
        }


def _set_design_env(monkeypatch) -> None:
    monkeypatch.setenv("AMICABLE_DESIGN_ENABLED", "1")
    monkeypatch.setenv("AMICABLE_DESIGN_GEMINI_API_KEY", "k")
    monkeypatch.setenv("AMICABLE_DESIGN_GEMINI_TEXT_MODEL", "text-model")
    monkeypatch.setenv("AMICABLE_DESIGN_GEMINI_IMAGE_MODEL", "image-model")


def test_api_design_lifecycle(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server
    from src.design import gemini_design

    _set_design_env(monkeypatch)
    clear_state("p1")

    monkeypatch.setattr(
        ws_server,
        "_ensure_project_access",
        lambda _request, project_id: _FakeProject(
            project_id=project_id, slug="proj", template_id="lovable-vite"
        ),
    )
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent())

    async def _fake_generate_design_approaches(**kwargs):
        instruction = str(kwargs.get("instruction") or "")
        return [
            DesignApproach(
                approach_id="approach_1",
                title=f"A {instruction}".strip(),
                rationale="R1",
                render_prompt="P1",
                image_base64="img1",
                mime_type="image/png",
                width=1280,
                height=800,
            ),
            DesignApproach(
                approach_id="approach_2",
                title="B",
                rationale="R2",
                render_prompt="P2",
                image_base64="img2",
                mime_type="image/png",
                width=1280,
                height=800,
            ),
        ]

    monkeypatch.setattr(
        gemini_design, "generate_design_approaches", _fake_generate_design_approaches
    )

    client = TestClient(ws_server.app)

    r1 = client.post(
        "/api/design/p1/approaches",
        json={"path": "/", "viewport_width": 1280, "viewport_height": 800},
    )
    assert r1.status_code == 200
    assert len(r1.json()["approaches"]) == 2

    r2 = client.get("/api/design/p1/state")
    assert r2.status_code == 200
    assert r2.json()["selected_approach_id"] is None

    r3 = client.post(
        "/api/design/p1/select",
        json={
            "approach_id": "approach_1",
            "total_iterations": 5,
            "pending_continue_decision": True,
        },
    )
    assert r3.status_code == 200
    assert r3.json()["selected_approach_id"] == "approach_1"
    assert r3.json()["total_iterations"] == 5
    assert r3.json()["pending_continue_decision"] is True

    r4 = client.post(
        "/api/design/p1/approaches/regenerate",
        json={"instruction": "compact layout"},
    )
    assert r4.status_code == 200
    assert "compact layout" in r4.json()["approaches"][0]["title"]


def test_api_design_select_invalid_id(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server
    from src.design import gemini_design

    _set_design_env(monkeypatch)
    clear_state("p2")

    monkeypatch.setattr(
        ws_server,
        "_ensure_project_access",
        lambda _request, project_id: _FakeProject(
            project_id=project_id, slug="proj", template_id="lovable-vite"
        ),
    )
    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FakeAgent())

    async def _fake_generate_design_approaches(**_kwargs):
        return [
            DesignApproach(
                approach_id="approach_1",
                title="A",
                rationale="R1",
                render_prompt="P1",
                image_base64="img1",
                mime_type="image/png",
                width=1280,
                height=800,
            ),
            DesignApproach(
                approach_id="approach_2",
                title="B",
                rationale="R2",
                render_prompt="P2",
                image_base64="img2",
                mime_type="image/png",
                width=1280,
                height=800,
            ),
        ]

    monkeypatch.setattr(
        gemini_design, "generate_design_approaches", _fake_generate_design_approaches
    )

    client = TestClient(ws_server.app)
    create_res = client.post(
        "/api/design/p2/approaches",
        json={"path": "/", "viewport_width": 1280, "viewport_height": 800},
    )
    assert create_res.status_code == 200

    bad = client.post("/api/design/p2/select", json={"approach_id": "missing"})
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_approach_id"


def test_api_design_snapshot_failed(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    _set_design_env(monkeypatch)
    clear_state("p3")

    monkeypatch.setattr(
        ws_server,
        "_ensure_project_access",
        lambda _request, project_id: _FakeProject(
            project_id=project_id, slug="proj", template_id="lovable-vite"
        ),
    )

    class _FailingAgent(_FakeAgent):
        async def capture_preview_screenshot(self, **_kwargs):
            return {
                "ok": False,
                "error": "capture failed",
                "path": "/",
                "mime_type": "image/jpeg",
            }

    monkeypatch.setattr(ws_server, "_get_agent", lambda: _FailingAgent())

    client = TestClient(ws_server.app)
    res = client.post("/api/design/p3/snapshot", json={})
    assert res.status_code == 500
    assert res.json()["error"] == "snapshot_failed"


def test_api_design_auth_guard(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import src.runtimes.ws_server as ws_server

    _set_design_env(monkeypatch)

    def _denied(_request, project_id):
        _ = project_id
        raise PermissionError("not_authenticated")

    monkeypatch.setattr(ws_server, "_ensure_project_access", _denied)

    client = TestClient(ws_server.app)
    res = client.get("/api/design/p4/state")
    assert res.status_code == 401
    assert res.json()["error"] == "not_authenticated"
