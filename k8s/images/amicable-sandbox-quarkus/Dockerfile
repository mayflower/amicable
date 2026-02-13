FROM maven:3.9.9-eclipse-temurin-21

# Install Python for the runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates tini \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-quarkus/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# App workspace
WORKDIR /app
COPY k8s/images/amicable-sandbox-quarkus/app/ /app/
RUN mvn -N wrapper:wrapper \
  && chmod +x /app/mvnw \
  && ./mvnw -q -DskipTests compile

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-quarkus/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-quarkus/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-quarkus/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-quarkus/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="./mvnw quarkus:dev -Dquarkus.http.host=0.0.0.0 -Dquarkus.http.port=3000"

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
