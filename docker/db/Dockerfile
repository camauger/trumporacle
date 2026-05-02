# Purpose: Postgres 16 + TimescaleDB + pgvector (built from source) + init SQL for pg_trgm.
FROM timescale/timescaledb:2.17.2-pg16

USER root
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates build-essential postgresql-server-dev-16; \
    git clone --depth 1 --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector; \
    make -C /tmp/pgvector -j"$(nproc)"; \
    make -C /tmp/pgvector install; \
    rm -rf /tmp/pgvector; \
    apt-get purge -y git build-essential postgresql-server-dev-16; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

COPY init-extensions.sql /docker-entrypoint-initdb.d/01-trumporacle-extensions.sql

USER postgres
