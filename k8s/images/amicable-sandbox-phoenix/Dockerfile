FROM elixir:1.17-bookworm

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-phoenix/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# App workspace
WORKDIR /app
ENV MIX_ENV=dev
RUN mix local.hex --force \
  && mix local.rebar --force \
  && mix archive.install hex phx_new --force \
  && mix phx.new /app --no-ecto --no-dashboard --no-mailer --no-assets --install

# Bind preview server to 0.0.0.0:3000 and use fs_poll for live reload under containerized filesystems.
RUN python3 - <<'PY'
from pathlib import Path

path = Path('/app/config/dev.exs')
text = path.read_text(encoding='utf-8', errors='replace')
text = text.replace(
    'http: [ip: {127, 0, 0, 1}, port: 4000],',
    'http: [ip: {0, 0, 0, 0}, port: 3000],',
)
if 'config :phoenix_live_reload, backend: :fs_poll' not in text:
    text += '\nconfig :phoenix_live_reload, backend: :fs_poll\n'
path.write_text(text, encoding='utf-8')
PY

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-phoenix/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-phoenix/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-phoenix/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-phoenix/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="mix phx.server"

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
