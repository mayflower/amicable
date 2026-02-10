import unittest

from src.platform_scaffold.scaffold import (
    ScaffoldContext,
    build_scaffold_context,
    render_catalog_info,
    render_mkdocs_yml,
    render_sonar_properties,
)


class TestPlatformScaffold(unittest.TestCase):
    def _ctx(self, template_id: str) -> ScaffoldContext:
        return build_scaffold_context(
            project_id="96ac6a98-03fa-4d53-b813-67197c32d505",
            template_id=template_id,
            project_name="My Project",
            project_slug="my-project",
            repo_web_url="https://git.example.com/group/my-project",
            branch="main",
            gitlab_base_url="https://git.example.com",
            gitlab_group_path="group",
        )

    def test_catalog_info_includes_required_annotations(self):
        ctx = self._ctx("vite")
        text = render_catalog_info(ctx)
        self.assertIn("backstage.io/techdocs-ref: dir:.", text)
        self.assertIn(
            "backstage.io/source-location: url:https://git.example.com/group/my-project/tree/main/",
            text,
        )
        self.assertIn("sonarqube.org/project-key:", text)

    def test_sonar_project_key_format_is_stable(self):
        ctx = build_scaffold_context(
            project_id="abc-123",
            template_id="vite",
            project_name="My Project",
            project_slug="my-project",
            repo_web_url="",
            branch="main",
            gitlab_base_url="https://git.example.com",
            gitlab_group_path="mygroup",
        )
        props = render_sonar_properties(ctx)
        self.assertIn("sonar.projectKey=mygroup_my-project_abc-123", props)

    def test_sonar_sources_mapping(self):
        cases = {
            "vite": "src",
            "nextjs15": "src",
            "sveltekit": "src",
            "hono": "src",
            "remix": "app",
            "nuxt3": ".",
            "fastapi": "app",
            "laravel": "app,resources,routes",
        }
        for tid, expected in cases.items():
            ctx = self._ctx(tid)
            props = render_sonar_properties(ctx)
            self.assertIn(f"sonar.sources={expected}", props)

    def test_mkdocs_nav_matches_docs_files(self):
        ctx = self._ctx("vite")
        yml = render_mkdocs_yml(ctx)
        self.assertIn("- Overview: index.md", yml)
        self.assertIn("- Development Guide: development.md", yml)
        self.assertIn("- Architecture: architecture.md", yml)
        self.assertIn("- Runbook: runbook.md", yml)

    def test_rendering_is_deterministic(self):
        ctx = self._ctx("nextjs15")
        a1 = render_catalog_info(ctx)
        a2 = render_catalog_info(ctx)
        self.assertEqual(a1, a2)
        b1 = render_sonar_properties(ctx)
        b2 = render_sonar_properties(ctx)
        self.assertEqual(b1, b2)
        c1 = render_mkdocs_yml(ctx)
        c2 = render_mkdocs_yml(ctx)
        self.assertEqual(c1, c2)


if __name__ == "__main__":
    unittest.main()
