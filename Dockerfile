# ─── Stage 1: build the React bundle ────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
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

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "config.asgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120"]
