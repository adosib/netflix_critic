FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

COPY ./hypercorn-fastapi-docker/images/start.sh /start.sh
RUN chmod +x /start.sh

COPY ./hypercorn-fastapi-docker/images/start-reload.sh /start-reload.sh
RUN chmod +x /start-reload.sh

COPY ./hypercorn-fastapi-docker/images/hypercorn_conf.py /hypercorn_conf.py

COPY pyproject.toml /pyproject.toml
COPY uv.lock /uv.lock

COPY ./webserver/templates /app/templates
COPY ./webserver/app_logger.py /app/app_logger.py
COPY ./webserver/app.py /app/app.py
COPY ./webserver/models.py /app/models.py

# Install Node.js and npm (required for PythonMonkey)
RUN apt-get update && apt-get install -y npm

RUN uv sync

WORKDIR /app

# Alias `uv run hypercorn` as `hypercorn`
RUN printf '#!/bin/bash \n uv run hypercorn $@' > /usr/bin/hypercorn
RUN chmod +x /usr/bin/hypercorn

ENV PATH="/usr/local/bin:$PATH"
ENV MODULE_NAME="app"
ENV WORKER_CLASS="uvloop"
ENV KEEP_ALIVE=30

EXPOSE 80
EXPOSE 443

CMD ["/start.sh"]