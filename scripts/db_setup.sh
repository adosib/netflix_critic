#!/bin/sh
set -e

echo "\n************** Restoring database from file at /data/pg_dump/Fc/pg.dump... \n"
pg_restore -d postgres /data/pg_dump/Fc/pg.dump
