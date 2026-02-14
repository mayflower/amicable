FROM elixir:1.18

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip curl ca-certificates tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-phoenix/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

ENV MIX_ENV=dev
WORKDIR /app
COPY k8s/images/amicable-sandbox-phoenix/app/mix.exs k8s/images/amicable-sandbox-phoenix/app/mix.lock ./
COPY k8s/images/amicable-sandbox-phoenix/app/config ./config
RUN mix local.hex --force \
  && mix local.rebar --force \
  && mix deps.get \
  && mix deps.compile
COPY k8s/images/amicable-sandbox-phoenix/app/ /app/
RUN mix compile

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
