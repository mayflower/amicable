import re
import unittest

from src.sandbox_backends.k8s_backend import (
    K8sAgentSandboxBackend,
    _dns_safe_claim_name,
    _preview_url,
)


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

    def test_dns_safe_claim_name_uses_slug(self):
        name = _dns_safe_claim_name("session-123", slug="counter-test")
        self.assertEqual(name, "counter-test")

    def test_dns_safe_claim_name_slug_sanitized(self):
        name = _dns_safe_claim_name("session-123", slug="My Cool App!")
        self.assertRegex(name, r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

    def test_dns_safe_claim_name_slug_fallback_on_empty(self):
        a = _dns_safe_claim_name("session-123", slug="")
        b = _dns_safe_claim_name("session-123")
        self.assertEqual(a, b)

    def test_preview_url_format(self):
        url = _preview_url(
            claim_name="amicable-0f3a9c2e",
            base_domain="preview.example.com",
            scheme="https",
        )
        self.assertEqual(url, "https://amicable-0f3a9c2e.preview.example.com/")

    def test_preview_url_strips_dot(self):
        url = _preview_url(
            claim_name="x", base_domain=".preview.example.com", scheme="https"
        )
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

    def test_delete_app_environment_prefers_explicit_claim_name(self):
        class _FakeCustomObjects:
            def __init__(self):
                self.deleted_name = None

            def delete_namespaced_custom_object(self, **kwargs):
                self.deleted_name = kwargs.get("name")

        class _FakeClient:
            class _ApiExceptionError(Exception):
                def __init__(self, status: int):
                    self.status = status

            ApiException = _ApiExceptionError

            class V1DeleteOptions:
                def __init__(self, **_kwargs):
                    pass

        b = K8sAgentSandboxBackend.__new__(K8sAgentSandboxBackend)
        b.namespace = "ns"
        b.custom_objects_api = _FakeCustomObjects()
        b._client = _FakeClient
        b._claim_exists = lambda name: name == "actual-claim"

        ok = b.delete_app_environment(
            session_id="sess-1",
            slug="my-slug",
            claim_name="actual-claim",
        )
        self.assertTrue(ok)
        self.assertEqual(b.custom_objects_api.deleted_name, "actual-claim")

    def test_wait_for_sandbox_ready_passes_on_final_ready_check(self):
        class _FakeWatch:
            def stream(self, **_kwargs):
                return []

            def stop(self):
                return None

        class _FakeCustomObjects:
            def list_namespaced_custom_object(self, **_kwargs):
                return {}

            def get_namespaced_custom_object(self, **_kwargs):
                return {
                    "status": {
                        "conditions": [
                            {"type": "Ready", "status": "True", "reason": "Running"}
                        ]
                    }
                }

        b = K8sAgentSandboxBackend.__new__(K8sAgentSandboxBackend)
        b.namespace = "ns"
        b.sandbox_ready_timeout_s = 1
        b.custom_objects_api = _FakeCustomObjects()
        b._watch_cls = _FakeWatch

        # Must not raise when final object is Ready.
        b._wait_for_sandbox_ready("claim-1")

    def test_wait_for_sandbox_ready_fast_path_skips_watch(self):
        class _WatchShouldNotBeUsed:
            def __init__(self):
                raise AssertionError("watch should not be created for ready sandbox")

        class _FakeCustomObjects:
            def get_namespaced_custom_object(self, **_kwargs):
                return {
                    "status": {
                        "conditions": [
                            {"type": "Ready", "status": "True", "reason": "WarmPoolReady"}
                        ]
                    }
                }

        b = K8sAgentSandboxBackend.__new__(K8sAgentSandboxBackend)
        b.namespace = "ns"
        b.sandbox_ready_timeout_s = 1
        b.custom_objects_api = _FakeCustomObjects()
        b._watch_cls = _WatchShouldNotBeUsed

        b._wait_for_sandbox_ready("claim-fast")

    def test_wait_for_sandbox_ready_raises_with_condition_summary(self):
        class _FakeWatch:
            def stream(self, **_kwargs):
                return []

            def stop(self):
                return None

        class _FakeCustomObjects:
            def get_namespaced_custom_object(self, **_kwargs):
                return {
                    "status": {
                        "conditions": [
                            {
                                "type": "Ready",
                                "status": "False",
                                "reason": "ImagePullBackOff",
                            }
                        ]
                    }
                }

            def list_namespaced_custom_object(self, **_kwargs):
                return {}

        b = K8sAgentSandboxBackend.__new__(K8sAgentSandboxBackend)
        b.namespace = "ns"
        b.sandbox_ready_timeout_s = 1
        b.custom_objects_api = _FakeCustomObjects()
        b._watch_cls = _FakeWatch

        with self.assertRaises(RuntimeError) as ctx:
            b._wait_for_sandbox_ready("claim-slow")
        self.assertIn("ImagePullBackOff", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
