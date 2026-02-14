# Amicable Sandbox Workspace

This is the template Vite + React + Tailwind workspace that Amicable edits inside the sandbox.

## Useful Commands

- `npm install`
- `npm run dev`
- `npm run build`
- `npm run lint` (if present)
- `npm run typecheck` (if present)

## File Editing

- **`write_file` overwrites the target file.** Never use `rm` or `unlink` to delete a file before rewriting it — just call `write_file` directly.
- Prefer `write_file` over `edit_file` when replacing most or all of a file's content.
## Notes

- The agent service may run lint/typecheck/build to validate changes.
- This file is loaded as "agent memory" by DeepAgents `MemoryMiddleware`.

