#!/bin/sh
set -e

# Гарантируем writable-директории (Railway volume опционален на /app/data)
mkdir -p /app/data

echo "LINGVA.AI entrypoint"
echo "  RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT:-}"
echo "  PORT=${PORT:-8080}"
echo "  DB_PATH=${DB_PATH:-/app/data/lingva.db (auto)}"

exec python bot.py
