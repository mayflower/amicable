FROM mcr.microsoft.com/dotnet/sdk:8.0

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-aspnetcore/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# App workspace
WORKDIR /app
COPY k8s/images/amicable-sandbox-aspnetcore/app/ /app/
RUN dotnet restore

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-aspnetcore/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-aspnetcore/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-aspnetcore/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-aspnetcore/runtime.py ./runtime.py

# Use polling watcher mode so hot reload remains reliable in containerized filesystems.
ENV DOTNET_USE_POLLING_FILE_WATCHER=1
ENV AMICABLE_PREVIEW_CMD="dotnet watch run --urls http://0.0.0.0:3000"

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
