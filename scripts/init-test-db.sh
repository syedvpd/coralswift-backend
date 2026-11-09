#!/bin/sh
# Creates the disposable database used by pytest. Runs once on a fresh volume.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "CREATE DATABASE ${POSTGRES_DB}_test OWNER ${POSTGRES_USER}"
