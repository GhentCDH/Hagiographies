FROM node:22-alpine

WORKDIR /app

COPY package*.json ./

RUN apk add --no-cache git tini

RUN npm install

EXPOSE 5480 5481

ENV VITE_DOCKER_MODE=true

# App server port
ENV PORT=5480

# Development API server port
ENV DEV_API_SERVER_PORT=5481

COPY scripts/dev.sh /dev.sh
COPY scripts/prod.sh /prod.sh
RUN chmod +x /dev.sh /prod.sh

ENTRYPOINT ["/sbin/tini", "--"]

# This is a dummy command to keep the container running
CMD ["tail", "-f", "/dev/null"]
