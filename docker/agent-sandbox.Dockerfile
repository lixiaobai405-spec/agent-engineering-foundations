FROM python:3.12-slim-bookworm

RUN mkdir -p /workspace && chown 65532:65532 /workspace

USER 65532:65532
WORKDIR /workspace
