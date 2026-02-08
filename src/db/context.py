from __future__ import annotations

import contextvars

_current_app_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "amicable_current_app_id", default=None
)


def set_current_app_id(app_id: str) -> contextvars.Token[str | None]:
    return _current_app_id.set(app_id)


def reset_current_app_id(token: contextvars.Token[str | None]) -> None:
    _current_app_id.reset(token)


def get_current_app_id() -> str:
    app_id = _current_app_id.get()
    if not app_id:
        raise RuntimeError("No current app_id bound to context")
    return app_id
