FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUBLEDGER_CONFIG=/app/config/config.toml \
    SUBLEDGER_STATIC_DIR=/app/static

WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
RUN pip install --no-cache-dir .
COPY backend/alembic.ini ./
COPY backend/docker/entrypoint.sh ./docker/entrypoint.sh
COPY --from=frontend-build /build/frontend/dist ./static
RUN chmod +x ./docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
