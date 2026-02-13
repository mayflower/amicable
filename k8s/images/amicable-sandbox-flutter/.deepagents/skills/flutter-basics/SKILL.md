---
name: flutter-basics
description: Practical guidance for editing Flutter apps with web-first preview in Amicable.
license: MIT
---

# Flutter Basics

## When To Use
- You are implementing or fixing features in a Flutter app template.

## Guidelines
- Keep primary app logic in `lib/` (usually `lib/main.dart` and feature widgets).
- Preserve platform folders (`android/`, `ios/`, `web/`) unless the task requires changing them.
- Favor composable widgets and avoid deeply nested widget trees when a helper widget improves readability.

## Verify
- Run `flutter analyze` after edits.
- If tests exist or are requested, run `flutter test`.
