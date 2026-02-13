---
name: laravel-basics
description: Execution-ready guidance for Laravel controller and validation workflows.
license: MIT
---

# Laravel Basics

## When To Use
- You are editing the Laravel template.
- You are implementing routes, controllers, views, or API behavior.

## Implementation Rules
- Keep route declarations in `routes/web.php` and `routes/api.php`.
- Keep controllers in `app/Http/Controllers` and move shared business logic into dedicated classes/services.
- Use Laravel validation patterns for request payloads before writing data.
- Keep views/components cohesive and avoid embedding heavy business logic in Blade templates.

## Data Notes
- For browser GraphQL access, use `window.__AMICABLE_DB__` and the DB proxy header (`x-amicable-app-key`).

## Verify
- Run `php artisan test` when tests exist.
- Confirm key routes and modified views render in preview.
- Confirm validated requests return expected status and payload.
