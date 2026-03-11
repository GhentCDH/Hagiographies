#!/bin/sh
set -e

echo "Starting in development mode..."
# Clear Kottster cache on startup to avoid stale schema errors
rm -rf /app/.cache
exec npm run dev -- --port 5480 --host 0.0.0.0
