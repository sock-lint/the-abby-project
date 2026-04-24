# ─── Stage 1: build the React bundle ────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Sentry DSN is baked into the React bundle at build time.
ARG VITE_SENTRY_DSN=""
ARG VITE_SENTRY_ENVIRONMENT="production"
ARG VITE_SENTRY_TRACES_SAMPLE_RATE="0.2"
ARG VITE_SENTRY_RELEASE=""
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
ENV VITE_SENTRY_ENVIRONMENT=${VITE_SENTRY_ENVIRONMENT}
ENV VITE_SENTRY_TRACES_SAMPLE_RATE=${VITE_SENTRY_TRACES_SAMPLE_RATE}
ENV VITE_SENTRY_RELEASE=${VITE_SENTRY_RELEASE}

# Sentry Vite Plugin needs these at build time to upload source maps.
# They exist only in this stage — never baked into the final image.
ARG SENTRY_AUTH_TOKEN=""
ARG SENTRY_ORG=""
ARG SENTRY_PROJECT=""
ENV SENTRY_AUTH_TOKEN=${SENTRY_AUTH_TOKEN}
ENV SENTRY_ORG=${SENTRY_ORG}
ENV SENTRY_PROJECT=${SENTRY_PROJECT}

RUN npm run build

# ─── Stage 2: Django + gunicorn, with the built bundle baked in ─────────────
FROM python:3.12-slim

# Coolify injects these build-args automatically; declare so BuildKit doesn't error
ARG COOLIFY_FQDN
ARG POSTGRES_USER
ARG POSTGRES_PASSWORD
ARG POSTGRES_DB
ARG SERVICE_URL_DJANGO
ARG SERVICE_FQDN_DJANGO
ARG COOLIFY_BUILD_SECRETS_HASH

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc libjpeg-dev zlib1g-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pull the built SPA into a directory that STATICFILES_DIRS picks up.
# collectstatic (below) then copies it into STATIC_ROOT for WhiteNoise.
COPY --from=frontend-build /app/frontend/dist /app/frontend_dist

RUN python manage.py collectstatic --noinput

# Run the container as a non-root user for defense-in-depth. /app is
# chowned so migrations + loadrpgcontent + Django logs are writable.
#
# NOTE: docker-compose.yml bind-mounts ./content/rpg/packs over this
# image's copy at runtime. The host-side directory MUST be owned by
# UID 1000 (or world-writable) or the MCP ``write_pack_file`` tool
# will fail with EACCES. On a fresh deploy host:
#   sudo chown -R 1000:1000 /opt/the-abby-project/content/rpg/packs
# --system is intentionally omitted: on Debian it caps IDs at
# SYS_UID_MAX=999 and rejects an explicit --uid 1000.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "config.asgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120"]
