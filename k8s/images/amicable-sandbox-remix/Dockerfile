FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates \
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

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
