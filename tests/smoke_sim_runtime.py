"""Smoke test: run DockerHostDriver with sim backend for a few seconds."""

from __future__ import annotations

import asyncio
import os

from device_connect_edge import DeviceRuntime

from dcd.device_connect import DockerHostDriver
from dcd.docker_backend import SimDockerBackend


async def main() -> None:
    os.environ.setdefault("DEVICE_CONNECT_ALLOW_INSECURE", "true")
    driver = DockerHostDriver(backend=SimDockerBackend(), simulate=True)
    runtime = DeviceRuntime(
        driver=driver,
        device_id="dcd-smoke",
        tenant="smoke",
        allow_insecure=True,
    )

    async def exercise() -> None:
        await asyncio.sleep(2)
        await driver.invoke("provision_container", spec={"image": "alpine:latest", "name": "smoke"})
        await asyncio.sleep(1)
        runtime.stop()

    runtime_task = asyncio.create_task(runtime.run())
    exercise_task = asyncio.create_task(exercise())
    await asyncio.wait([runtime_task, exercise_task], return_when=asyncio.FIRST_COMPLETED)
    print("smoke ok")


if __name__ == "__main__":
    asyncio.run(main())
