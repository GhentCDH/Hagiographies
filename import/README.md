# Hagiographies import workflow

## Requirements

You are expected to have a UTF-8 encoded `csv` file exported from Excel.
This file should be placed in the `../data/` directory.

## Usage

To run this import script from scratch (with a fresh SQLite database), run `just reinit` if you have `just` installed.
Otherwise, run the `reinit` recipe directly:

```sh
docker compose down -t 1
docker compose up -d --build
docker compose exec import uv run import
```
