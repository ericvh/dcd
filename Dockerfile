# Device Connect Docker host driver — runs against the host Docker socket.
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-cli compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV DCD_DEVICE_ID=docker-host-1
ENV DCD_TENANT=default

# Mount /var/run/docker.sock when running this image.
ENTRYPOINT ["dcd"]
CMD ["--help"]
