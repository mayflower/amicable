FROM php:8.3-cli-bookworm

# Install system deps: python for runtime API, node/npm for Laravel tooling, git/curl for scaffolding.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     python3 python3-pip git curl ca-certificates unzip \
  && rm -rf /var/lib/apt/lists/*

# Install Node 20 (for Laravel's package.json tooling)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get update \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# Install composer
RUN curl -fsSL https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-laravel/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Bake the workspace template into /app.
WORKDIR /app
ENV COMPOSER_ALLOW_SUPERUSER=1
RUN composer create-project laravel/laravel /app \
  && npm install

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-laravel/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-laravel/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-laravel/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-laravel/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="php artisan serve --host 0.0.0.0 --port 3000"

EXPOSE 8888
EXPOSE 3000

CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
