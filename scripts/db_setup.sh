#!/bin/sh
set -e

echo "\n************** Restoring database from file at /data/pg_dump/Ft/pgdump... \n"
pg_restore -d postgres /data/pg_dump/Ft/pgdump
