rebuild:
    docker compose down -t 1
    docker compose up -d --build

up:
    docker compose up -d

import:
    docker compose exec import uv run import

kottster:
    docker compose exec kottster /dev.sh

reinit: rebuild import

reset-db:
    rm -f data/hagiographies.db
