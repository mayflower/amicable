FROM python:3.12-bookworm

# Install system dependencies for Flutter + runtime API.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    clang \
    cmake \
    curl \
    libglu1-mesa \
    ninja-build \
    pkg-config \
    tini \
    unzip \
    xz-utils \
    zip \
  && rm -rf /var/lib/apt/lists/*

ARG FLUTTER_CHANNEL=stable
ARG FLUTTER_VERSION=3.27.3
ARG FLUTTER_HOME=/opt/flutter

ENV FLUTTER_HOME=${FLUTTER_HOME}
ENV PATH=${FLUTTER_HOME}/bin:${FLUTTER_HOME}/bin/cache/dart-sdk/bin:${PATH}
ENV FLUTTER_SUPPRESS_ANALYTICS=true
ENV CI=true

RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/${FLUTTER_CHANNEL}/linux/flutter_linux_${FLUTTER_VERSION}-${FLUTTER_CHANNEL}.tar.xz" -o /tmp/flutter.tar.xz \
  && mkdir -p /opt \
  && tar -xf /tmp/flutter.tar.xz -C /opt \
  && rm /tmp/flutter.tar.xz \
  && flutter --version \
  && flutter config --enable-web \
  && (flutter --disable-analytics || true)

WORKDIR /runtime
COPY k8s/images/amicable-sandbox-flutter/requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

WORKDIR /app
COPY k8s/images/amicable-sandbox-flutter/app/pubspec.yaml k8s/images/amicable-sandbox-flutter/app/pubspec.lock ./
RUN flutter pub get
COPY k8s/images/amicable-sandbox-flutter/app/ /app/

# Default DeepAgents memory/skills locations.
COPY k8s/images/amicable-sandbox-flutter/AGENTS.md /app/AGENTS.md
COPY k8s/images/amicable-sandbox-flutter/.deepagents/AGENTS.md /app/.deepagents/AGENTS.md
COPY k8s/images/amicable-sandbox-flutter/.deepagents/skills/ /app/.deepagents/skills/

# Runtime API.
WORKDIR /runtime
COPY k8s/images/amicable-sandbox-flutter/runtime.py ./runtime.py

ENV AMICABLE_PREVIEW_CMD="flutter run -d web-server --web-hostname 0.0.0.0 --web-port 3000 --no-dds"

EXPOSE 8888
EXPOSE 3000

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "runtime:app", "--host", "0.0.0.0", "--port", "8888"]
