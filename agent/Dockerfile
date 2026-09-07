# Build context is this directory, not the repo root:
#   docker build -t ghcr.io/ihorklymchukdev/omelet-agent:<version> agent/
# `agent/pyproject.toml` maps package-dir {"agent" = "."} against that context,
# which is also what keeps `agent/` importable and installable on its own
# (the property tests/test_no_agent_imports_host.py protects). `docker build .`
# from the repo root will not find pyproject.toml here.

ARG DOCKER_CLI_VERSION=29.8.0

# Pinned CLI-only stage: copying the binaries out of the official image is
# smaller than adding Docker's apt repo to the runtime stage, and pins the
# exact CLI version instead of whatever the distro repo serves that day.
FROM docker:${DOCKER_CLI_VERSION}-cli AS docker-cli

FROM python:3.12-slim AS runtime

ARG AGENT_VERSION=0.1.0
ARG DOCKER_GID=999

ENV OMELET_AGENT_VERSION=${AGENT_VERSION} \
    PYTHONUNBUFFERED=1

# Absolute /usr/bin/docker, not /usr/local/bin: core/lifecycle.py hardcodes
# this exact path, because a bare `docker` on a WSL2 host with Docker Desktop
# integration on can resolve to Desktop's own engine instead of this VM's.
COPY --from=docker-cli /usr/local/bin/docker /usr/bin/docker
# lifecycle.py calls `docker compose`, the plugin, not the standalone
# docker-compose binary. /usr/local/lib/docker/cli-plugins is one of the
# CLI's fixed plugin search paths regardless of where the docker binary lives.
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose \
     /usr/local/lib/docker/cli-plugins/docker-compose

# The mounted socket's GID on the VM is baked into the image as a default;
# a VM whose docker group has a different GID is fixed via stack.yml's
# group_add instead of a rebuild. Debian base images occasionally already own
# the default GID (a system group), so reuse it by name rather than fail the
# build outright.
RUN if getent group "${DOCKER_GID}" >/dev/null; then \
        groupmod -n docker "$(getent group "${DOCKER_GID}" | cut -d: -f1)"; \
    else \
        groupadd -g "${DOCKER_GID}" docker; \
    fi \
    && useradd -m -u 1000 -g docker agent

WORKDIR /app

# Only the installable package, not agent/templates (host-side verify fixture)
# or agent/deploy (compose manifests, not Python) -- neither belongs in the
# image.
COPY pyproject.toml /app/
COPY __init__.py /app/
COPY core /app/core
COPY api /app/api
RUN pip install --no-cache-dir .

USER agent

EXPOSE 39099

# python:3.12-slim has no curl/wget worth relying on; /health is designed to
# answer even when the Docker socket is unreachable, so a failing healthcheck
# means the agent process itself is down, not that a project failed to start.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('OMELET_AGENT_PORT', '39099'), timeout=3)"

CMD ["python", "-m", "agent.api"]
