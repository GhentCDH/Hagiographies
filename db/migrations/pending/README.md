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

| File | Blocked by (PRD, 2026-10-22) |
| :--- | :--- |
| `unique_edition_identifier.sql` | `BHL_8426-K` used by editions 770 and 811 |
| `edition__edition_no_self_reference.sql` | edition__edition 711: `BHL_7963-B` consults itself |
