# Laravel Full-Stack App Sandbox

This workspace is a Laravel (PHP) starter.

## File Editing

- **`write_file` creates a new file.** It will fail if the file already exists. Use it only for brand-new files.
- **Always prefer `edit_file`** for modifying existing files. Use `edit_file` even when replacing most or all of a file's content.
- Never delete a file and re-create it with `write_file` — use `edit_file` to rewrite it in place.
## Commands (from /app)
- `composer install` (if needed)
- `php artisan serve --host 0.0.0.0 --port 3000` (preview runs on port 3000)
- `php artisan test` (if present)

## Hasura / DB Proxy
- If configured, the agent injects `/public/amicable-db.js` and patches `resources/views/welcome.blade.php` to include `<script src="/amicable-db.js">`.
- The browser can read `window.__AMICABLE_DB__`.

### Using Hasura for persistence (recommended)
If the user asks for a database-backed feature (like a todo list), prefer Hasura via the DB proxy instead of sessions/files/local storage.

In the browser (served from the preview origin), call GraphQL like:
```js
const db = window.__AMICABLE_DB__;
const res = await fetch(db.graphqlUrl, {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "x-amicable-app-key": db.appKey,
  },
  body: JSON.stringify({ query: "{ __typename }" }),
});
console.log(await res.json());
```
