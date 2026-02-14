from __future__ import annotations

import importlib.util

import pytest

if (
    importlib.util.find_spec("deepagents") is None
    or importlib.util.find_spec("requests") is None
):
    pytest.skip(
        "deepagents/requests not installed in this environment", allow_module_level=True
    )

from src.deepagents_backend.session_sandbox_manager import SessionSandboxManager


def test_delete_session_prefers_explicit_sandbox_id():
    class _FakeK8s:
        def __init__(self):
            self.kwargs = None

        def delete_app_environment(self, **kwargs):
            self.kwargs = kwargs
            return True

    mgr = SessionSandboxManager.__new__(SessionSandboxManager)
    mgr._env_by_session = {"sess-1": object()}
    mgr._backend_by_session = {"sess-1": object()}
    mgr._k8s_backend = _FakeK8s()

    ok = mgr.delete_session("sess-1", sandbox_id="claim-123", slug="my-slug")
    assert ok is True
    assert mgr._k8s_backend.kwargs == {"claim_name": "claim-123"}
