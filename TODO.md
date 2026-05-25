# TODO — dcd

## Near term

- [x] Integration test job with Docker-in-Docker (real `DockerEngineBackend`) — CI `docker-integration` DinD via `tcp://127.0.0.1:2375`
- [x] Stream `container_logs` via Device Connect events (follow mode) — `container_log_line` + `follow=true`
- [x] `attach` / interactive TTY session RPC — documented out of scope (use `exec_in_container`)
- [x] Validate `compose_up` with inline YAML on real Docker (CI service container)
- [ ] Publish package to PyPI (`pip install dcd`) — deferred

## Portal / ops

- [ ] Example `dc-portalctl` provision script in `examples/`
- [ ] Document recommended NATS subject limits for high-frequency `container_state_changed`
- [ ] Helm chart or compose stack including dcd + portal sidecar pattern

## Remote / edge

- [ ] Document `DOCKER_HOST=ssh://user@host` for remote engines
- [ ] Cross-driver doc: agent recipe using **dcd** + **tcd** on one gateway (see `~/src/tcd`)
- [ ] Support rootless Docker socket paths

## Driver enhancements

- [ ] `provision_container` idempotency (create or update if name exists)
- [ ] Network create/connect RPCs
- [ ] Volume management RPCs
- [ ] Filter `list_containers` by label selector
- [x] Configurable state poll interval from `DCD_STATE_POLL_HZ` (replaces fixed 0.5s `@periodic`)

## Quality

- [x] GitHub Actions CI (Python 3.12/3.13, ruff check + format, pytest) — `.github/workflows/ci.yml`
- [x] Contract test against pinned `device-connect-edge` version matrix — `contract-matrix` job
