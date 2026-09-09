ARG NODE_BASE_IMAGE=node@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
FROM ${NODE_BASE_IMAGE}

ARG NODE_BASE_REPO_DIGEST=node@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
LABEL io.agent-foundations.sandbox-profile="node" \
      io.agent-foundations.base-repo-digest="${NODE_BASE_REPO_DIGEST}" \
      io.agent-foundations.lockfile-sha256="06c84831ab91e26c98c7ce32291c0e3aac95c97c0287203e5bb292687dbb8d98"

COPY package.json package-lock.json /opt/sandbox/
RUN cd /opt/sandbox \
    && npm ci --ignore-scripts \
    && groupadd --gid 65532 sandbox \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /project-ro /workspace \
    && chown 65532:65532 /workspace

COPY docker/sandbox-entrypoint.sh /usr/local/bin/sandbox-entrypoint
RUN chmod 0555 /usr/local/bin/sandbox-entrypoint

ENV SANDBOX_NODE_MODULES=/opt/sandbox/node_modules
USER 65532:65532
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/sandbox-entrypoint"]
