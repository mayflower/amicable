# Flutter App (Web-First) Sandbox

This workspace is a Flutter starter intended for AI-driven editing with live web preview.

## Preview Server — IMPORTANT

The Flutter web dev server is **already running** on port 3000. The runtime manages it automatically.

- **NEVER kill, stop, or restart the Flutter preview process.** If the process is killed the preview will go dark until the runtime auto-restarts it (up to 3 seconds delay). Repeatedly killing it wastes restart budget.
- **NEVER run `flutter run` manually** — the preview server is already running.
- After writing or editing files, the runtime **automatically triggers a Flutter hot restart**. Do **NOT** run `sleep` commands to wait for compilation — just continue with the next edit or task.
- If the preview seems stuck or shows stale content, try running `flutter clean && flutter pub get` — the runtime will auto-restart the dev server. Do **NOT** use `sleep` to wait.

## File Editing — IMPORTANT

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `flutter pub get`
- `flutter clean` (only if dependencies or generated code are in a bad state)

## QA
- `flutter analyze`
- `flutter test` (if present and enabled)

## Project Targets
- `web/` is used for live preview in Amicable.
- `android/` and `ios/` are scaffolded for later native development/export.
