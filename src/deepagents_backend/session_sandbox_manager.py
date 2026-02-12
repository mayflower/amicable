from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from deepagents.backends.protocol import SandboxBackendProtocol

from src.deepagents_backend.k8s_runtime_backend import K8sSandboxRuntimeBackend
from src.sandbox_backends.k8s_backend import K8sAgentSandboxBackend


@dataclass(frozen=True)
class SessionEnv:
    session_id: str
    sandbox_id: str  # claim name
    preview_url: str
    exists: bool
    runtime_base_url: str


class SessionSandboxManager:
    """Manages the mapping: session_id -> (SandboxClaim + DeepAgents backend)."""

    def __init__(self) -> None:
        # Fail fast with a clear error if deepagents isn't installed in this runtime.
        try:
            importlib.import_module("deepagents.backends.protocol")
        except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
            raise ImportError(
                "deepagents is required to use the Amicable sandbox manager"
            ) from exc

        # Reuse existing claim creation + ready wait logic.
        self._k8s_backend = K8sAgentSandboxBackend()

        self._env_by_session: dict[str, SessionEnv] = {}
        self._backend_by_session: dict[str, SandboxBackendProtocol] = {}

        self._root_dir = (
            os.environ.get("SANDBOX_ROOT_DIR") or "/app"
        ).strip() or "/app"
        self._request_timeout_s = int(
            os.environ.get("SANDBOX_REQUEST_TIMEOUT_S") or "60"
        )
        self._exec_timeout_s = int(os.environ.get("SANDBOX_EXEC_TIMEOUT_S") or "600")

    def ensure_session(
        self,
        session_id: str,
        *,
        template_name: str | None = None,
        slug: str | None = None,
    ) -> SessionEnv:
        if session_id in self._env_by_session:
            return self._env_by_session[session_id]

        env = self._k8s_backend.create_app_environment(
            session_id=session_id, template_name=template_name, slug=slug
        )
        sandbox_id = str(env["sandbox_id"])
        preview_url = str(env["url"])
        exists = bool(env.get("exists", False))

        # Same service DNS pattern the preview router uses.
        host = f"{sandbox_id}.{self._k8s_backend.namespace}.svc.cluster.local"
        runtime_base_url = f"http://{host}:{self._k8s_backend.runtime_port}"

        out = SessionEnv(
            session_id=session_id,
            sandbox_id=sandbox_id,
            preview_url=preview_url,
            exists=exists,
            runtime_base_url=runtime_base_url,
        )
        self._env_by_session[session_id] = out
        return out

    def get_backend(self, session_id: str) -> SandboxBackendProtocol:
        if session_id in self._backend_by_session:
            return self._backend_by_session[session_id]

        env = self.ensure_session(session_id)
        backend = K8sSandboxRuntimeBackend(
            sandbox_id=env.sandbox_id,
            base_url=env.runtime_base_url,
            root_dir=self._root_dir,
            request_timeout_s=self._request_timeout_s,
            exec_timeout_s=self._exec_timeout_s,
        )
        self._backend_by_session[session_id] = backend
        return backend

    def get_internal_preview_url(self, session_id: str) -> str:
        """Return the in-cluster preview URL for a session's sandbox."""
        env = self.ensure_session(session_id)
        host = f"{env.sandbox_id}.{self._k8s_backend.namespace}.svc.cluster.local"
        return f"http://{host}:{self._k8s_backend.preview_port}/"

    def delete_session(self, session_id: str) -> bool:
        """Delete the k8s SandboxClaim/pod for a session (best-effort)."""
        self._env_by_session.pop(session_id, None)
        self._backend_by_session.pop(session_id, None)
        return bool(self._k8s_backend.delete_app_environment(session_id=session_id))
