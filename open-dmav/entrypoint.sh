#!/bin/sh
set -e

if [ "${WAIT_FOR_DB:-1}" = "1" ]; then
  echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
  until nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do
    sleep 1
  done
fi

echo "Applying Django migrations and creating tables for apps without migrations..."
python manage.py migrate --noinput --run-syncdb

echo "Synchronizing generated enum value lists..."
python manage.py sync_enum_values --prune

exec "$@"
