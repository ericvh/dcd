# Device Connect Docker host driver — controls the host Engine via docker.sock.
#
# Build:
#   docker build -t dcd:latest .
#
# Run (D2D dev on the same machine that built the image):
#   docker run --rm -it \
#     -v /var/run/docker.sock:/var/run/docker.sock \
#     -e DEVICE_CONNECT_ALLOW_INSECURE=true \
#     dcd:latest
#
# See compose.yaml (Topo) and examples/docker-compose.dcd.yml.

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
      > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Topo x-topo args are injected into build.args and mapped here.
ARG DEVICE_ID=docker-host-edge
ARG TENANT=default
ARG ALLOW_INSECURE=true

ENV DCD_DEVICE_ID=${DEVICE_ID} \
    DCD_TENANT=${TENANT} \
    DEVICE_CONNECT_ALLOW_INSECURE=${ALLOW_INSECURE} \
  PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

LABEL org.opencontainers.image.title="dcd" \
      org.opencontainers.image.description="Device Connect docker_host driver" \
      org.opencontainers.image.source="https://github.com/ericvh/dcd"

# Runs the driver using env vars; pass CLI flags after the image name if needed.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD []
