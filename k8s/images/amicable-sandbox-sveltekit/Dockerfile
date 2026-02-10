FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-sveltekit/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app.
WORKDIR /app
ENV CI=1
RUN npx -y sv@latest create /app \
  --template minimal \
  --types ts \
  --no-add-ons \
  --no-dir-check \
  --install npm

# Pre-wire the base app with DB proxy wiring (Hasura via agent).
COPY k8s/images/amicable-sandbox-sveltekit/overlay/ /app/

# Pre-wire Hasura DB proxy integration for the SvelteKit template.
# The agent will overwrite /static/amicable-db.js with real credentials when Hasura is configured.
RUN python3 - <<'PY'
from pathlib import Path

db_js = Path("/app/static/amicable-db.js")
if not db_js.exists():
    db_js.write_text(
        "window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n",
        encoding="utf-8",
    )

app_html = Path("/app/src/app.html")
if app_html.exists():
    text = app_html.read_text(encoding="utf-8", errors="replace")
    if "/amicable-db.js" not in text:
        tag = '  <script src="/amicable-db.js"></script>\n'
        if "</head>" in text:
            text = text.replace("</head>", tag + "</head>", 1)
        else:
            text = text + "\n" + tag
        app_html.write_text(text, encoding="utf-8")
PY

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-sveltekit/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-sveltekit/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-sveltekit/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-sveltekit/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="npm run dev -- --host 0.0.0.0 --port 3000"

EXPOSE 8888
EXPOSE 3000

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
