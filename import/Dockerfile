FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS uv

WORKDIR /app

# avoids hardlink issues in containers
ENV UV_LINK_MODE=copy

# copy dependency files
COPY pyproject.toml uv.lock ./
COPY README.md ./
COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
