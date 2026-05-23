# TODO — dcd

## Near term

- [ ] Integration test job with Docker-in-Docker (real `DockerEngineBackend`)
- [ ] Stream `container_logs` via Device Connect events (follow mode)
- [ ] `attach` / interactive TTY session RPC (or document as out of scope)
- [ ] Validate `compose_up` with inline YAML on real Docker (CI service container)
- [ ] Publish package to PyPI (`pip install dcd`)

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
- [ ] Configurable `@periodic` interval from `DCD_STATE_POLL_HZ` (today fixed at 0.5s when hz > 0)

## Quality

- [x] GitHub Actions CI (Python 3.12/3.13, ruff, pytest) — `.github/workflows/ci.yml`
- [ ] Contract test against pinned `device-connect-edge` version matrix
