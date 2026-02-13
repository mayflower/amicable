from __future__ import annotations

from src.prompting.instruction_loader import compose_instruction_prompt


class _FakeBackend:
    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        if file_path not in self._files:
            raise FileNotFoundError(file_path)
        return self._files[file_path][offset : offset + limit]


def test_instruction_loader_merges_sources_with_imports() -> None:
    backend = _FakeBackend(
        {
            "/AGENTS.md": "Root rules\n@/shared.md\nEnd root",
            "/shared.md": "Shared rule",
            "/.deepagents/AGENTS.md": "Deep rule",
            "/memories/agent.local.md": "Local rule",
        }
    )

    out = compose_instruction_prompt(base_prompt="BASE", backend=backend)

    assert out.prompt.startswith("BASE")
    assert "Workspace instructions (/AGENTS.md):" in out.prompt
    assert "# imported: /shared.md" in out.prompt
    assert "Shared rule" in out.prompt
    assert "Workspace instructions (/.deepagents/AGENTS.md):" in out.prompt
    assert "Workspace instructions (/memories/agent.local.md):" in out.prompt
    assert out.truncated is False


def test_instruction_loader_detects_cycles() -> None:
    backend = _FakeBackend(
        {
            "/AGENTS.md": "@/a.md",
            "/a.md": "@/b.md",
            "/b.md": "@/a.md",
        }
    )

    out = compose_instruction_prompt(base_prompt="BASE", backend=backend)

    assert "BASE" in out.prompt
    assert any("(cycle)" in p for p in out.missing_paths)


def test_instruction_loader_respects_max_depth_and_max_chars() -> None:
    backend = _FakeBackend(
        {
            "/AGENTS.md": "@/a.md",
            "/a.md": "@/b.md\n" + ("x" * 100),
            "/b.md": "nested",
        }
    )

    out = compose_instruction_prompt(
        base_prompt="BASE",
        backend=backend,
        max_depth=2,
        max_chars=80,
    )

    assert any("max_depth" in p for p in out.missing_paths)
    assert out.truncated is True
    assert "truncated" in out.prompt.lower()


def test_instruction_loader_strips_code_fences() -> None:
    backend = _FakeBackend(
        {
            "/AGENTS.md": "```md\nKeep me\n```\n",
        }
    )

    out = compose_instruction_prompt(base_prompt="BASE", backend=backend)

    assert "```" not in out.prompt
    assert "Keep me" in out.prompt
