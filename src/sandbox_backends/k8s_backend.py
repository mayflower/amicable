from __future__ import annotations

import base64
import hashlib
import os
import re
import time
from typing import Any

CLAIM_API_GROUP = "extensions.agents.x-k8s.io"
CLAIM_API_VERSION = "v1alpha1"
CLAIM_PLURAL_NAME = "sandboxclaims"

SANDBOX_API_GROUP = "agents.x-k8s.io"
SANDBOX_API_VERSION = "v1alpha1"
SANDBOX_PLURAL_NAME = "sandboxes"

DEFAULT_PROJECT_ROOT = "/app"
DEFAULT_CODE_PATH = "/app/src"

_DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _dns_safe_claim_name(session_id: str, *, prefix: str = "amicable") -> str:
    # Deterministic name: prefix + '-' + 8 hex chars.
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]
    name = f"{prefix}-{digest}"
    # Enforce k8s DNS label rules.
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = name.strip("-")
    if len(name) > 63:
        name = name[:63].rstrip("-")

    if not _DNS_LABEL_RE.match(name):
        # As a last resort, fall back to a safe fixed prefix.
        name = f"{prefix}-{digest}"[:63].rstrip("-")

    return name


def _preview_url(*, claim_name: str, base_domain: str, scheme: str) -> str:
    scheme = (scheme or "https").strip()
    base_domain = base_domain.strip().lstrip(".")
    return f"{scheme}://{claim_name}.{base_domain}/"


def _ensure_kube_config_loaded() -> None:
    # In-cluster first; fall back to local kubeconfig (useful for dev).
    from kubernetes import config  # type: ignore

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _sandbox_ready(sandbox_obj: dict[str, Any]) -> bool:
    status = sandbox_obj.get("status", {})
    for cond in status.get("conditions", []) or []:
        if cond.get("type") == "Ready" and cond.get("status") in ("True", True):
            return True
    return False


