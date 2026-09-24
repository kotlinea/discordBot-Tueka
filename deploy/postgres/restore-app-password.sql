-- Run as the PostgreSQL administrator in the selected environment container.
-- Execute the generated statement without printing its password.
\set ON_ERROR_STOP on
\set ECHO none
\getenv app_name TUEKA_DB_NAME
SELECT format('ALTER ROLE %I PASSWORD %L', :'app_name',
              rtrim(pg_read_file('/run/secrets/database_password'), chr(10))) \gexec
