# ASP.NET Core Full-Stack App Sandbox

This workspace is an ASP.NET Core starter app intended for AI-driven editing.

## File Editing

- **`write_file` overwrites the target file.** Never use `rm` or `unlink` to delete a file before rewriting it — just call `write_file` directly.
- Prefer `write_file` over `edit_file` when replacing most or all of a file's content.
## Commands (from /app)
- `dotnet restore`
- `dotnet watch run --urls http://0.0.0.0:3000` (preview runs on port 3000)
- `dotnet build` / `dotnet test`

## Hot Reload Note
- File watching in virtualized/containerized environments can miss events.
- This template enables polling via `DOTNET_USE_POLLING_FILE_WATCHER=1`.
