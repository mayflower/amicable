from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .base import SandboxBackend


def get_backend() -> SandboxBackend:
    from .k8s_backend import K8sAgentSandboxBackend

    return K8sAgentSandboxBackend()
