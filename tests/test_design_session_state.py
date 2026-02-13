from __future__ import annotations

from src.design.session_state import (
    clear_state,
    get_lock,
    get_state,
    set_state,
    update_state,
)
from src.design.types import DesignApproach, DesignState


def _sample_state(project_id: str = "p1") -> DesignState:
    return DesignState(
        project_id=project_id,
        path="/",
        viewport_width=1280,
        viewport_height=800,
        approaches=[
            DesignApproach(
                approach_id="approach_1",
                title="A",
                rationale="R",
                render_prompt="P",
                image_base64="abcd",
                mime_type="image/png",
                width=1280,
                height=800,
            )
        ],
    )


def test_state_roundtrip_and_update() -> None:
    clear_state("p1")
    saved = set_state(_sample_state("p1"))
    assert saved.project_id == "p1"
    assert saved.updated_at_ms > 0

    loaded = get_state("p1")
    assert loaded is not None
    assert loaded.approaches[0].title == "A"

    updated = update_state("p1", selected_approach_id="approach_1", total_iterations=3)
    assert updated is not None
    assert updated.selected_approach_id == "approach_1"
    assert updated.total_iterations == 3

    clear_state("p1")
    assert get_state("p1") is None


def test_get_lock_is_stable_per_project() -> None:
    a = get_lock("p-lock")
    b = get_lock("p-lock")
    c = get_lock("p-lock-other")
    assert a is b
    assert a is not c
