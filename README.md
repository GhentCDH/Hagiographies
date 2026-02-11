# Hagiographies

Excel-to-SQLite import pipeline with a Kottster admin panel for browsing hagiographic data.

## Setup

```sh
just rebuild   # build Docker containers
just import    # create tables and import CSV data
just kottster  # start Kottster dev server on port 5480
```

## Project Structure

- `import/` — Python service that imports CSV data into SQLite
- `kottster/` — Kottster admin UI for browsing the database
- `data/` — SQLite database and CSV files (gitignored)
