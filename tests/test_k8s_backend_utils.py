import re
import unittest

from src.sandbox_backends.k8s_backend import _dns_safe_claim_name, _preview_url
from src.sandbox_backends.k8s_backend import K8sAgentSandboxBackend


class TestK8sBackendUtils(unittest.TestCase):
    def test_dns_safe_claim_name_is_dns_label(self):
        name = _dns_safe_claim_name("550e8400-e29b-41d4-a716-446655440000")
        self.assertLessEqual(len(name), 63)
        self.assertRegex(name, r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

    def test_dns_safe_claim_name_is_deterministic(self):
        a = _dns_safe_claim_name("session-123")
        b = _dns_safe_claim_name("session-123")
        c = _dns_safe_claim_name("session-124")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_dns_safe_claim_name_sanitizes(self):
        name = _dns_safe_claim_name("SESSION !! WEIRD / ")
        self.assertLessEqual(len(name), 63)
        self.assertTrue(re.match(r"^[a-z0-9-]+$", name))
        self.assertFalse(name.startswith("-"))
        self.assertFalse(name.endswith("-"))

    def test_preview_url_format(self):
        url = _preview_url(claim_name="amicable-0f3a9c2e", base_domain="preview.example.com", scheme="https")
        self.assertEqual(url, "https://amicable-0f3a9c2e.preview.example.com/")

    def test_preview_url_strips_dot(self):
        url = _preview_url(claim_name="x", base_domain=".preview.example.com", scheme="https")
        self.assertEqual(url, "https://x.preview.example.com/")

    def test_create_app_environment_uses_template_name_override(self):
        class _FakeCustomObjects:
            def __init__(self):
                self.created = None

            def create_namespaced_custom_object(self, **kwargs):
                self.created = kwargs.get("body")

        b = K8sAgentSandboxBackend.__new__(K8sAgentSandboxBackend)
        b.namespace = "ns"
        b.template_name = "default-template"
        b.preview_base_domain = "preview.example.com"
        b.preview_scheme = "https"
        b.runtime_port = 8888
        b.preview_port = 3000
        b.sandbox_ready_timeout_s = 1
        b.custom_objects_api = _FakeCustomObjects()
        b._client = None

        # Avoid touching kube APIs.
        b._claim_exists = lambda _name: False
        b._wait_for_sandbox_ready = lambda _name: None

        b.create_app_environment(session_id="session-123", template_name="my-template")
        assert b.custom_objects_api.created is not None
        self.assertEqual(
            b.custom_objects_api.created["spec"]["sandboxTemplateRef"]["name"],
            "my-template",
        )


if __name__ == "__main__":
    unittest.main()
