# syntax=docker/dockerfile:1

FROM node:22-alpine

WORKDIR /app

# System deps: tini (PID1), build tools for better-sqlite3 native compile, jq
RUN apk add --no-cache git tini sqlite sqlite-dev make g++ jq

# Enable pnpm via corepack
RUN npm install --global corepack@latest && corepack enable

# Pre-configure pnpm workspace so better-sqlite3 is allowed to build natively
RUN pnpm init && \
    printf "onlyBuiltDependencies:\n- better-sqlite3\n" >> pnpm-workspace.yaml && \
    pnpm add better-sqlite3

# Install app dependencies (patches* assumes the directory exists in the repo)
COPY package*.json ./
COPY patches* ./
RUN pnpm install

# Copy full source
COPY . .

# ── Build-time config ─────────────────────────────────────────────────────────
# KOTTSTER_BASE_PATH is a build ARG: Vite bakes it into the bundle at build time
ARG KOTTSTER_BASE_PATH=""
ENV VITE_BASE_PATH=${KOTTSTER_BASE_PATH}
ENV VITE_DOCKER_MODE=true
ENV PORT=5480
ENV DEV_API_SERVER_PORT=5481
ENV DATABASE_PATH=/app/app.db

# Inject optional basePath into kottster-app.json before the Vite build
RUN jq --arg bp "${KOTTSTER_BASE_PATH}" \
    '. + if $bp != "" then {basePath: $bp} else {} end' \
    kottster-app.json > kottster-app.tmp.json && \
    mv kottster-app.tmp.json kottster-app.json

RUN pnpm run build

# Permissions & non-root runtime user
RUN chmod +x /app/scripts/* && \
    mkdir -p /app/.cache && \
    chown -R node:node /app/

EXPOSE 5480 5481

USER node
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["sh", "scripts/prod.sh"]