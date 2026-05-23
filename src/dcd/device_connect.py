"""Device Connect driver exposing Docker Engine container lifecycle."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from device_connect_edge.drivers import DeviceDriver, emit, periodic, rpc
from device_connect_edge.types import DeviceIdentity, DeviceStatus

from dcd.docker_backend import DockerBackend, build_docker_backend
from dcd.models import ComposeProvisionSpec, ContainerProvisionSpec

logger = logging.getLogger(__name__)


class DockerHostDriver(DeviceDriver):
    """Device Connect driver for provisioning and controlling Docker containers.

    Exposes container CRUD, logs, exec, image pull, and compose up/down over
    the Device Connect mesh (D2D LAN or Portal-backed NATS).
    """

    device_type = "docker_host"

    def __init__(
        self,
        backend: DockerBackend | None = None,
        *,
        simulate: bool = False,
        docker_host: str | None = None,
        state_poll_hz: float = 2.0,
        host_label: str | None = None,
    ) -> None:
        super().__init__()
        self._backend = backend or build_docker_backend(simulate=simulate, docker_host=docker_host)
        self._simulate = simulate
        self._docker_host = docker_host
        self._state_poll_hz = state_poll_hz
        self._host_label = host_label
        self._connected = False
        self._docker_info: dict[str, Any] = {}
        self._last_container_states: dict[str, str] = {}

    @property
    def identity(self) -> DeviceIdentity:
        model = "simulated" if self._simulate else "Docker Engine"
        if self._host_label:
            model = f"{model} ({self._host_label})"
        return DeviceIdentity(
            device_type=self.device_type,
            manufacturer="Docker",
            model=model,
            description="Docker host — provision and control containers via Device Connect",
        )

    @property
    def status(self) -> DeviceStatus:
        availability = "idle" if self._connected else "offline"
        return DeviceStatus(ts=datetime.now(UTC), availability=availability)

    async def connect(self) -> None:
        self._docker_info = await self._backend.ping()
        self._connected = True
        logger.info(
            "Docker host driver connected (sim=%s version=%s)",
            self._simulate,
            self._docker_info.get("docker_version"),
        )

    async def disconnect(self) -> None:
        self._connected = False
        self._last_container_states.clear()
        logger.info("Docker host driver disconnected")

    @rpc()
    async def get_status(self) -> dict[str, Any]:
        """Return driver and Docker Engine connectivity status."""
        return {
            "status": "success",
            "connected": self._connected,
            "device_type": self.device_type,
            "simulate": self._simulate,
            "docker_host": self._docker_host,
            "docker": self._docker_info,
        }

    @rpc()
    async def ping_docker(self) -> dict[str, Any]:
        """Ping the Docker Engine and refresh cached engine metadata."""
        self._docker_info = await self._backend.ping()
        return {"status": "success", **self._docker_info}

    @rpc()
    async def list_containers(self, all_containers: bool = False) -> dict[str, Any]:
        """List containers on this Docker host.

        Args:
            all_containers: Include stopped containers when true.
        """
        containers = await self._backend.list_containers(all_containers=all_containers)
        return {
            "status": "success",
            "containers": [c.model_dump() for c in containers],
            "count": len(containers),
        }

    @rpc()
    async def get_container(self, container_id: str) -> dict[str, Any]:
        """Inspect a single container by ID or name."""
        summary = await self._backend.get_container(container_id)
        return {"status": "success", "container": summary.model_dump()}

    @rpc()
    async def provision_container(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Create (provision) a container from a JSON specification.

        Args:
            spec: Fields matching ContainerProvisionSpec (image, name, ports, …).
        """
        parsed = ContainerProvisionSpec.model_validate(spec)
        summary = await self._backend.create_container(parsed)
        await self.container_state_changed(
            container_id=summary.id,
            name=summary.name,
            previous_state=None,
            state=summary.state,
            image=summary.image,
        )
        return {"status": "success", "container": summary.model_dump()}

    @rpc()
    async def start_container(self, container_id: str) -> dict[str, Any]:
        """Start a stopped container."""
        summary = await self._backend.start_container(container_id)
        return {"status": "success", "container": summary.model_dump()}

    @rpc()
    async def stop_container(self, container_id: str, timeout_s: int = 10) -> dict[str, Any]:
        """Stop a running container."""
        summary = await self._backend.stop_container(container_id, timeout_s=timeout_s)
        return {"status": "success", "container": summary.model_dump()}

    @rpc()
    async def restart_container(self, container_id: str, timeout_s: int = 10) -> dict[str, Any]:
        """Restart a container."""
        summary = await self._backend.restart_container(container_id, timeout_s=timeout_s)
        return {"status": "success", "container": summary.model_dump()}

    @rpc()
    async def remove_container(self, container_id: str, force: bool = False) -> dict[str, Any]:
        """Remove a container."""
        await self._backend.remove_container(container_id, force=force)
        return {"status": "success", "container_id": container_id, "force": force}

    @rpc()
    async def container_logs(
        self,
        container_id: str,
        tail: int = 100,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Fetch container logs."""
        logs = await self._backend.container_logs(container_id, tail=tail, since=since)
        return {"status": "success", "container_id": container_id, "logs": logs}

    @rpc()
    async def exec_in_container(
        self,
        container_id: str,
        command: list[str],
        environment: dict[str, str] | None = None,
        workdir: str | None = None,
    ) -> dict[str, Any]:
        """Run a command inside a running container."""
        result = await self._backend.exec_in_container(
            container_id,
            command,
            environment=environment,
            workdir=workdir,
        )
        return {
            "status": "success" if result.exit_code == 0 else "error",
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    @rpc()
    async def pull_image(self, image: str) -> dict[str, Any]:
        """Pull an image from a registry."""
        result = await self._backend.pull_image(image)
        return {"status": "success", **result}

    @rpc()
    async def list_images(self) -> dict[str, Any]:
        """List images available on this host."""
        images = await self._backend.list_images()
        return {"status": "success", "images": images, "count": len(images)}

    @rpc()
    async def compose_up(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Start services with docker compose up."""
        parsed = ComposeProvisionSpec.model_validate(spec)
        result = await self._backend.compose_up(parsed)
        return {"status": "success", **result}

    @rpc()
    async def compose_down(
        self,
        project_dir: str,
        compose_file: str | None = None,
        remove_volumes: bool = False,
    ) -> dict[str, Any]:
        """Stop and remove compose project resources."""
        result = await self._backend.compose_down(
            project_dir=project_dir,
            compose_file=compose_file,
            remove_volumes=remove_volumes,
        )
        return {"status": "success", **result}

    @rpc()
    async def list_managed_containers(self) -> dict[str, Any]:
        """List containers labeled as managed by this driver."""
        containers = await self._backend.list_containers(all_containers=True)
        managed = [c for c in containers if c.managed_by_dcd]
        return {
            "status": "success",
            "containers": [c.model_dump() for c in managed],
            "count": len(managed),
        }

    @emit()
    async def container_state_changed(
        self,
        container_id: str,
        name: str,
        previous_state: str | None,
        state: str,
        image: str,
    ) -> None:
        """Emitted when a container transitions state."""

    @periodic(interval=0.5)
    async def _poll_container_states(self) -> None:
        if not self._connected or self._state_poll_hz <= 0:
            return
        containers = await self._backend.list_containers(all_containers=True)
        for summary in containers:
            prev = self._last_container_states.get(summary.id)
            if prev is not None and prev != summary.state:
                await self.container_state_changed(
                    container_id=summary.id,
                    name=summary.name,
                    previous_state=prev,
                    state=summary.state,
                    image=summary.image,
                )
        self._last_container_states = {c.id: c.state for c in containers}
