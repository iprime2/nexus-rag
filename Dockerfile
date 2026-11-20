# syntax=docker/dockerfile:1
#
# Multi-stage build:
#   builder: has uv; resolves and installs dependencies into /app/.venv
#   runtime: only Python + the finished virtualenv; no uv, no build tools,
#            no source tree, runs as an unprivileged user
#
# Build:  docker build -t nexus-rag .
# Run:    docker run --rm -p 127.0.0.1:8000:8000 nexus-rag

ARG PYTHON_IMAGE=python:3.13.18-slim-trixie

# ---------------------------------------------------------------- builder
FROM ${PYTHON_IMAGE} AS builder

# uv is copied in as a single static binary (Docker Hub mirror of the official image).
COPY --from=astral/uv:0.11.32 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# 1) Dependencies only. This layer is rebuilt only when uv.lock or
#    pyproject.toml change, not on every code edit, so rebuilds are fast.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# 2) The application itself, installed as a regular (non-editable) package.
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime

# A fixed, non-root UID: if the process is compromised it has no root
# privileges, and file ownership on mounted volumes is predictable.
RUN groupadd --system --gid 10001 nexus \
 && useradd --system --uid 10001 --gid nexus --no-create-home --shell /usr/sbin/nologin nexus

WORKDIR /app
COPY --from=builder --chown=nexus:nexus /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXUS_LOG_FORMAT=json

USER nexus
EXPOSE 8000

# Liveness only (no dependency checks). The slim image has no curl, so use Python.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status != 200)"]

# Exec form: uvicorn is PID 1 and receives SIGTERM directly, so it can shut down gracefully.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
