FROM php:8.4-cli-bookworm

# Install system deps: python for runtime API, node/npm for Laravel tooling.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     python3 python3-pip curl ca-certificates unzip tini \
  && rm -rf /var/lib/apt/lists/*

# Install Node 20 (for Laravel tooling)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get update \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# Install Composer (pinned major line)
COPY --from=composer:2.8 /usr/bin/composer /usr/local/bin/composer

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-laravel/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

WORKDIR /app
ENV COMPOSER_ALLOW_SUPERUSER=1
COPY k8s/images/amicable-sandbox-laravel/app/composer.json k8s/images/amicable-sandbox-laravel/app/composer.lock ./
COPY k8s/images/amicable-sandbox-laravel/app/package.json k8s/images/amicable-sandbox-laravel/app/package-lock.json ./
RUN composer install --no-interaction --prefer-dist --no-progress --no-scripts \
  && npm ci
COPY k8s/images/amicable-sandbox-laravel/app/ /app/
RUN composer install --no-interaction --prefer-dist --no-progress
COPY k8s/images/amicable-sandbox-laravel/overlay/ /app/

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

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
