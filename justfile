KOTTSTER_HOST := "localhost"
KOTTSTER_PORT := "5480"
KOTTSTER_PATH := "/hagiographies/admin"
KOTTSTER_URL := "http://{{KOTTSTER_HOST}}:{{KOTTSTER_PORT}}{{KOTTSTER_PATH}}"

rebuild:
    docker compose down -t 1
    docker compose up -d --build

up:
    docker compose up -d

import:
	docker compose exec import uv run import
	docker compose exec kottster rm -rf /app/.cache
	docker compose restart kottster

kottster:
    docker compose exec kottster ./scripts/dev.sh

reset-db:
    rm -f data/hagiographies.db*

map-up:
    docker compose up --build -d hagiographies-map

reinit: rebuild reset-db import map-up

open:
    @echo "Waiting for {{KOTTSTER_URL}}..."
    @until nc -z {{KOTTSTER_HOST}} {{KOTTSTER_PORT}}; do \
      printf "."; sleep 0.5; \
    done
    @echo "\n{{KOTTSTER_URL}} ready!"
    @if [ "{{os()}}" = "macos" ]; then \
      open "{{KOTTSTER_URL}}"; \
    elif [ "{{os()}}" = "linux" ]; then \
      xdg-open "{{KOTTSTER_URL}}"; \
    else \
      start "{{KOTTSTER_URL}}"; \
    fi
