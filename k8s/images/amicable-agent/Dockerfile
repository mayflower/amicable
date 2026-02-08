FROM python:3.12-slim

WORKDIR /app

# git + rsync are required for GitLab-backed persistence.
RUN apt-get update \
  && apt-get install -y --no-install-recommends git rsync ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY k8s/images/amicable-agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "src.runtimes.ws_server:app", "--host", "0.0.0.0", "--port", "8000"]
