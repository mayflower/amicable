from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.responses import Response


def _load_runtime_module():
    repo_root = Path(__file__).resolve().parents[1]
    runtime_path = repo_root / "k8s/images/amicable-sandbox/runtime.py"
    spec = importlib.util.spec_from_file_location("amicable_sandbox_runtime", runtime_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_healthz_unhealthy_when_preview_exhausted():
    runtime = _load_runtime_module()
    runtime._preview_state_update(  # type: ignore[attr-defined]
        running_pid=None,
        restart_count=5,
        exhausted=True,
        last_exit_code=1,
        last_error="boom",
    )

    response = Response()
    payload = asyncio.run(runtime.healthz(response))
    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["preview"]["exhausted"] is True


def test_readyz_requires_running_preview():
    runtime = _load_runtime_module()
    runtime._preview_state_update(  # type: ignore[attr-defined]
        running_pid=12345,
        exhausted=False,
        restart_count=0,
        last_exit_code=None,
        last_error=None,
    )
    ok_response = Response()
    ok_payload = asyncio.run(runtime.readyz(ok_response))
    assert ok_response.status_code == 200
    assert ok_payload["status"] == "ready"

    runtime._preview_state_update(running_pid=None, exhausted=False)  # type: ignore[attr-defined]
    bad_response = Response()
    bad_payload = asyncio.run(runtime.readyz(bad_response))
    assert bad_response.status_code == 503
    assert bad_payload["status"] == "not_ready"
