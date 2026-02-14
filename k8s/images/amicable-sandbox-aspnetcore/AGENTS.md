# ASP.NET Core Full-Stack App Sandbox

This workspace is an ASP.NET Core starter app intended for AI-driven editing.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `dotnet restore`
- `dotnet watch run --urls http://0.0.0.0:3000` (preview runs on port 3000)
- `dotnet build` / `dotnet test`

## Hot Reload Note
- File watching in virtualized/containerized environments can miss events.
- This template enables polling via `DOTNET_USE_POLLING_FILE_WATCHER=1`.
