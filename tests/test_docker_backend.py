"""Unit tests for SimDockerBackend."""

from __future__ import annotations

import pytest

from dcd.docker_backend import SimDockerBackend
from dcd.models import ContainerProvisionSpec


@pytest.fixture
def backend() -> SimDockerBackend:
    return SimDockerBackend()


async def test_ping_reports_simulated(backend: SimDockerBackend) -> None:
    info = await backend.ping()
    assert info["connected"] is True
    assert info["simulated"] is True


async def test_get_container_by_name(backend: SimDockerBackend) -> None:
    from dcd.models import ContainerProvisionSpec

    created = await backend.create_container(
        ContainerProvisionSpec(image="alpine:latest", name="by-name")
    )
    fetched = await backend.get_container("by-name")
    assert fetched.id == created.id


async def test_remove_running_without_force_raises(backend: SimDockerBackend) -> None:
    from dcd.models import ContainerProvisionSpec

    created = await backend.create_container(ContainerProvisionSpec(image="alpine:latest", name="running"))
    with pytest.raises(ValueError, match="running"):
        await backend.remove_container(created.id, force=False)


async def test_compose_down_removes_compose_containers(backend: SimDockerBackend) -> None:
    from dcd.models import ComposeProvisionSpec

    await backend.compose_up(ComposeProvisionSpec(compose_yaml="services:\n  app:\n    image: alpine\n"))
    result = await backend.compose_down()
    assert result["status"] == "success"
    assert result["simulated"] is True


async def test_create_start_stop_remove(backend: SimDockerBackend) -> None:
    spec = ContainerProvisionSpec(image="alpine:latest", name="unit-test")
    created = await backend.create_container(spec)
    assert created.name == "unit-test"

    running = await backend.start_container(created.id)
    assert running.state == "running"

    stopped = await backend.stop_container(created.id)
    assert stopped.state == "exited"

    await backend.remove_container(created.id, force=True)
    with pytest.raises(KeyError):
        await backend.get_container(created.id)
