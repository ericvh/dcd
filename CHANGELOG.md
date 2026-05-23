# Changelog

All notable changes to **dcd** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- GitHub Actions CI (`.github/workflows/ci.yml`): ruff + pytest on Python 3.12/3.13; `workflow_dispatch`
- Unit tests: `test_config`, `test_models`, `test_runtime_launcher`, `test_cli`; expanded backend/driver coverage

### Changed

- Design/docs: split from **[tcd](../tcd)** — Topo SSH deploy is a separate driver (`topo_deployer`)

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
