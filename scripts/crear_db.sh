#!/usr/bin/env sh
# Crea las bases locales de Postgres (desarrollo y tests) con PostGIS.
# Requiere un Postgres local corriendo y un usuario con permisos de superusuario.
#   brew services start postgresql@18
set -e
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"

for base in suite_cabana suite_cabana_test; do
  psql -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='suite'" | grep -q 1 \
    || psql -d postgres -c "CREATE ROLE suite LOGIN PASSWORD 'suite' CREATEDB;"
  psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$base'" | grep -q 1 \
    || psql -d postgres -c "CREATE DATABASE $base OWNER suite;"
  psql -d "$base" -v ON_ERROR_STOP=1 -c \
    "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS btree_gist; GRANT ALL ON SCHEMA public TO suite;"
  echo "✓ $base"
done
