# Biobank for one lab: `docker compose up` (see docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BIOBANK_LOCAL_ROOT=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY biobank ./biobank
COPY core ./core
COPY bench ./bench
RUN pip install ".[postgres]"

COPY docker/entrypoint.sh /usr/local/bin/biobank-entrypoint
RUN chmod +x /usr/local/bin/biobank-entrypoint

VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["biobank-entrypoint"]
