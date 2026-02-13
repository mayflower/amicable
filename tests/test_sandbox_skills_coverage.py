from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "k8s" / "images"


REQUIRED_SKILLS: dict[str, set[str]] = {
    "amicable-sandbox": {"sandbox-basics", "sandbox-preview-contract"},
    "amicable-sandbox-lovable-vite": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "react-vite-basics",
        "tanstack-query",
        "hasura-graphql-client",
    },
    "amicable-sandbox-nextjs15": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "nextjs-basics",
        "hasura-graphql-client",
    },
    "amicable-sandbox-remix": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "remix-basics",
        "hasura-graphql-client",
    },
    "amicable-sandbox-nuxt3": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "nuxt-basics",
        "hasura-graphql-client",
    },
    "amicable-sandbox-sveltekit": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "sveltekit-basics",
        "hasura-graphql-client",
    },
    "amicable-sandbox-fastapi": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "fastapi-basics",
    },
    "amicable-sandbox-hono": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "hono-basics",
    },
    "amicable-sandbox-laravel": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "laravel-basics",
        "hasura-db-proxy",
        "hasura-graphql-client",
    },
    "amicable-sandbox-flutter": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "flutter-basics",
    },
    "amicable-sandbox-phoenix": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "phoenix-basics",
    },
    "amicable-sandbox-aspnetcore": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "aspnetcore-basics",
    },
    "amicable-sandbox-quarkus": {
        "sandbox-basics",
        "sandbox-preview-contract",
        "quarkus-basics",
    },
}

DB_ENABLED_IMAGES = {
    "amicable-sandbox-lovable-vite",
    "amicable-sandbox-nextjs15",
    "amicable-sandbox-remix",
    "amicable-sandbox-nuxt3",
    "amicable-sandbox-sveltekit",
    "amicable-sandbox-laravel",
}

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
WHEN_TO_USE_RE = re.compile(r"^##\s+When To Use\b", re.MULTILINE)
VERIFY_RE = re.compile(r"^##\s+(Verify|Verification|QA)\b", re.MULTILINE)


def _skill_files_for_image(image: str) -> list[Path]:
    root = IMAGES_DIR / image / ".deepagents" / "skills"
    return sorted(root.glob("*/SKILL.md"))


def _skill_dirs_for_image(image: str) -> set[str]:
    return {p.parent.name for p in _skill_files_for_image(image)}


def _parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise AssertionError(f"missing frontmatter in {path}")
    out: dict[str, str] = {}
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def test_required_skills_present_per_image() -> None:
    for image, required in REQUIRED_SKILLS.items():
        present = _skill_dirs_for_image(image)
        missing = sorted(required - present)
        assert not missing, f"{image} missing required skills: {missing}"


def test_db_enabled_images_have_hasura_graphql_client() -> None:
    for image in DB_ENABLED_IMAGES:
        present = _skill_dirs_for_image(image)
        assert "hasura-graphql-client" in present, (
            f"{image} must include hasura-graphql-client"
        )


def test_all_skill_frontmatter_and_sections() -> None:
    all_files = sorted(IMAGES_DIR.glob("*/.deepagents/skills/*/SKILL.md"))
    assert all_files, "no sandbox skill files discovered"

    for path in all_files:
        text = path.read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(path)

        for key in ("name", "description", "license"):
            value = (frontmatter.get(key) or "").strip()
            assert value, f"{path} missing required frontmatter key: {key}"

        assert WHEN_TO_USE_RE.search(text), f"{path} missing '## When To Use' section"
        assert VERIFY_RE.search(text), (
            f"{path} missing verification section (expected ## Verify/## Verification/## QA)"
        )


def test_no_duplicate_frontmatter_skill_name_per_image() -> None:
    for image in REQUIRED_SKILLS:
        seen: dict[str, Path] = {}
        for path in _skill_files_for_image(image):
            name = (_parse_frontmatter(path).get("name") or "").strip()
            assert name, f"{path} has empty skill frontmatter name"
            if name in seen:
                raise AssertionError(
                    f"duplicate skill frontmatter name '{name}' in {image}: "
                    f"{seen[name]} and {path}"
                )
            seen[name] = path
