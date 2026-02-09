import sys
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so tests can import the local `src/` package.
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _disable_gitlab_requirement_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Most unit tests don't configure GitLab env; keep GitLab enforcement opt-in per test.
    monkeypatch.setenv("AMICABLE_GIT_SYNC_REQUIRED", "0")
