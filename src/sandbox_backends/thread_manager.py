"""Thread-aware sandbox management for multi-tenant chat applications.

This module provides ThreadedSandboxManager, which maps conversation thread IDs
to isolated sandbox environments with persistent filesystems.

Adapted from the generic agent-sandbox ThreadedSandboxManager to use Amicable's
K8s backend classes (K8sAgentSandboxBackend for claim lifecycle,
K8sSandboxRuntimeBackend for DeepAgents backend protocol).
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from datetime import timedelta  # noqa: TC003
from typing import Any

from src.deepagents_backend.k8s_runtime_backend import K8sSandboxRuntimeBackend
from src.sandbox_backends.k8s_backend import K8sAgentSandboxBackend

logger = logging.getLogger(__name__)


class ThreadedSandboxManager:
    """Maps thread_id to sandbox with lifecycle management.

    Provides per-thread sandbox isolation for chat applications where each
    conversation thread needs its own isolated execution environment with
    persistent filesystem.

    Thread Safety:
        This class is thread-safe. Multiple threads can call get_backend()
        and delete_thread() concurrently.

    Usage:
        manager = ThreadedSandboxManager(
            idle_ttl=timedelta(hours=1),
        )

        # Same thread = same sandbox (filesystem persists)
        backend1 = manager.get_backend("user-123")
        backend1.execute("echo 'hello' > /app/state.txt")

        # Later call with same thread_id reuses the sandbox
        backend2 = manager.get_backend("user-123")
        result = backend2.execute("cat /app/state.txt")

        # Different thread = different sandbox
        backend3 = manager.get_backend("user-456")

        # Cleanup
        manager.delete_thread("user-123")
        manager.close()
    """

    def __init__(
        self,
        template_name: str | None = None,
        idle_ttl: timedelta | None = None,
        claim_prefix: str = "thread",
        root_dir: str | None = None,
        request_timeout_s: int | None = None,
        exec_timeout_s: int | None = None,
    ) -> None:
        self.template_name = template_name  # None → K8sAgentSandboxBackend default
        self.idle_ttl = idle_ttl
        self.claim_prefix = claim_prefix
        self._root_dir = (root_dir or os.environ.get("SANDBOX_ROOT_DIR") or "/app").strip() or "/app"
        self._request_timeout_s = request_timeout_s or int(os.environ.get("SANDBOX_REQUEST_TIMEOUT_S") or "60")
        self._exec_timeout_s = exec_timeout_s or int(os.environ.get("SANDBOX_EXEC_TIMEOUT_S") or "600")

        # Reuse the existing K8s backend for claim lifecycle (create/wait/delete).
        self._k8s_backend = K8sAgentSandboxBackend()

        # Thread-safe storage
        self._lock = threading.RLock()
        self._backends: dict[str, K8sSandboxRuntimeBackend] = {}
        self._sandbox_ids: dict[str, str] = {}  # thread_id → claim_name
        self._last_access: dict[str, float] = {}

    def _generate_claim_name(self, thread_id: str) -> str:
        """Generate a deterministic claim name from thread_id.

        Uses SHA-256 hash (first 12 hex chars) to ensure valid Kubernetes
        resource naming while maintaining deterministic mapping from thread_id.
        """
        hash_suffix = hashlib.sha256(thread_id.encode()).hexdigest()[:12]
        return f"{self.claim_prefix}-{hash_suffix}"

    def get_backend(self, thread_id: str) -> K8sSandboxRuntimeBackend:
        """Get or create a backend for the given thread_id.

        If a sandbox already exists for this thread_id, returns the existing
        backend. Otherwise, creates a new sandbox and returns its backend.

        The sandbox's filesystem persists across calls with the same thread_id.
        """
        with self._lock:
            self._last_access[thread_id] = time.time()

            if thread_id in self._backends:
                logger.debug("Reusing existing sandbox for thread '%s'", thread_id)
                return self._backends[thread_id]

            claim_name = self._generate_claim_name(thread_id)
            logger.info(
                "Creating sandbox for thread '%s' (claim: %s)", thread_id, claim_name
            )

            # Use K8sAgentSandboxBackend to create the claim and wait for readiness.
            env = self._k8s_backend.create_app_environment(
                session_id=thread_id,
                template_name=self.template_name,
                slug=claim_name,
            )
            sandbox_id = str(env["sandbox_id"])

            host = f"{sandbox_id}.{self._k8s_backend.namespace}.svc.cluster.local"
            runtime_base_url = f"http://{host}:{self._k8s_backend.runtime_port}"

            backend = K8sSandboxRuntimeBackend(
                sandbox_id=sandbox_id,
                base_url=runtime_base_url,
                root_dir=self._root_dir,
                request_timeout_s=self._request_timeout_s,
                exec_timeout_s=self._exec_timeout_s,
            )

            self._backends[thread_id] = backend
            self._sandbox_ids[thread_id] = sandbox_id
            logger.info("Sandbox ready for thread '%s' (id: %s)", thread_id, sandbox_id)
            return backend

    def delete_thread(self, thread_id: str) -> bool:
        """Delete the sandbox for a specific thread.

        Cleans up the sandbox pod and associated resources. The thread's
        filesystem will be lost.
        """
        with self._lock:
            if thread_id not in self._sandbox_ids:
                logger.warning("No sandbox found for thread '%s'", thread_id)
                return False

            sandbox_id = self._sandbox_ids.pop(thread_id)
            self._backends.pop(thread_id, None)
            self._last_access.pop(thread_id, None)

        logger.info("Deleting sandbox for thread '%s' (claim: %s)", thread_id, sandbox_id)
        try:
            return self._k8s_backend.delete_app_environment(
                session_id=thread_id, slug=sandbox_id
            )
        except Exception:
            logger.error(
                "Failed to delete sandbox for thread '%s' (claim: %s). "
                "Manual cleanup may be required.",
                thread_id,
                sandbox_id,
                exc_info=True,
            )
            return False

    def cleanup_idle(self) -> int:
        """Clean up sandboxes that have been idle longer than idle_ttl.

        Only has effect if idle_ttl was set during initialization.
        Call this method periodically to clean up idle sandboxes.
        """
        if self.idle_ttl is None:
            return 0

        cutoff = time.time() - self.idle_ttl.total_seconds()
        threads_to_cleanup = []

        with self._lock:
            for thread_id, last_access in list(self._last_access.items()):
                if last_access < cutoff:
                    threads_to_cleanup.append(thread_id)

        cleaned = 0
        failed = []
        for thread_id in threads_to_cleanup:
            logger.info("Cleaning up idle sandbox for thread '%s'", thread_id)
            if self.delete_thread(thread_id):
                cleaned += 1
            else:
                failed.append(thread_id)

        if failed:
            logger.warning(
                "Failed to clean up %d idle sandbox(es): %s",
                len(failed),
                failed,
            )

        return cleaned

    def list_threads(self) -> list[str]:
        """List all active thread IDs."""
        with self._lock:
            return list(self._backends.keys())

    def close(self) -> None:
        """Clean up all sandboxes.

        Should be called when shutting down the application.
        """
        with self._lock:
            thread_ids = list(self._sandbox_ids.keys())

        logger.info(
            "Closing ThreadedSandboxManager, cleaning up %d sandboxes", len(thread_ids)
        )

        failed = []
        for thread_id in thread_ids:
            if not self.delete_thread(thread_id):
                failed.append(thread_id)

        if failed:
            logger.error(
                "Failed to clean up %d sandbox(es): %s. "
                "These may need manual cleanup via kubectl.",
                len(failed),
                failed,
            )

    def __enter__(self) -> ThreadedSandboxManager:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
