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
  && git config --global --add safe.directory /opt/flutter \
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

# Pre-download the Web SDK and warm the DDC compilation cache so that
# the warm-pool pod starts serving the preview in seconds instead of ~30 s.
# 1) Download the Web SDK artifacts at build time.
# 2) Start a throwaway debug server, wait until DDC compiles, then kill it.
#    This populates .dart_tool/ caches that `flutter run` reuses at runtime.
RUN flutter precache --web
RUN sh -c '\
  flutter run -d web-server --web-port 19999 --no-dds & \
  FPID=$! ; \
  for i in $(seq 1 180); do \
    curl -s -o /dev/null http://localhost:19999/ 2>/dev/null && break ; \
    sleep 1 ; \
  done ; \
  kill $FPID 2>/dev/null ; wait $FPID 2>/dev/null || true'

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
