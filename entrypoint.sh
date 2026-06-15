#!/bin/sh
set -e

mkdir -p /app/data

echo "LINGVA.AI entrypoint v1.3.0"
echo "  RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-}"
echo "  PORT=${PORT:-8080}"

exec python -u bot.py
