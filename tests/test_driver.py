"""Tests for DockerHostDriver RPCs and Device Connect contract."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from device_connect_edge import DeviceRuntime
from device_connect_edge.errors import FunctionInvocationError

from contract import REQUIRED_EVENTS, REQUIRED_FUNCTIONS
from dcd.device_connect import DockerHostDriver
from dcd.docker_backend import SimDockerBackend


def test_runtime_exposes_contract_functions_and_events() -> None:
    driver = DockerHostDriver(backend=SimDockerBackend(), simulate=True)
    runtime = DeviceRuntime(
        driver=driver,
        device_id="test-docker-host",
        tenant="test",
        allow_insecure=True,
    )

    function_names = {func.name for func in runtime.capabilities.functions}
    event_names = {event.name for event in runtime.capabilities.events}

    assert REQUIRED_FUNCTIONS <= function_names
    assert REQUIRED_EVENTS <= event_names
    assert driver.device_type == "docker_host"


async def test_get_status_after_connect(connected_driver: DockerHostDriver) -> None:
    status = await connected_driver.invoke("get_status")

    assert status["status"] == "success"
    assert status["device_type"] == "docker_host"
    assert status["connected"] is True
    assert status["simulate"] is True


async def test_provision_and_lifecycle(connected_driver: DockerHostDriver) -> None:
    created = await connected_driver.invoke(
        "provision_container",
        spec={"image": "alpine:latest", "name": "test-alpine", "command": ["sleep", "3600"]},
    )
    assert created["status"] == "success"
    cid = created["container"]["id"]

    listed = await connected_driver.invoke("list_containers", all_containers=True)
    assert listed["count"] >= 1

    stopped = await connected_driver.invoke("stop_container", container_id=cid)
    assert stopped["container"]["state"] == "exited"

    started = await connected_driver.invoke("start_container", container_id=cid)
    assert started["container"]["state"] == "running"

    logs = await connected_driver.invoke("container_logs", container_id=cid, tail=10)
    assert "test-alpine" in logs["logs"] or "created" in logs["logs"]

    exec_result = await connected_driver.invoke(
        "exec_in_container",
        container_id=cid,
        command=["echo", "hello"],
    )
    assert exec_result["exit_code"] == 0

    removed = await connected_driver.invoke("remove_container", container_id=cid, force=True)
    assert removed["status"] == "success"


async def test_list_managed_containers(connected_driver: DockerHostDriver) -> None:
    await connected_driver.invoke(
        "provision_container",
        spec={"image": "busybox:latest", "name": "managed-busybox"},
    )
    managed = await connected_driver.invoke("list_managed_containers")
    assert managed["count"] >= 1
    assert all(c["managed_by_dcd"] for c in managed["containers"])


async def test_pull_image(connected_driver: DockerHostDriver) -> None:
    result = await connected_driver.invoke("pull_image", image="nginx:alpine")
    assert result["status"] == "success"
    images = await connected_driver.invoke("list_images")
    assert images["count"] >= 1


async def test_compose_up_simulated(connected_driver: DockerHostDriver) -> None:
    result = await connected_driver.invoke(
        "compose_up",
        spec={"compose_yaml": "services:\n  app:\n    image: alpine\n"},
    )
    assert result["status"] == "success"
    assert result.get("simulated") is True


async def test_get_container_not_found(connected_driver: DockerHostDriver) -> None:
    with pytest.raises(FunctionInvocationError):
        await connected_driver.invoke("get_container", container_id="does-not-exist")


async def test_ping_docker_refreshes_info(connected_driver: DockerHostDriver) -> None:
    result = await connected_driver.invoke("ping_docker")
    assert result["status"] == "success"
    assert result["connected"] is True
    assert result.get("simulated") is True


async def test_restart_container(connected_driver: DockerHostDriver) -> None:
    created = await connected_driver.invoke(
        "provision_container",
        spec={"image": "alpine:latest", "name": "restart-me"},
    )
    cid = created["container"]["id"]
    restarted = await connected_driver.invoke("restart_container", container_id=cid)
    assert restarted["container"]["state"] == "running"


async def test_compose_down_simulated(connected_driver: DockerHostDriver) -> None:
    up = await connected_driver.invoke(
        "compose_up",
        spec={"compose_yaml": "services:\n  web:\n    image: nginx\n"},
    )
    down = await connected_driver.invoke(
        "compose_down",
        project_dir=up.get("project_dir", "/tmp/unused-in-sim"),
    )
    assert down["status"] == "success"


async def test_follow_container_logs_emits_events(
    connected_driver: DockerHostDriver,
    captured_events: list[tuple[str, dict[str, Any]]],
) -> None:
    created = await connected_driver.invoke(
        "provision_container",
        spec={"image": "alpine:latest", "name": "log-follow"},
    )
    cid = created["container"]["id"]

    start = await connected_driver.invoke(
        "container_logs",
        container_id=cid,
        tail=5,
        follow=True,
    )
    assert start["streaming"] is True

    await asyncio.sleep(0.3)

    log_events = [p for name, p in captured_events if name == "container_log_line"]
    assert log_events
    assert log_events[0]["container_id"] == cid

    stop = await connected_driver.invoke("stop_container_logs", container_id=cid)
    assert stop["stopped"] is True

    await connected_driver.invoke("remove_container", container_id=cid, force=True)
