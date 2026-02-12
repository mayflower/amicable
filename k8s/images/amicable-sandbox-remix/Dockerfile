FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-remix/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app.
WORKDIR /tmp
ENV CI=1
RUN npx -y create-react-router@latest /app \
  --template remix-run/react-router-templates/default \
  --package-manager npm \
  --yes \
  --install \
  --no-git-init

# Pre-wire the base app with DB proxy wiring (Hasura via agent).
COPY k8s/images/amicable-sandbox-remix/overlay/ /app/

# Pre-wire Hasura DB proxy integration for the Remix-style template.
# The agent will overwrite /public/amicable-db.js with real credentials when Hasura is configured.
RUN python3 - <<'PY'
from pathlib import Path

db_js = Path("/app/public/amicable-db.js")
if not db_js.exists():
    db_js.write_text(
        "window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n",
        encoding="utf-8",
    )

root = Path("/app/app/root.tsx")
if root.exists():
    text = root.read_text(encoding="utf-8", errors="replace")
    if "/amicable-db.js" not in text:
        tag = '      <script src="/amicable-db.js"></script>\n'
        if "<Scripts" in text:
            text = text.replace("<Scripts", tag + "      <Scripts", 1)
        elif "</head>" in text:
            text = text.replace("</head>", tag + "    </head>", 1)
        else:
            text = text + "\n" + tag
        root.write_text(text, encoding="utf-8")
PY

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-remix/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-remix/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-remix/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-remix/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="npm run dev -- --host 0.0.0.0 --port 3000"

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
