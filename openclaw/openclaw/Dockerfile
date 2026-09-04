FROM ghcr.io/openclaw/openclaw:2026.9.1

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*
USER node
