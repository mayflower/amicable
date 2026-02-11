# Usage Guide

## What Amicable Does

Amicable lets users build and iterate on web apps through conversation:

1. User opens the editor and sends a prompt.
2. Agent receives the request over WebSocket.
3. Agent edits files in an isolated sandbox.
4. Deterministic QA validates the result.
5. Updated app appears in the live preview iframe.

## Core User Flow

### 1) Start or Resume Session

- Frontend sends an `init` message.
- Agent ensures sandbox availability and returns `sandbox_id` and preview `url`.

### 2) Prompt the Agent

- Frontend sends `user` messages with natural-language change requests.
- Agent streams `agent_partial` and then `agent_final`.

### 3) Watch File/Action Status

- Agent sends update messages (`update_file`, `update_in_progress`, `update_completed`) to show current work.
- Optional trace events expose tool-call timelines.

### 4) Review the Preview

- Preview runs from sandbox port `3000`, routed by wildcard host.
- Users iterate with additional prompts.

## Human-in-the-Loop (HITL)

Destructive operations can pause execution for approval:

- Server emits `hitl_request`.
- Client answers with `hitl_response`.
- Workflow resumes from checkpoint.

## Typical Personas

- App builders: Use the editor to generate and refine app code quickly.
- Platform engineers: Operate and secure sandboxes, routing, and auth.
- Developers: Extend templates, tooling, and backend capabilities.

## Related Docs

- [Architecture](architecture.md)
- [Development](development.md)
- [Operations](operations.md)
