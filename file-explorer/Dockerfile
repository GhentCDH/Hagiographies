# Stage 1: the Svelte build.
FROM oven/bun:1 AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

# Stage 2: the Rust binary, with the frontend embedded in it.
FROM rust:1-bookworm AS builder
WORKDIR /app

# Build the dependencies against a dummy main first, so a source change does not
# recompile the whole tree.
COPY Cargo.toml Cargo.lock ./
RUN mkdir -p src \
    && echo 'fn main(){}' > src/main.rs \
    && SKIP_FRONTEND_BUILD=1 cargo build --release \
    && rm -rf src

COPY build.rs ./
COPY src/ ./src/
COPY --from=frontend /app/frontend/dist ./frontend/dist/

# Touch main.rs so cargo rebuilds the binary and not just the cached deps.
RUN touch src/main.rs \
    && SKIP_FRONTEND_BUILD=1 cargo build --release

# Stage 3: runtime.
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/target/release/file-explorer ./

# Both are mounted at run time: the config so it can change without a rebuild,
# the share because it lives on the host.
ENV FILES_CONFIG=/app/config.toml
ENV FILES_SHARE_ROOT=/srv/share

EXPOSE 3000
CMD ["./file-explorer"]
