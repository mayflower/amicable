# Phoenix Full-Stack App Sandbox

This workspace is a Phoenix starter app intended for AI-driven editing.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `mix deps.get`
- `mix phx.server` (preview runs on port 3000)
- `mix compile` / `mix test`

## Hot Reload Note
- The template config enables `:fs_poll` for Phoenix live reload to improve reliability in containerized filesystems.
