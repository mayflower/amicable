FROM node:20-bookworm

# Install Python for the runtime API and app.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-fastapi/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# App workspace
WORKDIR /app
COPY k8s/images/amicable-sandbox-fastapi/app/ /app/
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Pre-wire Hasura DB proxy integration for the FastAPI template.
# The agent will overwrite /amicable-db.js with real credentials when Hasura is configured.
RUN python3 - <<'PY'
from pathlib import Path

db_js = Path("/app/amicable-db.js")
if not db_js.exists():
    db_js.write_text(
        "window.__AMICABLE_DB__ = window.__AMICABLE_DB__ || null;\n",
        encoding="utf-8",
    )
PY

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-fastapi/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-fastapi/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-fastapi/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-fastapi/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload"

EXPOSE 8888
EXPOSE 3000

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
