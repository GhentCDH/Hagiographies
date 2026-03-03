FROM node:22-alpine AS base
WORKDIR /app
COPY package*.json ./
RUN apk add --no-cache git tini
RUN npm install

FROM base AS dev
EXPOSE 5480 5481
ENV VITE_DOCKER_MODE=true
ENV PORT=5480
ENV DEV_API_SERVER_PORT=5481
COPY scripts/dev.sh /dev.sh
COPY scripts/prod.sh /prod.sh
RUN chmod +x /dev.sh /prod.sh
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["tail", "-f", "/dev/null"]

FROM base AS prd
EXPOSE 5480
ENV PORT=5480
COPY . .
ARG KOTTSTER_BASE_PATH
ENV KOTTSTER_BASE_PATH=$KOTTSTER_BASE_PATH
RUN npm run build
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["npm", "run", "start"]
