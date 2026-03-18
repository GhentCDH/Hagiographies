FROM node:22-trixie
WORKDIR /app

COPY kottster/package*.json .
COPY kottster/*json .
COPY kottster/vite.config.js .

COPY kottster/scripts ./scripts

RUN npm install

CMD ["sh" , "/app/scripts/dev.sh"]