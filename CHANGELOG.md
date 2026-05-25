# Changelog

All notable changes to **dcd** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Log follow: `container_logs(follow=true)` emits `container_log_line`; `stop_container_logs` RPC
- Topo deploy template (`compose.yaml` + `deploy/topo.md`) and production `Dockerfile` / entrypoint
- Docker Engine integration tests (`pytest -m docker`) and CI DinD job
- Contract matrix CI job for pinned `device-connect-edge`

### Changed

- State polling interval follows `DCD_STATE_POLL_HZ` (not a fixed 0.5s decorator)
- Inline `compose_yaml` projects persist until `compose_down` (temp dir lifecycle fix)
- `docker compose` CLI flag ordering (`-f` before `up`/`down`)
- GitHub Actions: separate lint, unit, contract-matrix, and docker-integration jobs; ruff format check
- Interactive attach/TTY documented as out of scope

### Deferred

- PyPI publish (`pip install dcd`)

## [0.1.0] - 2026-05-23

### Added

- Initial **Device Connect Docker host driver** (`device_type = docker_host`)
- Container lifecycle RPCs: provision, start, stop, restart, remove, logs, exec
- Image RPCs: `pull_image`, `list_images`
- Compose RPCs: `compose_up`, `compose_down` via host `docker compose` CLI
- `container_state_changed` event with periodic state polling
- `SimDockerBackend` and `--sim` CLI flag for CI without Docker
- Portal and D2D runtime configuration (credentials, discovery mode, messaging URLs)
- Dockerfile and `examples/docker-compose.dcd.yml` for socket-mounted deployment
- Documentation: README, DESIGN (Topo vs Docker tradeoffs), TODO
- Apache-2.0 license

[0.1.0]: https://github.com/example/dcd/releases/tag/v0.1.0
