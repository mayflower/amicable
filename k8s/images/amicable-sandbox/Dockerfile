FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox/requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app (mirrors Beam behavior).
WORKDIR /app
RUN git clone https://github.com/beam-cloud/react-vite-shadcn-ui.git /app \
  && rm -f pnpm-lock.yaml \
  && npm install \
  && npm install @tanstack/react-query react-router-dom recharts sonner zod react-hook-form @hookform/resolvers date-fns uuid

# Fix dev-server/HMR config for reverse-proxied previews (avoid `ws://:::3000`).
COPY k8s/images/amicable-sandbox/fix_vite_config.py /tmp/fix_vite_config.py
RUN python3 /tmp/fix_vite_config.py && rm /tmp/fix_vite_config.py

# Default DeepAgents memory/skills locations (loaded by the agent service).
COPY k8s/images/amicable-sandbox/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox/runtime.py ./runtime.py

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
