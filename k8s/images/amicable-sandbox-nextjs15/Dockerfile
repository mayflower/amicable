FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-nextjs15/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app.
WORKDIR /app
ENV CI=1
RUN npx -y create-next-app@15 /app \
  --ts \
  --eslint \
  --tailwind \
  --app \
  --src-dir \
  --import-alias "@/*" \
  --use-npm \
  --no-turbo \
  --no-git

# Minimal shadcn-like primitives.
RUN npm install @radix-ui/react-slot class-variance-authority clsx tailwind-merge lucide-react
COPY k8s/images/amicable-sandbox-nextjs15/overlay/ /app/

# Pre-wire Hasura DB proxy integration for the Next.js template.
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

layout_candidates = [Path("/app/app/layout.tsx"), Path("/app/src/app/layout.tsx")]
tag = '        <script src="/amicable-db.js"></script>\n'

for layout in layout_candidates:
    if not layout.exists():
        continue
    text = layout.read_text(encoding="utf-8", errors="replace")
    if "/amicable-db.js" in text:
        break
    if "<head>" in text:
        text = text.replace("<head>", "<head>\n" + tag, 1)
    elif "</head>" in text:
        text = text.replace("</head>", tag + "      </head>", 1)
    else:
        m = re.search(r"<html[^>]*>", text)
        if m:
            head = "      <head>\n" + tag + "      </head>\n"
            text = text[: m.end()] + "\n" + head + text[m.end() :]
        elif "<body" in text:
            text = text.replace("<body", tag + "      <body", 1)
        else:
            text = tag + text
    layout.write_text(text, encoding="utf-8")
    break
PY

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-nextjs15/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-nextjs15/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-nextjs15/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-nextjs15/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="npm run dev -- -H 0.0.0.0 -p 3000"

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
