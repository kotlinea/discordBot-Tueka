#!/bin/sh
set -eu
# Only the empty-volume PostgreSQL initializer executes this script.
# Application credentials never use the PostgreSQL superuser.
app_password="$(cat /run/secrets/database_password)"
psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 \
  --set app_name="$TUEKA_DB_NAME" --set app_password="$app_password" <<'SQL'
CREATE ROLE :"app_name" LOGIN PASSWORD :'app_password';
CREATE DATABASE :"app_name" OWNER :"app_name";
SQL
unset app_password
