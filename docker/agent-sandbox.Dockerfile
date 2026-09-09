FROM python:3.12-slim-bookworm

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace /opt/isolated-home /opt/isolated-xdg \
    && chown 65532:65532 /workspace /opt/isolated-home /opt/isolated-xdg

USER 65532:65532
WORKDIR /workspace
