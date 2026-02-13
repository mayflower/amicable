# Flutter App (Web-First) Sandbox

This workspace is a Flutter starter intended for AI-driven editing with live web preview.

## Preview Server — IMPORTANT

The Flutter web dev server is **already running** on port 3000. The runtime manages it automatically.

- **NEVER kill, stop, or restart the Flutter preview process.** If the process is killed the preview will go dark until the runtime auto-restarts it (up to 3 seconds delay). Repeatedly killing it wastes restart budget.
- **NEVER run `flutter run` manually** — the preview server is already running.
- After writing or editing `.dart` files, the Flutter web dev server **automatically detects changes and recompiles** (hot restart). Wait 10–15 seconds for the rebuild to finish before checking the preview.
- If the preview seems stuck or shows stale content, try running `flutter clean && flutter pub get` and then wait — the runtime will auto-restart the dev server.

## Commands (from /app)
- `flutter pub get`
- `flutter clean` (only if dependencies or generated code are in a bad state)

## QA
- `flutter analyze`
- `flutter test` (if present and enabled)

## Project Targets
- `web/` is used for live preview in Amicable.
- `android/` and `ios/` are scaffolded for later native development/export.
