#!/bin/sh
set -e

echo "Starting in production mode..."

echo "Building project first..."
npm run build

echo "Starting production server..."
# Clear Kottster cache on startup to avoid stale schema errors
rm -rf /app/.cache
exec npm run start
