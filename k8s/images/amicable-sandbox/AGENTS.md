# Amicable Sandbox Workspace

This is the template Vite + React + Tailwind workspace that Amicable edits inside the sandbox.

## Useful Commands

- `npm install`
- `npm run dev`
- `npm run build`
- `npm run lint` (if present)
- `npm run typecheck` (if present)

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Notes

- The agent service may run lint/typecheck/build to validate changes.
- This file is loaded as "agent memory" by DeepAgents `MemoryMiddleware`.

