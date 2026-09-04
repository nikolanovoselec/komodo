FROM ghcr.io/openclaw/openclaw:2026.9.1

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*
COPY --chmod=755 openclaw-gateway-entrypoint.sh /usr/local/bin/openclaw-gateway-entrypoint
USER node
