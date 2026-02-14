import importlib
import importlib.util

import pytest

if importlib.util.find_spec("deepagents") is None:
    pytest.skip(
        "deepagents not installed in this environment", allow_module_level=True
    )
requests = pytest.importorskip("requests")
K8sSandboxRuntimeBackend = importlib.import_module(
    "src.deepagents_backend.k8s_runtime_backend"
).K8sSandboxRuntimeBackend


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_exec_fallback_only_on_404_405():
    backend = K8sSandboxRuntimeBackend(
        sandbox_id="s1",
        base_url="http://example.invalid",
        root_dir="/app",
    )
    calls: list[str] = []

    def _fake_request(_method, path, **_kwargs):
        calls.append(path)
        if path == "execute":
            exc = requests.HTTPError("not found")
            exc.response = type("_Resp", (), {"status_code": 404})()
            raise exc
        assert path == "exec"
        return _FakeResp({"stdout": "ok", "stderr": "", "exit_code": 0})

    backend._request = _fake_request  # type: ignore[method-assign]
    out = backend._exec_raw("echo hi", timeout_s=1)  # type: ignore[attr-defined]
    assert out.exit_code == 0
    assert calls == ["execute", "exec"]


def test_exec_timeout_does_not_fallback():
    backend = K8sSandboxRuntimeBackend(
        sandbox_id="s1",
        base_url="http://example.invalid",
        root_dir="/app",
    )
    calls: list[str] = []

    def _fake_request(_method, path, **_kwargs):
        calls.append(path)
        raise requests.Timeout("timed out")

    backend._request = _fake_request  # type: ignore[method-assign]
    with pytest.raises(requests.Timeout):
        backend._exec_raw("echo hi", timeout_s=1)  # type: ignore[attr-defined]
    assert calls == ["execute"]
