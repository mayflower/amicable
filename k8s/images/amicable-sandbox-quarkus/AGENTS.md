# Quarkus Full-Stack App Sandbox

This workspace is a Quarkus starter app intended for AI-driven editing.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `./mvnw quarkus:dev -Dquarkus.http.host=0.0.0.0 -Dquarkus.http.port=3000` (preview runs on port 3000)
- `./mvnw -q -DskipTests compile`
- `./mvnw -q test`

## Hot Reload Note
- Quarkus dev mode (`quarkus:dev`) is enabled as the preview command for fast edit-feedback loops.
