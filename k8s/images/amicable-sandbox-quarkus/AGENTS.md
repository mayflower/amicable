# Quarkus Full-Stack App Sandbox

This workspace is a Quarkus starter app intended for AI-driven editing.

## File Editing

- **`write_file` overwrites the target file.** Never use `rm` or `unlink` to delete a file before rewriting it — just call `write_file` directly.
- Prefer `write_file` over `edit_file` when replacing most or all of a file's content.
## Commands (from /app)
- `./mvnw quarkus:dev -Dquarkus.http.host=0.0.0.0 -Dquarkus.http.port=3000` (preview runs on port 3000)
- `./mvnw -q -DskipTests compile`
- `./mvnw -q test`

## Hot Reload Note
- Quarkus dev mode (`quarkus:dev`) is enabled as the preview command for fast edit-feedback loops.
