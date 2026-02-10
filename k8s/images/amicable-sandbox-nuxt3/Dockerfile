FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-nuxt3/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app.
WORKDIR /app
ENV CI=1
RUN npx -y nuxi@latest init /app \
  --template minimal \
  --package-manager npm \
  --no-install \
  --no-git-init \
  --force \
  && npm install \
  && npm install @nuxtjs/tailwindcss

# Pre-wire the base app with DB proxy wiring (Hasura via agent).
COPY k8s/images/amicable-sandbox-nuxt3/overlay/ /app/

# Pre-wire Hasura DB proxy integration for the Nuxt template.
# The agent will overwrite /public/amicable-db.js with real credentials when Hasura is configured.
RUN python3 - <<'PY'
import re
from pathlib import Path

db_js = Path("/app/public/amicable-db.js")
if not db_js.exists():
    db_js.write_text(
        "window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n",
        encoding="utf-8",
    )

cfg = Path("/app/nuxt.config.ts")
if cfg.exists():
    text = cfg.read_text(encoding="utf-8", errors="replace")
    if "/amicable-db.js" not in text:
        # Best-effort insert into defineNuxtConfig({ ... }).
        m = re.search(r"defineNuxtConfig\(\s*\{", text)
        if not m:
            text = text + '\n\nexport default defineNuxtConfig({ app: { head: { script: [{ src: "/amicable-db.js" }] } } });\n'
        elif re.search(r"\bapp\s*:\s*\{", text):
            # Insert a head.script if missing (simple heuristic).
            if re.search(r"\bhead\s*:\s*\{", text):
                text = re.sub(
                    r"(\bhead\s*:\s*\{)",
                    r'\1\n      script: [{ src: "/amicable-db.js" }],',
                    text,
                    count=1,
                )
            else:
                text = re.sub(
                    r"(\bapp\s*:\s*\{)",
                    r'\1\n    head: { script: [{ src: "/amicable-db.js" }] },',
                    text,
                    count=1,
                )
        else:
            insert = (
                "\n  app: {\n"
                "    head: {\n"
                '      script: [{ src: "/amicable-db.js" }],\n'
                "    },\n"
                "  },"
            )
            text = text[: m.end()] + insert + text[m.end() :]
        cfg.write_text(text, encoding="utf-8")
PY

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-nuxt3/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-nuxt3/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-nuxt3/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-nuxt3/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="npm run dev -- --host 0.0.0.0 --port 3000"

EXPOSE 8888
EXPOSE 3000

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
