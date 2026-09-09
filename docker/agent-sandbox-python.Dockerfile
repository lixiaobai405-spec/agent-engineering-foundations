FROM python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

LABEL io.agent-foundations.sandbox-profile="python" \
      io.agent-foundations.base-repo-digest="python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2" \
      io.agent-foundations.lockfile-sha256="54a48d9fe970cea3b27a5488b123660a0b6c73cd68e8462bdac231737b85c531"

COPY docker/agent-sandbox-python.requirements.lock /opt/sandbox/requirements.lock
RUN python -m pip install --no-cache-dir --requirement /opt/sandbox/requirements.lock \
    && groupadd --gid 65532 sandbox \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /project-ro /workspace \
    && chown 65532:65532 /workspace

COPY docker/sandbox-entrypoint.sh /usr/local/bin/sandbox-entrypoint
RUN chmod 0555 /usr/local/bin/sandbox-entrypoint

ENV PYTHONPATH=/workspace/src
USER 65532:65532
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/sandbox-entrypoint"]
