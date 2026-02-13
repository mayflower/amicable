# Configuration

This page summarizes the main runtime configuration knobs. For exhaustive environment references and deployment examples, see existing deep-dive docs.

## Agent Core

- `DEEPAGENTS_MODEL`: model provider/model identifier.
- `DEEPAGENTS_QA`: enable deterministic QA stage.
- `DEEPAGENTS_QA_TIMEOUT_S`: timeout for each QA command.
- `DEEPAGENTS_QA_COMMANDS`: CSV override for QA commands.
- `DEEPAGENTS_SELF_HEAL_MAX_ROUNDS`: maximum self-heal loops.
- `DEEPAGENTS_MEMORY_SOURCES`: memory file locations loaded into agent context.
- `DEEPAGENTS_SKILLS_SOURCES`: skill directories loaded into agent context.
- `AMICABLE_WEB_TOOLS_ENABLED`: enable Claude-style `WebSearch`/`WebFetch` tools.
- `AMICABLE_WEB_FETCH_MODEL`: model used for `WebFetch(url, prompt)` grounded answers.
- `AMICABLE_WEB_FETCH_TIMEOUT_S`: fetch timeout for `WebFetch` HTTP requests.
- `AMICABLE_WEB_FETCH_MAX_CONTENT_CHARS`: max extracted page chars sent to the fetch-QA model.
- `AMICABLE_WEB_SEARCH_TIMEOUT_S`: timeout for `WebSearch` provider calls.
- `AMICABLE_WEB_SEARCH_MAX_RESULTS`: max normalized `WebSearch` results returned.
- `AMICABLE_WEB_SEARCH_USER_AGENT`: optional User-Agent override for web search/fetch requests.

## Auth and Session

- `AUTH_MODE`: `none` or `google`.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: OAuth credentials.
- `SESSION_SECRET`: cookie/session signing secret.
- `PUBLIC_BASE_URL`: base URL used for callback construction.
- `CORS_ALLOW_ORIGINS`: allowed frontend origins.
- `AUTH_REDIRECT_ALLOW_ORIGINS`: allowed redirect origins.

## Sandbox and Preview Routing

- `K8S_SANDBOX_NAMESPACE`: namespace for SandboxClaims/Sandboxes.
- `K8S_SANDBOX_TEMPLATE_NAME`: default SandboxTemplate.
- `PREVIEW_BASE_DOMAIN`: wildcard preview base domain.
- `PREVIEW_SCHEME`: `https` or `http`.
- `SANDBOX_RUNTIME_PORT`: runtime API port (default `8888`).
- `SANDBOX_PREVIEW_PORT`: preview server port (default `3000`).

## GitLab Sync (Optional)

- `GITLAB_TOKEN`: enables authenticated GitLab operations.
- `AMICABLE_GIT_SYNC_ENABLED`: toggle sync.
- `AMICABLE_GIT_SYNC_REQUIRED`: treat sync as hard requirement.
- `GITLAB_BASE_URL`, `GITLAB_GROUP_PATH`: target GitLab location.
- `AMICABLE_GIT_SYNC_BRANCH`: target branch for commits.

## Hasura DB Integration (Optional)

- `HASURA_BASE_URL`
- `HASURA_GRAPHQL_ADMIN_SECRET`
- `HASURA_GRAPHQL_JWT_SECRET`
- `HASURA_SOURCE_NAME`
- `AMICABLE_PUBLIC_BASE_URL`
- `AMICABLE_DB_PROXY_ORIGIN_MODE`

## Frontend Runtime Config

- `VITE_AGENT_WS_URL`
- `VITE_AGENT_HTTP_URL` (optional; can be derived from WS URL)

For deployed editor images, runtime values can be injected with `window.__AMICABLE_CONFIG__` in `frontend/public/config.js`.

## Related Docs

- [Deployment](deployment.md)
- [Sandbox Configuration](sandbox_config.md)
