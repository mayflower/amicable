---
name: sandbox-basics
description: Quick reference for npm-based Amicable sandbox workflow.
license: MIT
---

# Sandbox Basics

## When To Use
- You are editing an npm-based web template in Amicable.
- You need the standard command order for reliable sandbox feedback.

## Checklist
- Install dependencies first when needed: `npm install`.
- Prefer deterministic QA scripts when available: `npm run -s lint`, `npm run -s typecheck`, `npm run -s build`.
- Keep edits scoped and rerun checks after each meaningful change.

## Verify
- Run all available QA scripts in this order: lint -> typecheck -> build.
- Confirm the preview app still loads after the last successful check.
