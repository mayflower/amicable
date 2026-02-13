---
name: sandbox-basics
description: Quick reference for Laravel sandbox workflow.
license: MIT
---

# Sandbox Basics

## When To Use
- You are editing the Laravel sandbox template.
- You need deterministic command order before handoff.

## Checklist
- Install dependencies when needed: `composer install` and `npm install`.
- Use deterministic checks: `php artisan test` when tests exist.
- Keep preview compatibility with `php artisan serve --host 0.0.0.0 --port 3000`.

## Verify
- Run tests when available and ensure no regressions.
- Confirm the preview loads and key routes respond.
