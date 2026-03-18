FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS uv

WORKDIR /app

# avoids hardlink issues in containers
ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends graphviz 
