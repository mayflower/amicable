---
name: flutter-basics
description: Execution-ready guidance for Flutter web-first sandbox development.
license: MIT
---

# Flutter Basics

## When To Use
- You are implementing or fixing features in the Flutter template.
- You need to keep web preview behavior stable while evolving app code.

## Implementation Rules
- Keep feature logic in `lib/` and split large widgets into focused subwidgets.
- Preserve platform folders unless the task explicitly requires platform-level edits.
- Favor clear state/data flow over deeply nested monolithic widget trees.

## Sandbox Notes
- Preview uses Flutter web-server mode on port `3000`.
- Dependency changes usually require running `flutter pub get`.

## Verify
- Run `flutter analyze`.
- Run `flutter test` when tests exist or were requested.
- Confirm the updated screen/flow works in web preview.
