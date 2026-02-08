FROM node:20-bookworm AS build

WORKDIR /repo

# Install deps first for better caching
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# Build
COPY frontend ./frontend
RUN cd frontend && npm run build

FROM nginx:1.27-alpine

COPY k8s/images/amicable-editor/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/frontend/dist /usr/share/nginx/html

# Default runtime config (overridden by ConfigMap mount in Kubernetes)
RUN printf '%s\n' 'window.__AMICABLE_CONFIG__={};' > /usr/share/nginx/html/config.js
