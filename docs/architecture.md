# Architecture

## System Overview

```text
Browser (Editor SPA)
    -> WebSocket
Agent (FastAPI/Uvicorn + DeepAgents Controller)
    -> HTTP (cluster DNS)
Sandbox Pod
    |- Runtime API :8888
    '- Preview Server :3000
```

## Main Components

- Editor SPA (`frontend/`): Chat UI, session state, device preview controls.
- Agent service (`src/runtimes/ws_server.py`): WebSocket protocol and auth endpoints.
- Agent core (`src/agent_core.py`): session orchestration and streamed responses.
- Controller graph (`src/deepagents_backend/controller_graph.py`): edit, QA, self-heal loop, optional git sync.
- Sandbox backend (`src/sandbox_backends/k8s_backend.py`): SandboxClaim lifecycle and preview URL construction.

## Runtime Request Flow

1. Client sends `init`.
2. Agent creates or reuses sandbox session.
3. Client sends `user`.
4. Controller graph runs DeepAgents edit step.
5. QA runs deterministic checks (`lint`, `typecheck`, `build` if available).
6. On failure, graph loops with self-heal prompt until max rounds.
7. Final response is streamed to client.

## WebSocket Protocol

Message shape:

```json
{ "type": "<type>", "data": {}, "id": "...", "session_id": "..." }
```

Common message types:

- `init`
- `user`
- `agent_partial`
- `agent_final`
- `update_file`
- `update_in_progress`
- `update_completed`
- `trace_event`
- `hitl_request`
- `hitl_response`

## Safety Model

- Policy wrapper blocks dangerous paths/commands.
- HITL approval can interrupt destructive operations.
- Sandboxes isolate project execution from the agent service.

## Related Docs

- [Configuration](configuration.md)
- [Deployment](deployment.md)
- [Operations](operations.md)
