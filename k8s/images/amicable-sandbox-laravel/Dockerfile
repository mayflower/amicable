FROM php:8.3-cli-bookworm

# Install system deps: python for runtime API, node/npm for Laravel tooling, git/curl for scaffolding.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     python3 python3-pip git curl ca-certificates unzip tini \
  && rm -rf /var/lib/apt/lists/*

# Install Node 20 (for Laravel's package.json tooling)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get update \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# Install composer
RUN curl -fsSL https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-laravel/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app.
WORKDIR /app
ENV COMPOSER_ALLOW_SUPERUSER=1
RUN composer create-project laravel/laravel /app \
  && npm install

# Pre-wire the base app with DB proxy wiring (Hasura via agent).
COPY k8s/images/amicable-sandbox-laravel/overlay/ /app/

# Pre-wire Hasura DB proxy integration for the Laravel template.
# The agent will overwrite /public/amicable-db.js with real credentials when Hasura is configured.
RUN python3 - <<'PY'
from pathlib import Path

# Placeholder asset served at /amicable-db.js.
db_js = Path("/app/public/amicable-db.js")
if not db_js.exists():
    db_js.write_text(
        "window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n",
        encoding="utf-8",
    )

# Ensure the default welcome page includes the script tag (idempotent).
welcome = Path("/app/resources/views/welcome.blade.php")
if welcome.exists():
    text = welcome.read_text(encoding="utf-8", errors="replace")
    if "/amicable-db.js" not in text:
        tag = '    <script src="/amicable-db.js"></script>\n'
        if "</head>" in text:
            text = text.replace("</head>", tag + "</head>", 1)
        else:
            text = text + "\n" + tag
        welcome.write_text(text, encoding="utf-8")
PY

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-laravel/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-laravel/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-laravel/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-laravel/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="php artisan serve --host 0.0.0.0 --port 3000"

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
