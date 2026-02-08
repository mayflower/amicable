from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langgraph.types import interrupt

if TYPE_CHECKING:  # pragma: no cover
    from langgraph.runtime import Runtime


_DESTRUCTIVE_DB_TOOLS = {"db_drop_table", "db_truncate_table"}


class DangerousDbHitlMiddleware(AgentMiddleware):
    """Interrupt before destructive DB tool calls (drop/truncate)."""

    def after_model(
        self, state: AgentState[Any], _runtime: Runtime[Any] | None = None
    ) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        if not messages:
            return None

        last_ai_msg = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)), None
        )
        if not last_ai_msg or not getattr(last_ai_msg, "tool_calls", None):
            return None

        action_requests: list[dict[str, Any]] = []
        review_configs: list[dict[str, Any]] = []
        interrupt_indices: list[int] = []

        for idx, tool_call in enumerate(last_ai_msg.tool_calls):
            name = tool_call.get("name")
            if name not in _DESTRUCTIVE_DB_TOOLS:
                continue
            args = tool_call.get("args") or {}
            if not isinstance(args, dict):
                continue

            action_requests.append(
                {
                    "name": name,
                    "args": args,
                    "description": (
                        "Destructive database operation requires approval.\n\n"
                        f"Tool: {name}\nArgs: {json.dumps(args, indent=2, sort_keys=True)}"
                    ),
                }
            )
            review_configs.append(
                {
                    "action_name": name,
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            )
            interrupt_indices.append(idx)

        if not action_requests:
            return None

        hitl_request = {
            "action_requests": action_requests,
            "review_configs": review_configs,
        }
        decisions = interrupt(hitl_request)["decisions"]
        if len(decisions) != len(interrupt_indices):
            raise ValueError(
                "Number of HITL decisions does not match interrupted tool calls"
            )

        revised_tool_calls: list[ToolCall] = []
        artificial_tool_messages: list[ToolMessage] = []
        decision_idx = 0

        for idx, tool_call in enumerate(last_ai_msg.tool_calls):
            if idx not in interrupt_indices:
                revised_tool_calls.append(tool_call)
                continue

            decision = decisions[decision_idx]
            decision_idx += 1
            dtype = decision.get("type")

            if dtype == "approve":
                revised_tool_calls.append(tool_call)
                continue

            if dtype == "edit":
                edited = decision.get("edited_action") or {}
                name = edited.get("name")
                args = edited.get("args")
                if not isinstance(name, str) or not isinstance(args, dict):
                    raise ValueError("Invalid HITL edit decision payload")
                revised_tool_calls.append(
                    ToolCall(
                        type="tool_call",
                        name=name,
                        args=args,
                        id=tool_call.get("id"),
                    )
                )
                continue

            if dtype == "reject":
                msg = decision.get("message") or (
                    f"User rejected the tool call for `{tool_call.get('name')}` with id {tool_call.get('id')}"
                )
                artificial_tool_messages.append(
                    ToolMessage(
                        content=str(msg),
                        name=str(tool_call.get("name") or "db"),
                        tool_call_id=str(tool_call.get("id") or ""),
                        status="error",
                    )
                )
                continue

            raise ValueError(f"Unexpected HITL decision type: {dtype!r}")

        last_ai_msg.tool_calls = revised_tool_calls
        return {"messages": [last_ai_msg, *artificial_tool_messages]}

    async def aafter_model(
        self, state: AgentState[Any], runtime: Runtime[Any] | None = None
    ) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
