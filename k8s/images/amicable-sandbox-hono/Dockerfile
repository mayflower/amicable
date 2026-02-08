FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-hono/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# App workspace
WORKDIR /app
COPY k8s/images/amicable-sandbox-hono/app/ /app/
RUN npm install

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-hono/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-hono/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-hono/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-hono/runtime.py ./runtime.py

ENV HOST=0.0.0.0
ENV PORT=3000
ENV AMICABLE_PREVIEW_CMD="npm run dev"

EXPOSE 8888
EXPOSE 3000

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
