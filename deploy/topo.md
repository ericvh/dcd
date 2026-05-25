# Deploy dcd with Arm Topo

[dcd](https://github.com/ericvh/dcd) ships a [Topo](https://github.com/arm/topo) template as [`compose.yaml`](../compose.yaml) at the repository root. Topo builds the image on your laptop, transfers it to the target, and runs `docker compose up` there — with `/var/run/docker.sock` mounted so **dcd controls the same Docker Engine that is running it**.

## Prerequisites

- [Topo](https://github.com/arm/topo) installed on your workstation
- SSH access to an **Arm64** Linux target with Docker Engine and Compose plugin
- For **D2D**: set `ALLOW_INSECURE=true` (default in the template) on the LAN
- For **Portal**: provision a device credential on the portal and copy the `.creds.json` file onto the target before deploy

## Quick deploy (D2D)

```bash
topo clone https://github.com/ericvh/dcd.git
cd dcd
topo deploy --target pi@raspberrypi.local
```

Topo prompts for template arguments (`DEVICE_ID`, `TENANT`, `ALLOW_INSECURE`) and injects them into the image build.

Verify on the target:

```bash
ssh pi@raspberrypi.local docker ps
ssh pi@raspberrypi.local docker logs dcd-driver
```

## Portal on the edge

1. Provision credentials (portal UI or `dc-portalctl devices provision`).
2. Copy the file to the target, e.g. `~/.config/device-connect/my-docker-host.creds.json`.
3. Edit `compose.yaml` on the cloned project (or use a local override) before `topo deploy`:

```yaml
services:
  dcd:
    environment:
      DEVICE_CONNECT_PORTAL: "true"
      NATS_CREDENTIALS_FILE: /creds/my-docker-host.creds.json
      DEVICE_CONNECT_DISCOVERY_MODE: infra
      DEVICE_CONNECT_ALLOW_INSECURE: "false"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /home/pi/.config/device-connect:/creds:ro
```

4. Redeploy: `topo deploy --target pi@raspberrypi.local`

## Local Docker (no Topo)

Same socket pattern without SSH:

```bash
docker build -t dcd:local .
docker run --rm -d \
  --name dcd-driver \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DEVICE_CONNECT_ALLOW_INSECURE=true \
  -e DCD_DEVICE_ID=docker-host-edge \
  dcd:local
```

Or use [`examples/docker-compose.dcd.yml`](../examples/docker-compose.dcd.yml).

## Security notes

- Mounting `docker.sock` grants the container **full control** of the host Engine (equivalent to root on the host for container workloads). Restrict network access and Portal credentials accordingly.
- Set `ALLOW_INSECURE=false` and use Portal + TLS when leaving the lab.
- **tcd** ([topo_deployer](https://github.com/ericvh/tcd)) is the right driver when workloads must be built on a laptop and deployed to remote boards over SSH **without** a local Engine on the board. **dcd** is for boards that already run Docker and should expose that Engine on Device Connect.

## Stop / update

```bash
topo stop --target pi@raspberrypi.local
topo deploy --target pi@raspberrypi.local
```
