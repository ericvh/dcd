"""Integration tests against a real Docker Engine (GitHub Actions / local)."""

from __future__ import annotations

import os
import shutil
import uuid

import pytest

from dcd.docker_backend import DockerEngineBackend, build_docker_backend
from dcd.models import ComposeProvisionSpec, ContainerProvisionSpec

pytestmark = pytest.mark.docker


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        import asyncio

        asyncio.run(DockerEngineBackend().ping())
        return True
    except Exception:
        return False


skip_no_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker Engine not available (set DOCKER_HOST or start Docker)",
)


@pytest.fixture
async def engine_backend() -> DockerEngineBackend:
    backend = DockerEngineBackend()
    yield backend
    # Best-effort cleanup for containers left by a failed assertion.
    try:
        for summary in await backend.list_containers(all_containers=True):
            if summary.name.startswith("dcd-it-"):
                await backend.remove_container(summary.id, force=True)
    except Exception:
        pass


@skip_no_docker
async def test_engine_ping() -> None:
    backend = DockerEngineBackend()
    info = await backend.ping()
    assert info["connected"] is True
    assert info.get("simulated") is not True


@skip_no_docker
async def test_provision_lifecycle_on_real_engine(engine_backend: DockerEngineBackend) -> None:
    name = f"dcd-it-{uuid.uuid4().hex[:8]}"
    spec = ContainerProvisionSpec(
        image="alpine:3.20",
        name=name,
        command=["sleep", "30"],
    )
    created = await engine_backend.create_container(spec)
    assert created.name == name

    started = await engine_backend.start_container(created.id)
    assert started.state == "running"

    stopped = await engine_backend.stop_container(created.id, timeout_s=5)
    assert stopped.state == "exited"

    await engine_backend.remove_container(created.id, force=True)


@skip_no_docker
async def test_compose_up_inline_yaml(engine_backend: DockerEngineBackend) -> None:
    service = f"dcd-it{uuid.uuid4().hex[:6]}"
    yaml = f"""
services:
  {service}:
    image: alpine:3.20
    command: ["sleep", "60"]
"""
    up = await engine_backend.compose_up(
        ComposeProvisionSpec(compose_yaml=yaml, detach=True, services=[service])
    )
    assert up["status"] == "success"
    project_dir = up["project_dir"]
    assert project_dir

    containers = await engine_backend.list_containers(all_containers=False)
    names = {c.name for c in containers}
    assert any(service in n for n in names)

    down = await engine_backend.compose_down(project_dir=project_dir)
    assert down["status"] == "success"


@skip_no_docker
async def test_ci_reports_docker_host_when_set() -> None:
    """Sanity check that CI DinD wiring is visible to tests."""
    host = os.environ.get("DOCKER_HOST", "")
    if host.startswith("tcp://"):
        backend = DockerEngineBackend()
        info = await backend.ping()
        assert info["connected"] is True


@skip_no_docker
async def test_build_docker_backend_uses_engine_when_not_sim() -> None:
    backend = build_docker_backend(simulate=False)
    info = await backend.ping()
    assert info.get("simulated") is not True
