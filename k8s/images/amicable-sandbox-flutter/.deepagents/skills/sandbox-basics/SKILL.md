---
name: sandbox-basics
description: Quick reference for Flutter sandbox workflow.
license: MIT
---

# Sandbox Basics

## When To Use
- You are editing the Flutter sandbox template.
- You need deterministic Flutter checks in the web-first sandbox.

## Checklist
- Install/update dependencies with `flutter pub get` when needed.
- Prefer deterministic QA: `flutter analyze`.
- Run `flutter test` when tests exist or were requested.

## Verify
- Run `flutter analyze` and ensure no errors.
- Run `flutter test` when applicable.
- Confirm preview runs on web server port `3000`.
