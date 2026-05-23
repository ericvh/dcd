# dcd — Device Connect Docker host driver

**dcd** exposes a Docker Engine on the [Device Connect](https://github.com/arm/device-connect) mesh as a `docker_host` device. Agents and other devices can **provision**, **start/stop**, **inspect**, **tail logs**, **exec**, and run **docker compose** projects over JSON-RPC — on **D2D** (LAN, no portal) or **Portal** (multi-tenant NATS + registry).

License: [Apache-2.0](LICENSE)

## Features

- **Provision containers** via `provision_container` with ports, volumes, env, labels
- **Lifecycle**: start, stop, restart, remove
- **Interact**: `container_logs`, `exec_in_container`
- **Images**: `pull_image`, `list_images`
- **Compose**: `compose_up` / `compose_down` (host `docker compose` CLI)
- **Events**: `container_state_changed` when container state transitions
- **D2D and Portal**: same driver; configure messaging via CLI or env (see below)
- **Bare metal or in-container**: mount `docker.sock` when running inside Docker
- **Sim mode**: `--sim` for CI and development without Docker

## Install

```bash
cd ~/src/dcd
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python **3.12** or **3.13** and Docker Engine API access (socket or `DOCKER_HOST`).

## Quick start — D2D (LAN)

No portal credentials; Zenoh multicast discovery by default:

```bash
export DEVICE_CONNECT_ALLOW_INSECURE=true
dcd --sim --device-id docker-host-1 --tenant dev
```

With a real Docker socket:

```bash
export DEVICE_CONNECT_ALLOW_INSECURE=true
dcd --device-id docker-host-1 --tenant dev
```

Invoke from another process using `device-connect-agent-tools` or a second driver with `invoke_remote`.

## Quick start — Portal

Provision a device credential in the portal (or `dc-portalctl devices provision`), then:

```bash
dcd \
  --portal \
  --portal-credentials ~/.config/device-connect/my-device.creds.json \
  --nats-credentials-file ~/.config/device-connect/my-device.creds.json \
  --device-id my-docker-host
```

Portal mode sets NATS URLs from the credential file and uses registry (`discovery_mode=infra`) unless overridden.

Force D2D while using portal-issued creds for NATS only:

```bash
dcd --portal --discovery-mode d2d ...
```

## Run in Docker

Build and run with the host socket (see `examples/docker-compose.dcd.yml`):

```bash
docker build -t dcd:local .
docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DEVICE_CONNECT_ALLOW_INSECURE=true \
  dcd:local --device-id docker-host-edge --tenant dev
```

## RPC reference

| Function | Description |
|----------|-------------|
| `get_status` | Driver + engine connectivity |
| `ping_docker` | Refresh Docker Engine metadata |
| `list_containers` | List containers (`all_containers`) |
| `get_container` | Inspect by ID or name |
| `provision_container` | Create container from spec dict |
| `start_container` / `stop_container` / `restart_container` / `remove_container` | Lifecycle |
| `container_logs` | Tail logs |
| `exec_in_container` | Run command in container |
| `pull_image` / `list_images` | Image operations |
| `compose_up` / `compose_down` | Docker Compose projects |
| `list_managed_containers` | Containers with `deviceconnect.dev/managed=true` |

**Event:** `container_state_changed` — `container_id`, `name`, `previous_state`, `state`, `image`

### Provision spec example

```json
{
  "image": "nginx:alpine",
  "name": "web-1",
  "ports": [{"container_port": 80, "host_port": 8080}],
  "environment": {"FOO": "bar"},
  "labels": {"app": "demo"}
}
```

Managed containers automatically receive `deviceconnect.dev/managed=true` and `deviceconnect.dev/driver=dcd` labels unless `device_connect_labels` is set to `false` in the spec.

## Configuration

| Variable | Description |
|----------|-------------|
| `DCD_DEVICE_ID` / `DEVICE_ID` | Device Connect device id |
| `DCD_TENANT` / `TENANT` | Tenant namespace |
| `DCD_SIM` | Use simulated Docker backend |
| `DOCKER_HOST` | Remote engine URL |
| `DCD_STATE_POLL_HZ` | State poll rate for events (default `2.0`, `0` disables) |
| `DEVICE_CONNECT_ALLOW_INSECURE` | D2D dev mode |
| `DEVICE_CONNECT_PORTAL` / `DCD_PORTAL` | Enable portal defaults |
| `NATS_CREDENTIALS_FILE` | Portal NATS JWT creds |
| `DEVICE_CONNECT_DISCOVERY_MODE` | `d2d`, `p2p`, or `infra` |
| `MESSAGING_URLS` / `NATS_URL` | Explicit broker URLs |

## Development

```bash
pytest -v
python tests/smoke_sim_runtime.py
ruff check src tests
```

### CI

GitHub Actions runs on every push to `main`, pull request, and manual **workflow_dispatch**:

- **Ruff** lint (`src`, `tests`)
- **pytest** on Python 3.12 and 3.13 (simulated Docker backend; no daemon required)

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

See [DESIGN.md](DESIGN.md) for architecture and the **Topo vs Docker** tradeoff analysis.

## Related projects

- **[tcd](../tcd)** — Device Connect driver for **Arm Topo** (`topo_deployer`); SSH deploy to edge boards
- [device-connect](https://github.com/arm/device-connect) — edge SDK and portal
- [topo](https://github.com/arm/topo) — underlying CLI used by **tcd**
