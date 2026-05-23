"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from dcd.device_connect import DockerHostDriver
from dcd.docker_backend import SimDockerBackend


@pytest.fixture
def captured_events() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def sim_backend() -> SimDockerBackend:
    return SimDockerBackend()


@pytest.fixture
def driver(
    sim_backend: SimDockerBackend,
    captured_events: list[tuple[str, dict[str, Any]]],
) -> DockerHostDriver:
    host_driver = DockerHostDriver(backend=sim_backend, simulate=True)
    host_driver.set_event_callback(
        lambda name, payload: captured_events.append((name, payload))
    )
    return host_driver


@pytest.fixture
async def connected_driver(driver: DockerHostDriver) -> DockerHostDriver:
    await driver.connect()
    yield driver
    await driver.disconnect()
