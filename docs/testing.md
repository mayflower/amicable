# Testing and Validation

## Backend (Python)

Run all tests:

```bash
pytest
```

Run a single file:

```bash
pytest tests/test_deepagents_qa.py
```

Run a single test by name:

```bash
pytest -k test_name
```

Quick static checks:

```bash
python3 -m compileall -q src
ruff check src/
ruff format src/
```

## Frontend (React/Vite)

```bash
cd frontend
npm run lint
npm run build
```

## QA Loop in Runtime

After DeepAgents edits, controller QA attempts available scripts from sandbox `package.json`:

1. `lint`
2. `typecheck`
3. `build`

Failures can trigger self-heal rounds up to `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS`.

## Suggested Pre-Merge Checklist

1. Run backend tests and lint.
2. Run frontend lint/build.
3. Verify a representative editor workflow end-to-end.
4. Confirm deployment docs/config were updated for behavior changes.

## Related Docs

- [Development](development.md)
- [Operations](operations.md)
