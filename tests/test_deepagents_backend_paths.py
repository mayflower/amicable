import importlib.util
import unittest

import pytest

if importlib.util.find_spec("deepagents") is None or importlib.util.find_spec("requests") is None:
    pytest.skip("deepagents/requests not installed in this environment", allow_module_level=True)

from src.deepagents_backend.k8s_runtime_backend import K8sSandboxRuntimeBackend


class TestDeepAgentsBackendPaths(unittest.TestCase):
    def test_to_internal_maps_under_root(self):
        b = K8sSandboxRuntimeBackend(
            sandbox_id="s",
            base_url="http://example.invalid",
            root_dir="/app",
        )
        self.assertEqual(b._to_internal("/src/App.tsx"), "/app/src/App.tsx")  # type: ignore[attr-defined]

    def test_to_relative_strips_root(self):
        b = K8sSandboxRuntimeBackend(
            sandbox_id="s",
            base_url="http://example.invalid",
            root_dir="/app",
        )
        self.assertEqual(b._to_relative("/src/App.tsx"), "src/App.tsx")  # type: ignore[attr-defined]

    def test_to_public(self):
        b = K8sSandboxRuntimeBackend(
            sandbox_id="s",
            base_url="http://example.invalid",
            root_dir="/app",
        )
        self.assertEqual(b._to_public("/app/src/App.tsx"), "/src/App.tsx")  # type: ignore[attr-defined]

    def test_path_traversal_raises(self):
        b = K8sSandboxRuntimeBackend(
            sandbox_id="s",
            base_url="http://example.invalid",
            root_dir="/app",
        )
        with self.assertRaises(ValueError):
            b._to_internal("/../etc/passwd")  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
