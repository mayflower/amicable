# Development Guide

## Prerequisites

- Python 3.12+
- Node.js 20+
- Kubernetes cluster with `agent-sandbox` CRDs (for full runtime path)
- API key for the configured LLM provider (for agent execution)

## Local Setup

```bash
git clone https://github.com/mayflower/amicable
cd amicable
pip install -r requirements.txt

cd frontend
npm install
```

## Run Frontend

```bash
cd frontend
npm run dev
```

By default, the frontend reads `VITE_AGENT_WS_URL` from environment or runtime config (`frontend/public/config.js` in deployed editor image).

## Run Backend Checks

```bash
pytest
python3 -m compileall -q src
ruff check src/
ruff format src/
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

## Codebase Layout

- `src/runtimes/ws_server.py`: FastAPI + WebSocket entrypoint.
- `src/agent_core.py`: session lifecycle and streaming behavior.
- `src/deepagents_backend/`: DeepAgents adapter, controller graph, QA, safety wrappers.
- `src/sandbox_backends/`: Kubernetes sandbox provisioning integration.
- `frontend/src/`: editor UI, transport, message handling.
- `k8s/images/`: container images for agent, editor, and sandbox templates.

## Recommended Developer Workflow

1. Reproduce issue or define the requested behavior.
2. Implement changes in backend/frontend/template as needed.
3. Run targeted checks first, then full lint/build/test.
4. Validate behavior end-to-end via editor + sandbox preview.
5. Update docs when functionality or operations change.

## Related Docs

- [Testing](testing.md)
- [Sandbox Configuration](sandbox_config.md)
- [Local kind Setup](local_kind.md)
