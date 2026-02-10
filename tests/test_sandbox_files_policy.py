from __future__ import annotations

import pytest

from src.sandbox_files.policy import normalize_public_path, require_mutation_allowed


def test_normalize_public_path_accepts_relative() -> None:
    assert normalize_public_path("src/App.tsx") == "/src/App.tsx"


def test_normalize_public_path_rejects_empty() -> None:
    with pytest.raises(ValueError):
        normalize_public_path("")


def test_normalize_public_path_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        normalize_public_path("/src/../secrets.txt")


def test_require_mutation_denies_main_tsx() -> None:
    with pytest.raises(PermissionError):
        require_mutation_allowed("/src/main.tsx")


def test_require_mutation_denies_node_modules() -> None:
    with pytest.raises(PermissionError):
        require_mutation_allowed("/node_modules/x.js")
