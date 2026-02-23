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

map-up:
    docker compose up --build -d hagiographies-map

map-down:
    docker compose down hagiographies-map

map-logs:
    docker compose logs -f hagiographies-map

map-rebuild:
    docker compose build --no-cache hagiographies-map
    docker compose up -d hagiographies-map