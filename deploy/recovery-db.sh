#!/bin/sh
set -eu
export PGPASSWORD="$(cat /run/secrets/database_password)"
case "$1" in
  backup) exec pg_dump --format=custom --no-owner --no-privileges ;;
  empty)
    count=$(psql -Atc "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')")
    test "$count" = 0 ;;
  idle)
    count=$(psql -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()")
    test "$count" = 0 ;;
  restore) exec pg_restore --exit-on-error --single-transaction --no-owner --no-privileges --dbname "$PGDATABASE" ;;
  *) exit 2 ;;
esac
