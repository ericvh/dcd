"""Device Connect driver exposing Docker Engine container lifecycle."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from device_connect_edge.drivers import DeviceDriver, emit, rpc
from device_connect_edge.types import DeviceIdentity, DeviceStatus

from dcd.docker_backend import DockerBackend, build_docker_backend
from dcd.models import ComposeProvisionSpec, ContainerProvisionSpec

logger = logging.getLogger(__name__)


class DockerHostDriver(DeviceDriver):
    """Device Connect driver for provisioning and controlling Docker containers.

    Exposes container CRUD, logs, exec, image pull, and compose up/down over
    the Device Connect mesh (D2D LAN or Portal-backed NATS).

    Interactive attach/TTY sessions are out of scope; use ``exec_in_container``
    for one-shot commands or follow logs via ``container_logs`` + events.
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
        self._poll_task: asyncio.Task[None] | None = None
        self._log_follow_tasks: dict[str, asyncio.Task[None]] = {}
        self._log_follow_stops: dict[str, asyncio.Event] = {}

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
        if self._state_poll_hz > 0:
            interval = max(0.1, 1.0 / self._state_poll_hz)
            self._poll_task = asyncio.create_task(
                self._poll_container_states_loop(interval),
                name="dcd-state-poll",
            )
        logger.info(
            "Docker host driver connected (sim=%s version=%s poll_hz=%s)",
            self._simulate,
            self._docker_info.get("docker_version"),
            self._state_poll_hz,
        )

    async def disconnect(self) -> None:
        self._connected = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        for container_id in list(self._log_follow_tasks):
            await self.stop_container_logs(container_id)
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
            "state_poll_hz": self._state_poll_hz,
            "log_follow_active": list(self._log_follow_tasks.keys()),
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
        follow: bool = False,
    ) -> dict[str, Any]:
        """Fetch container logs, or start streaming via ``container_log_line`` events.

        Args:
            container_id: Container ID or name.
            tail: Number of lines to return or seed a follow stream.
            since: Optional RFC3339 timestamp for log start.
            follow: When true, emit ``container_log_line`` events until
                ``stop_container_logs`` is called.
        """
        if follow:
            if container_id in self._log_follow_tasks:
                return {
                    "status": "success",
                    "streaming": True,
                    "container_id": container_id,
                    "already_following": True,
                }
            task = asyncio.create_task(
                self._follow_container_logs(container_id, tail=tail, since=since),
                name=f"dcd-logs-{container_id}",
            )
            self._log_follow_tasks[container_id] = task
            return {"status": "success", "streaming": True, "container_id": container_id}

        logs = await self._backend.container_logs(container_id, tail=tail, since=since)
        return {"status": "success", "container_id": container_id, "logs": logs}

    @rpc()
    async def stop_container_logs(self, container_id: str) -> dict[str, Any]:
        """Stop a log follow stream started by ``container_logs(..., follow=true)``."""
        stop = self._log_follow_stops.pop(container_id, None)
        if stop is not None:
            stop.set()
        task = self._log_follow_tasks.pop(container_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return {
            "status": "success",
            "container_id": container_id,
            "stopped": task is not None or stop is not None,
        }

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

    @emit()
    async def container_log_line(
        self,
        container_id: str,
        line: str,
        stream: str = "stdout",
    ) -> None:
        """Emitted for each log line when ``container_logs`` is called with ``follow=true``."""

    async def _poll_container_states_loop(self, interval: float) -> None:
        try:
            while self._connected:
                await self._poll_container_states_once()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise

    async def _poll_container_states_once(self) -> None:
        if not self._connected:
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

    async def _follow_container_logs(
        self,
        container_id: str,
        *,
        tail: int,
        since: str | None,
    ) -> None:
        stop = asyncio.Event()
        self._log_follow_stops[container_id] = stop

        async def on_line(stream: str, line: str) -> None:
            await self.container_log_line(
                container_id=container_id,
                line=line,
                stream=stream,
            )

        try:
            await self._backend.stream_container_logs(
                container_id,
                tail=tail,
                since=since,
                stop=stop,
                on_line=on_line,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Log follow failed for %s", container_id)
            raise
        finally:
            self._log_follow_stops.pop(container_id, None)
            self._log_follow_tasks.pop(container_id, None)
