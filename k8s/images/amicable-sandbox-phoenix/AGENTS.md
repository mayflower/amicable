# Phoenix Full-Stack App Sandbox

This workspace is a Phoenix starter app intended for AI-driven editing.

## File Editing

- **`write_file` overwrites the target file.** Never use `rm` or `unlink` to delete a file before rewriting it — just call `write_file` directly.
- Prefer `write_file` over `edit_file` when replacing most or all of a file's content.
## Commands (from /app)
- `mix deps.get`
- `mix phx.server` (preview runs on port 3000)
- `mix compile` / `mix test`

## Hot Reload Note
- The template config enables `:fs_poll` for Phoenix live reload to improve reliability in containerized filesystems.
