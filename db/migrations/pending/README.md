# Parked migrations

The runner only reads `db/migrations/*.sql`, so files in this folder are never
applied. Each one is finished and tested, but blocked by production data that
the researchers have to fix first. The header of each file names the blocking
rows.

To activate one:
1. Fix the data.
2. Give the file the next free number and move it to `db/migrations/`.
3. Add the matching constraint to `utils/utilities/src/utilities/model.py`.
4. Run `just db_diagram`.

None at the moment. The last two (edition identifier uniqueness and no
self-consulting edition) became 063 and 064 in October 2026.
