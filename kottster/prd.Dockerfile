# ---- Builder ----
FROM node:22.22.1-alpine AS builder
WORKDIR /app

COPY kottster/package*.json .
COPY kottster/*json .
COPY kottster/vite.config.js .

COPY kottster/app ./app
COPY kottster/scripts ./scripts

RUN npm install
RUN npm run build

# ---- Runner ----
FROM node:22.22.1-alpine AS runner
WORKDIR /app

COPY --from=builder /app/package.json .
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist

CMD ["node", "dist/server/server.cjs"]