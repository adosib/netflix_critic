FROM postgres:latest

COPY ./scripts/db_setup.sh /docker-entrypoint-initdb.d/db_setup.sh
RUN chmod +x /docker-entrypoint-initdb.d/db_setup.sh