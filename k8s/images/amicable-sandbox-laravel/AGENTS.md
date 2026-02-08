# Laravel Full-Stack App Sandbox

This workspace is a Laravel (PHP) starter.

## Commands (from /app)
- `composer install` (if needed)
- `php artisan serve --host 0.0.0.0 --port 3000` (preview runs on port 3000)
- `php artisan test` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and patches `resources/views/welcome.blade.php` to include `<script src="/amicable-db.js">`.
- The browser can read `window.__AMICABLE_DB__`.
