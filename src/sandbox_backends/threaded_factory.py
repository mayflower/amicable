"""Factory for per-thread sandbox isolation with DeepAgents.

Provides create_threaded_backend_factory() which reads the thread_id from the
LangGraph configurable and delegates to ThreadedSandboxManager for per-thread
sandbox isolation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.sandbox_backends.thread_manager import ThreadedSandboxManager

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.deepagents_backend.k8s_runtime_backend import K8sSandboxRuntimeBackend

logger = logging.getLogger(__name__)


def create_threaded_backend_factory(
    manager: ThreadedSandboxManager | None = None,
    template_name: str | None = None,
    **kwargs: Any,
) -> Callable[[Any], K8sSandboxRuntimeBackend]:
    """Create a BackendFactory that provides per-thread sandbox isolation.

    This factory reads the thread_id from the LangGraph config and uses a
    ThreadedSandboxManager to provide isolated sandboxes per conversation thread.
    Each thread gets its own sandbox with persistent filesystem.

    Usage:
        from deepagents import create_deep_agent
        from langgraph.checkpoint.memory import MemorySaver
        from src.sandbox_backends.thread_manager import ThreadedSandboxManager
        from src.sandbox_backends.threaded_factory import create_threaded_backend_factory

        manager = ThreadedSandboxManager(
            idle_ttl=timedelta(hours=1),
        )

        agent = create_deep_agent(
            model=model,
            backend=create_threaded_backend_factory(manager=manager),
            checkpointer=MemorySaver(),
        )

        # Same thread = same sandbox (filesystem persists)
        agent.invoke(msg1, config={"configurable": {"thread_id": "user-123"}})
        agent.invoke(msg2, config={"configurable": {"thread_id": "user-123"}})

        # Different thread = different sandbox
        agent.invoke(msg3, config={"configurable": {"thread_id": "user-456"}})

        manager.close()

    Args:
        manager: Optional ThreadedSandboxManager instance. If not provided,
            one will be created (but you won't have lifecycle control).
        template_name: Name of the SandboxTemplate to claim. Only used when
            creating an implicit manager.
        **kwargs: Additional arguments passed to ThreadedSandboxManager when
            creating an implicit manager.

    Returns:
        A factory callable that accepts a ToolRuntime and returns a
        K8sSandboxRuntimeBackend for the current thread.
    """
    _manager = manager
    if _manager is None:
        _manager = ThreadedSandboxManager(
            template_name=template_name,
            **kwargs,
        )

    def factory(runtime: Any) -> K8sSandboxRuntimeBackend:
        config = getattr(runtime, "config", {}) or {}
        configurable = config.get("configurable", {}) or {}
        thread_id = configurable.get("thread_id", "default-thread")

        logger.debug("Creating backend for thread_id: %s", thread_id)
        return _manager.get_backend(thread_id)

    return factory
