from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DesignApproach:
    approach_id: str
    title: str
    rationale: str
    render_prompt: str
    image_base64: str
    mime_type: str
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "approach_id": self.approach_id,
            "title": self.title,
            "rationale": self.rationale,
            "render_prompt": self.render_prompt,
            "image_base64": self.image_base64,
            "mime_type": self.mime_type,
            "width": int(self.width),
            "height": int(self.height),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DesignApproach:
        return cls(
            approach_id=str(d["approach_id"]),
            title=str(d["title"]),
            rationale=str(d["rationale"]),
            render_prompt=str(d["render_prompt"]),
            image_base64=str(d["image_base64"]),
            mime_type=str(d["mime_type"]),
            width=int(d["width"]),
            height=int(d["height"]),
        )


@dataclass
class DesignState:
    project_id: str
    path: str
    viewport_width: int
    viewport_height: int
    approaches: list[DesignApproach] = field(default_factory=list)
    selected_approach_id: str | None = None
    total_iterations: int = 0
    pending_continue_decision: bool = False
    last_user_instruction: str | None = None
    updated_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "path": self.path,
            "viewport_width": int(self.viewport_width),
            "viewport_height": int(self.viewport_height),
            "approaches": [a.to_dict() for a in self.approaches],
            "selected_approach_id": self.selected_approach_id,
            "total_iterations": int(self.total_iterations),
            "pending_continue_decision": bool(self.pending_continue_decision),
            "last_user_instruction": self.last_user_instruction,
            "updated_at_ms": int(self.updated_at_ms),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DesignState:
        return cls(
            project_id=str(d["project_id"]),
            path=str(d["path"]),
            viewport_width=int(d["viewport_width"]),
            viewport_height=int(d["viewport_height"]),
            approaches=[DesignApproach.from_dict(a) for a in d.get("approaches", [])],
            selected_approach_id=d.get("selected_approach_id"),
            total_iterations=int(d.get("total_iterations", 0)),
            pending_continue_decision=bool(d.get("pending_continue_decision", False)),
            last_user_instruction=d.get("last_user_instruction"),
            updated_at_ms=int(d.get("updated_at_ms", 0)),
        )


@dataclass
class SnapshotResponse:
    ok: bool
    image_base64: str | None
    mime_type: str
    width: int
    height: int
    path: str
    target_url: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "image_base64": self.image_base64,
            "mime_type": self.mime_type,
            "width": int(self.width),
            "height": int(self.height),
            "path": self.path,
            "target_url": self.target_url,
            "error": self.error,
        }
