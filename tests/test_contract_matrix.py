"""Contract stability across pinned device-connect-edge versions."""

from __future__ import annotations

import importlib.metadata

from device_connect_edge import DeviceRuntime

from contract import PINNED_DEVICE_CONNECT_EDGE, REQUIRED_EVENTS, REQUIRED_FUNCTIONS
from dcd.device_connect import DockerHostDriver
from dcd.docker_backend import SimDockerBackend


def test_installed_device_connect_edge_matches_pin() -> None:
    installed = importlib.metadata.version("device-connect-edge")
    assert installed == PINNED_DEVICE_CONNECT_EDGE


def test_runtime_exposes_full_contract() -> None:
    driver = DockerHostDriver(backend=SimDockerBackend(), simulate=True)
    runtime = DeviceRuntime(
        driver=driver,
        device_id="contract-test",
        tenant="test",
        allow_insecure=True,
    )

    function_names = {func.name for func in runtime.capabilities.functions}
    event_names = {event.name for event in runtime.capabilities.events}

    missing_functions = REQUIRED_FUNCTIONS - function_names
    missing_events = REQUIRED_EVENTS - event_names

    assert not missing_functions, f"missing RPCs: {sorted(missing_functions)}"
    assert not missing_events, f"missing events: {sorted(missing_events)}"
