from __future__ import annotations

from typing import Protocol


class SandboxBackend(Protocol):
    """Abstract sandbox backend.

    Backends must provide a workspace environment that contains a Vite dev server
    (preview) and a filesystem under /app.

    Returned dicts must include:
      - url: preview URL suitable for iframe
      - sandbox_id: opaque identifier used for subsequent calls

    Backends may additionally include:
      - exists: bool (true if reconnected to an existing sandbox)
    """

    def create_app_environment(self, *, session_id: str) -> dict: ...

    def load_code(self, *, sandbox_id: str) -> tuple[dict[str, bytes], str]: ...

    def edit_code(self, *, sandbox_id: str, code_map: dict[str, str]) -> dict: ...
