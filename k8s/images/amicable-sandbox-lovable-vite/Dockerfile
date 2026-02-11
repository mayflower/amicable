FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-lovable-vite/requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app (mirrors Beam behavior).
WORKDIR /app
RUN git clone https://github.com/beam-cloud/react-vite-shadcn-ui.git /app \
  && rm -f pnpm-lock.yaml \
  && npm install \
  && npm install @tanstack/react-query react-router-dom recharts sonner zod react-hook-form @hookform/resolvers date-fns uuid

# Fix dev-server/HMR config for reverse-proxied previews (avoid `ws://:::3000`).
COPY k8s/images/amicable-sandbox-lovable-vite/fix_vite_config.py /tmp/fix_vite_config.py
RUN python3 /tmp/fix_vite_config.py && rm /tmp/fix_vite_config.py

# Pre-wire the base app with DB proxy wiring (Hasura via agent).
COPY k8s/images/amicable-sandbox-lovable-vite/overlay/ /app/

# Pre-wire Hasura DB proxy integration for the Vite template.
# The agent will overwrite /amicable-db.js with real credentials when Hasura is configured.
RUN python3 - <<'PY'
import re
from pathlib import Path

db_js = Path("/app/amicable-db.js")
if not db_js.exists():
    db_js.write_text(
        "window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n",
        encoding="utf-8",
    )

index_html = Path("/app/index.html")
if index_html.exists():
    text = index_html.read_text(encoding="utf-8", errors="replace")
    changed = False
    if "<title>Amicable Starter</title>" not in text:
        if "<title" in text:
            text = re.sub(
                r"<title[^>]*>.*?</title>",
                "<title>Amicable Starter</title>",
                text,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
        elif "</head>" in text:
            text = text.replace(
                "</head>", "  <title>Amicable Starter</title>\n</head>", 1
            )
        else:
            text = "  <title>Amicable Starter</title>\n" + text
        changed = True
    if "/amicable-db.js" not in text:
        tag = '  <script src="/amicable-db.js"></script>\n'
        if "</head>" in text:
            text = text.replace("</head>", tag + "</head>", 1)
        else:
            text = text + "\n" + tag
        changed = True
    if changed:
        index_html.write_text(text, encoding="utf-8")
PY

# Default DeepAgents memory/skills locations (loaded by the agent service).
COPY k8s/images/amicable-sandbox-lovable-vite/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-lovable-vite/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-lovable-vite/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-lovable-vite/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="npm run dev -- --host 0.0.0.0 --port 3000"

EXPOSE 8888
EXPOSE 3000

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