class K8sAgentSandboxBackend:
    def __init__(self) -> None:
        import requests  # type: ignore
        from kubernetes import client, watch  # type: ignore

        self.namespace = os.environ.get("K8S_SANDBOX_NAMESPACE", "default")
        self.template_name = os.environ.get(
            "K8S_SANDBOX_TEMPLATE_NAME", "amicable-sandbox"
        )
        self.preview_base_domain = os.environ.get("PREVIEW_BASE_DOMAIN")
        self.preview_scheme = os.environ.get("PREVIEW_SCHEME", "https")
        self.runtime_port = _env_int("SANDBOX_RUNTIME_PORT", 8888)
        self.preview_port = _env_int("SANDBOX_PREVIEW_PORT", 3000)

        self.sandbox_ready_timeout_s = _env_int("K8S_SANDBOX_READY_TIMEOUT", 180)

        _ensure_kube_config_loaded()
        self._watch_cls = watch.Watch
        self._client = client
        self.custom_objects_api = client.CustomObjectsApi()

        # requests defaults; keep it simple.
        self._requests = requests
        self._http = requests.Session()

    def create_app_environment(
        self, *, session_id: str, template_name: str | None = None
    ) -> dict:
        if not self.preview_base_domain:
            raise RuntimeError(
                "PREVIEW_BASE_DOMAIN is required for SANDBOX_BACKEND=k8s"
            )

        tmpl = (template_name or self.template_name).strip() or self.template_name
        claim_name = _dns_safe_claim_name(session_id)

        exists = self._claim_exists(claim_name)
        if not exists:
            manifest = {
                "apiVersion": f"{CLAIM_API_GROUP}/{CLAIM_API_VERSION}",
                "kind": "SandboxClaim",
                "metadata": {"name": claim_name},
                "spec": {"sandboxTemplateRef": {"name": tmpl}},
            }
            self.custom_objects_api.create_namespaced_custom_object(
                group=CLAIM_API_GROUP,
                version=CLAIM_API_VERSION,
                namespace=self.namespace,
                plural=CLAIM_PLURAL_NAME,
                body=manifest,
            )

        self._wait_for_sandbox_ready(claim_name)

        preview_url = _preview_url(
            claim_name=claim_name,
            base_domain=self.preview_base_domain,
            scheme=self.preview_scheme,
        )
        return {
            "url": preview_url,
            "sandbox_id": claim_name,
            "exists": exists,
        }

    def delete_app_environment(self, *, session_id: str) -> bool:
        """Delete the SandboxClaim for a session_id (best-effort).

        Returns True if a claim existed and a delete was issued.
        """
        claim_name = _dns_safe_claim_name(session_id)
        if not self._claim_exists(claim_name):
            return False
        try:
            self.custom_objects_api.delete_namespaced_custom_object(
                group=CLAIM_API_GROUP,
                version=CLAIM_API_VERSION,
                namespace=self.namespace,
                plural=CLAIM_PLURAL_NAME,
                name=claim_name,
                body=self._client.V1DeleteOptions(  # type: ignore[attr-defined]
                    propagation_policy="Foreground"
                ),
            )
            return True
        except self._client.ApiException as e:
            if e.status == 404:
                return False
            raise

    def load_code(self, *, sandbox_id: str) -> tuple[dict[str, bytes], str]:
        # sandbox_id is claim_name
        rel_paths = self._list_files(sandbox_id, "src")

        file_map: dict[str, bytes] = {}
        for rel in rel_paths:
            full = f"{DEFAULT_PROJECT_ROOT}/{rel.lstrip('/')}"
            file_map[full] = self._download(sandbox_id, rel)

        package_json = self._download(sandbox_id, "package.json").decode(
            "utf-8", errors="replace"
        )
        return file_map, package_json

    def edit_code(self, *, sandbox_id: str, code_map: dict[str, str]) -> dict:
        # Translate /app/... absolute paths to relative paths under /app.
        for path, content in code_map.items():
            rel = self._to_relative(path)
            self._write_b64(sandbox_id, rel, content.encode("utf-8"))

        return {"sandbox_id": sandbox_id}

    def _claim_exists(self, claim_name: str) -> bool:
        try:
            self.custom_objects_api.get_namespaced_custom_object(
                group=CLAIM_API_GROUP,
                version=CLAIM_API_VERSION,
                namespace=self.namespace,
                plural=CLAIM_PLURAL_NAME,
                name=claim_name,
            )
            return True
        except self._client.ApiException as e:
            if e.status == 404:
                return False
            raise

    def _wait_for_sandbox_ready(self, claim_name: str) -> None:
        w = self._watch_cls()
        start = time.time()

        for event in w.stream(
            func=self.custom_objects_api.list_namespaced_custom_object,
            namespace=self.namespace,
            group=SANDBOX_API_GROUP,
            version=SANDBOX_API_VERSION,
            plural=SANDBOX_PLURAL_NAME,
            field_selector=f"metadata.name={claim_name}",
            timeout_seconds=self.sandbox_ready_timeout_s,
        ):
            obj = event.get("object")
            if not isinstance(obj, dict):
                continue
            if _sandbox_ready(obj):
                w.stop()
                return
            if time.time() - start > self.sandbox_ready_timeout_s:
                w.stop()
                break

        # Final get for error context.
        try:
            sandbox = self.custom_objects_api.get_namespaced_custom_object(
                group=SANDBOX_API_GROUP,
                version=SANDBOX_API_VERSION,
                namespace=self.namespace,
                plural=SANDBOX_PLURAL_NAME,
                name=claim_name,
            )
        except Exception:
            sandbox = None
        raise RuntimeError(
            f"Timed out waiting for sandbox '{claim_name}' to become Ready. Last object: {sandbox}"
        )

    def _runtime_base_url(self, claim_name: str) -> str:
        host = f"{claim_name}.{self.namespace}.svc.cluster.local"
        return f"http://{host}:{self.runtime_port}"

    def _request(self, claim_name: str, method: str, path: str, **kwargs):
        url = f"{self._runtime_base_url(claim_name).rstrip('/')}/{path.lstrip('/')}"
        resp = self._http.request(method, url, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp

    def _list_files(self, claim_name: str, dir_rel: str) -> list[str]:
        # Returns relative file paths under /app (e.g. "src/App.tsx"). Directories are excluded.
        resp = self._request(claim_name, "GET", "list", params={"dir": dir_rel})
        data = resp.json()
        files = data.get("files", [])
        if not isinstance(files, list):
            return []
        out: list[str] = []
        for item in files:
            if isinstance(item, str) and item and not item.endswith("/"):
                out.append(item.lstrip("/"))
        return out

    def _download(self, claim_name: str, rel_path: str) -> bytes:
        rel = rel_path.lstrip("/")
        resp = self._request(claim_name, "GET", f"download/{rel}")
        return resp.content

    def _write_b64(self, claim_name: str, rel_path: str, payload: bytes) -> None:
        rel = rel_path.lstrip("/")
        content_b64 = base64.b64encode(payload).decode("ascii")
        self._request(
            claim_name,
            "POST",
            "write_b64",
            json={"path": rel, "content_b64": content_b64},
        )

    def _to_relative(self, path: str) -> str:
        # Accept absolute /app/... and also already-relative paths.
        p = path.strip()
        if p.startswith(DEFAULT_PROJECT_ROOT + "/"):
            p = p[len(DEFAULT_PROJECT_ROOT) + 1 :]
        p = p.lstrip("/")
        return p
