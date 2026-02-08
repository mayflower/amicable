FROM node:20-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates \
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

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
